use std::sync::{Arc, Mutex};

use resvg::tiny_skia;
use resvg::usvg;
use usvg::fontdb;

/// Families probed in order when the document does not pin a font explicitly.
///
/// CJK-capable faces come first so a Chinese song title renders with the same
/// face as the surrounding Latin text instead of collapsing into tofu boxes.
const PREFERRED_FONT_FAMILIES: &[&str] = &[
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Sans SC",
    "Noto Sans TC",
    "Source Han Sans SC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Droid Sans Fallback",
    "Microsoft YaHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Sans",
    "DejaVu Sans",
    "Liberation Sans",
    "Arial",
    "Helvetica",
];

/// Upper bound for the rasterisation scale factor.
const MAX_RENDER_SCALE: f32 = 8.0;
/// Upper bound for either pixmap dimension, in pixels.
const MAX_RENDER_DIMENSION: u32 = 16_384;
/// Bound decoded memory as well as each dimension.
const MAX_RENDER_PIXELS: u64 = 8_388_608;
const MAX_COVER_PIXELS: usize = 4_194_304;
const MAX_COVER_DIMENSION: usize = 4_096;
const MAX_COVER_BYTES: usize = 5 * 1024 * 1024;
const MAX_SVG_BYTES: usize = 16 * 1024 * 1024;

#[derive(Clone, PartialEq, Eq)]
struct FontCacheKey {
    font_files: Vec<String>,
    font_dirs: Vec<String>,
    load_system_fonts: bool,
}

#[derive(Clone)]
struct ResolvedFonts {
    database: Arc<fontdb::Database>,
    default_family: Option<String>,
}

static FONT_CACHE: Mutex<Option<(FontCacheKey, ResolvedFonts)>> = Mutex::new(None);

fn select_default_family(database: &fontdb::Database) -> Option<String> {
    for candidate in PREFERRED_FONT_FAMILIES {
        let families = [fontdb::Family::Name(candidate)];
        let query = fontdb::Query {
            families: &families,
            ..fontdb::Query::default()
        };
        if database.query(&query).is_some() {
            return Some((*candidate).to_string());
        }
    }

    database
        .faces()
        .find_map(|face| face.families.first().map(|(name, _)| name.clone()))
}

fn build_font_database(
    font_files: &[String],
    font_dirs: &[String],
    load_system_fonts: bool,
) -> Result<ResolvedFonts, String> {
    let mut database = fontdb::Database::new();

    for file in font_files {
        database
            .load_font_file(file)
            .map_err(|error| format!("failed to load font file {file}: {error}"))?;
    }

    for directory in font_dirs {
        database.load_fonts_dir(directory);
    }

    // Explicit sources take priority over system fonts, including the bundled
    // default passed by the plugin. File order is preserved before directories.
    let explicit_family = database
        .faces()
        .find_map(|face| face.families.first().map(|(name, _)| name.clone()));
    if load_system_fonts {
        database.load_system_fonts();
    }

    // Without this the generic families stay pinned to Arial / Times New Roman,
    // which silently drops every glyph on hosts that ship neither.
    let default_family = explicit_family.or_else(|| select_default_family(&database));
    if let Some(family) = &default_family {
        database.set_sans_serif_family(family.clone());
        database.set_serif_family(family.clone());
        database.set_monospace_family(family.clone());
    }

    Ok(ResolvedFonts {
        database: Arc::new(database),
        default_family,
    })
}

/// Resolve (and cache) the font database for a given font configuration.
///
/// Scanning system fonts costs tens of milliseconds, so the result is memoised
/// behind a single-entry cache keyed by the exact font configuration.
fn resolve_fonts(
    font_files: &[String],
    font_dirs: &[String],
    load_system_fonts: bool,
) -> Result<ResolvedFonts, String> {
    let key = FontCacheKey {
        font_files: font_files.to_vec(),
        font_dirs: font_dirs.to_vec(),
        load_system_fonts,
    };

    {
        let guard = FONT_CACHE.lock().unwrap_or_else(|error| error.into_inner());
        if let Some((cached_key, cached_fonts)) = guard.as_ref() {
            if *cached_key == key {
                return Ok(cached_fonts.clone());
            }
        }
    }

    let resolved = build_font_database(font_files, font_dirs, load_system_fonts)?;

    let mut guard = FONT_CACHE.lock().unwrap_or_else(|error| error.into_inner());
    *guard = Some((key, resolved.clone()));
    Ok(resolved)
}

