use std::sync::Arc;

use resvg::tiny_skia;
use resvg::usvg;
use usvg::fontdb;

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

fn build_font_database(
    font_files: &[String],
    font_dirs: &[String],
    load_system_fonts: bool,
) -> Result<fontdb::Database, RenderError> {
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

    Ok(database)
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
    if !scale.is_finite() || scale <= 0.0 {
        return Err(RenderError::InvalidScale(format!(
            "scale must be a positive finite number, got {scale}"
        )));
    }

    let font_database = build_font_database(font_files, font_dirs, load_system_fonts)?;

    let options = usvg::Options {
        fontdb: Arc::new(font_database),
        ..usvg::Options::default()
    };

    let tree = usvg::Tree::from_str(svg, &options)
        .map_err(|error| RenderError::Parse(error.to_string()))?;

    let size = tree.size();
    let width = (size.width() * scale).ceil().max(1.0) as u32;
    let height = (size.height() * scale).ceil().max(1.0) as u32;

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
