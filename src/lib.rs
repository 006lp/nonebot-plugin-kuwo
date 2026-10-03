use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use resvg::{tiny_skia, usvg};

mod qmc;

const MAX_RENDER_DIMENSION: u32 = 16_384;

#[pyfunction]
fn kuwo_base64_decrypt(value: &str) -> PyResult<String> {
    qmc::kuwo_base64_decrypt(value).map_err(Into::into)
}

#[pyfunction]
fn extract_qmc_raw_key_from_ekey(py: Python<'_>, ekey: &str) -> PyResult<Py<PyBytes>> {
    let raw_key = qmc::extract_qmc_raw_key_from_ekey(ekey)?;
    Ok(PyBytes::new(py, &raw_key).into())
}

#[pyfunction]
fn derive_qmc_key(py: Python<'_>, raw_key: &[u8]) -> PyResult<Py<PyBytes>> {
    let derived_key = qmc::derive_qmc_key(raw_key)?;
    Ok(PyBytes::new(py, &derived_key).into())
}

#[pyfunction]
#[pyo3(signature = (data, raw_key, offset = 0))]
fn decrypt_qmc_bytes(
    py: Python<'_>,
    data: &[u8],
    raw_key: &[u8],
    offset: usize,
) -> PyResult<Py<PyBytes>> {
    let decrypted = py.detach(|| qmc::decrypt_qmc_bytes(data, raw_key, offset))?;
    Ok(PyBytes::new(py, &decrypted).into())
}

#[pyfunction]
#[pyo3(signature = (source_path, target_path, ekey, chunk_size = 65536))]
fn decrypt_mflac_file(
    py: Python<'_>,
    source_path: &str,
    target_path: &str,
    ekey: &str,
    chunk_size: usize,
) -> PyResult<()> {
    if chunk_size == 0 {
        return Err(PyValueError::new_err("chunk_size must be greater than 0"));
    }
    Ok(py.detach(|| qmc::decrypt_mflac_file(source_path, target_path, ekey, chunk_size))?)
}

fn render_svg(svg: &str, scale: f32) -> Result<Vec<u8>, String> {
    if !scale.is_finite() || scale <= 0.0 || scale > 8.0 {
        return Err("scale must be finite and in the range (0, 8]".to_string());
    }

    let mut options = usvg::Options::default();
    options.fontdb_mut().load_system_fonts();
    let tree = usvg::Tree::from_data(svg.as_bytes(), &options)
        .map_err(|err| format!("failed to parse SVG: {err}"))?;

    let size = tree.size();
    let width = (size.width() * scale).ceil() as u32;
    let height = (size.height() * scale).ceil() as u32;
    if width == 0 || height == 0 || width > MAX_RENDER_DIMENSION || height > MAX_RENDER_DIMENSION {
        return Err(format!(
            "render size {width}x{height} is invalid or too large"
        ));
    }

    let mut pixmap = tiny_skia::Pixmap::new(width, height)
        .ok_or_else(|| format!("failed to allocate {width}x{height} pixmap"))?;
    resvg::render(
        &tree,
        tiny_skia::Transform::from_scale(scale, scale),
        &mut pixmap.as_mut(),
    );
    pixmap
        .encode_png()
        .map_err(|err| format!("failed to encode PNG: {err}"))
}

#[pyfunction]
#[pyo3(signature = (svg, scale = 1.0))]
fn render_svg_to_png(py: Python<'_>, svg: &str, scale: f32) -> PyResult<Py<PyBytes>> {
    let png = py
        .detach(|| render_svg(svg, scale))
        .map_err(PyValueError::new_err)?;
    Ok(PyBytes::new(py, &png).into())
}

#[pymodule(gil_used = false)]
#[pyo3(name = "_qmc_rs")]
fn qmc_rs(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(kuwo_base64_decrypt, module)?)?;
    module.add_function(wrap_pyfunction!(extract_qmc_raw_key_from_ekey, module)?)?;
    module.add_function(wrap_pyfunction!(derive_qmc_key, module)?)?;
    module.add_function(wrap_pyfunction!(decrypt_qmc_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(decrypt_mflac_file, module)?)?;
    module.add_function(wrap_pyfunction!(render_svg_to_png, module)?)?;
    Ok(())
}
