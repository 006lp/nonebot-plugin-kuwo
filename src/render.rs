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

/// Errors raised while rasterising an SVG document into PNG bytes.
#[derive(Debug)]
pub enum RenderError {
    InvalidScale(String),
    Font(String),
    Parse(String),
    Size(String),
    Encode(String),
}

impl std::fmt::Display for RenderError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidScale(message)
            | Self::Font(message)
            | Self::Parse(message)
            | Self::Size(message)
            | Self::Encode(message) => f.write_str(message),
        }
    }
}

impl std::error::Error for RenderError {}

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
) -> Result<ResolvedFonts, RenderError> {
    let mut database = fontdb::Database::new();

    if load_system_fonts {
        database.load_system_fonts();
    }

    for directory in font_dirs {
        database.load_fonts_dir(directory);
    }

    for file in font_files {
        database.load_font_file(file).map_err(|error| {
            RenderError::Font(format!("failed to load font file {file}: {error}"))
        })?;
    }

    // Without this the generic families stay pinned to Arial / Times New Roman,
    // which silently drops every glyph on hosts that ship neither.
    let default_family = select_default_family(&database);
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
) -> Result<ResolvedFonts, RenderError> {
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
/// `font_files` / `font_dirs` register extra fonts on top of the ones found on
/// the host system, which is what makes CJK text render on minimal images.
pub fn render_svg_to_png(
    svg: &str,
    scale: f32,
    font_files: &[String],
    font_dirs: &[String],
    load_system_fonts: bool,
) -> Result<Vec<u8>, RenderError> {
    if !scale.is_finite() || scale <= 0.0 || scale > MAX_RENDER_SCALE {
        return Err(RenderError::InvalidScale(format!(
            "scale must be finite and within (0, {MAX_RENDER_SCALE}], got {scale}"
        )));
    }

    let fonts = resolve_fonts(font_files, font_dirs, load_system_fonts)?;

    let mut options = usvg::Options::default();
    if let Some(family) = &fonts.default_family {
        options.font_family = family.clone();
    }
    options.fontdb = fonts.database;

    let tree = usvg::Tree::from_str(svg, &options)
        .map_err(|error| RenderError::Parse(error.to_string()))?;

    let size = tree.size();
    let width = (size.width() * scale).ceil().max(1.0) as u32;
    let height = (size.height() * scale).ceil().max(1.0) as u32;

    if width > MAX_RENDER_DIMENSION || height > MAX_RENDER_DIMENSION {
        return Err(RenderError::Size(format!(
            "render size {width}x{height} exceeds the {MAX_RENDER_DIMENSION}px limit"
        )));
    }

    let mut pixmap = tiny_skia::Pixmap::new(width, height)
        .ok_or_else(|| RenderError::Size(format!("cannot allocate pixmap of {width}x{height}")))?;

    resvg::render(
        &tree,
        tiny_skia::Transform::from_scale(scale, scale),
        &mut pixmap.as_mut(),
    );

    pixmap
        .encode_png()
        .map_err(|error| RenderError::Encode(error.to_string()))
}