/// Rasterise an SVG string into PNG bytes.
///
/// `scale` multiplies the intrinsic SVG size, so `2.0` yields a HiDPI bitmap.
/// `font_files` / `font_dirs` take priority over host system fonts, which remain
/// available as glyph fallbacks. The first loaded explicit face is the default.
pub fn render_svg_to_png(
    svg: &str,
    scale: f32,
    font_files: &[String],
    font_dirs: &[String],
    load_system_fonts: bool,
) -> Result<Vec<u8>, String> {
    if !scale.is_finite() || scale <= 0.0 || scale > MAX_RENDER_SCALE {
        return Err(format!(
            "scale must be finite and within (0, {MAX_RENDER_SCALE}], got {scale}"
        ));
    }
    if svg.len() > MAX_SVG_BYTES {
        return Err(format!("SVG exceeds the {MAX_SVG_BYTES} byte limit"));
    }

    let document = usvg::roxmltree::Document::parse(svg).map_err(|error| error.to_string())?;

    let fonts = resolve_fonts(font_files, font_dirs, load_system_fonts)?;
    if fonts.database.is_empty()
        && document
            .descendants()
            .any(|node| node.has_tag_name(("http://www.w3.org/2000/svg", "text")))
    {
        return Err(
            "no fonts available for SVG text; install a CJK font or configure font sources"
                .to_string(),
        );
    }

    let mut options = usvg::Options::default();
    if let Some(family) = &fonts.default_family {
        options.font_family = family.clone();
    }
    options.fontdb = fonts.database;
    // Covers are embedded raster images. Inspect headers before any decoder
    // allocates pixel buffers, and never resolve local files or nested SVGs.
    let default_data_resolver = usvg::ImageHrefResolver::default_data_resolver();
    options.image_href_resolver = usvg::ImageHrefResolver {
        resolve_string: Box::new(|_, _| None),
        resolve_data: Box::new(move |mime, data, options| {
            if data.len() > MAX_COVER_BYTES
                || !matches!(
                    mime,
                    "image/png" | "image/jpeg" | "image/gif" | "image/webp"
                )
            {
                return None;
            }
            let size = imagesize::blob_size(&data).ok()?;
            if size.width == 0
                || size.height == 0
                || size.width > MAX_COVER_DIMENSION
                || size.height > MAX_COVER_DIMENSION
                || size.width.checked_mul(size.height)? > MAX_COVER_PIXELS
            {
                return None;
            }
            default_data_resolver(mime, data, options)
        }),
    };

    let tree = usvg::Tree::from_xmltree(&document, &options).map_err(|error| error.to_string())?;

    let size = tree.size();
    let width = (size.width() * scale).ceil().max(1.0) as u32;
    let height = (size.height() * scale).ceil().max(1.0) as u32;

    if width > MAX_RENDER_DIMENSION || height > MAX_RENDER_DIMENSION {
        return Err(format!(
            "render size {width}x{height} exceeds the {MAX_RENDER_DIMENSION}px limit"
        ));
    }
    if u64::from(width) * u64::from(height) > MAX_RENDER_PIXELS {
        return Err(format!(
            "render size {width}x{height} exceeds the {MAX_RENDER_PIXELS} pixel limit"
        ));
    }

    let mut pixmap = tiny_skia::Pixmap::new(width, height)
        .ok_or_else(|| format!("cannot allocate pixmap of {width}x{height}"))?;

    resvg::render(
        &tree,
        tiny_skia::Transform::from_scale(scale, scale),
        &mut pixmap.as_mut(),
    );

    pixmap.encode_png().map_err(|error| error.to_string())
}
