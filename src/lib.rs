use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

mod qmc;
mod render;

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

#[pyfunction]
#[pyo3(signature = (svg, scale = 1.0, font_files = None, font_dirs = None, load_system_fonts = true))]
fn render_svg_to_png(
    py: Python<'_>,
    svg: &str,
    scale: f32,
    font_files: Option<Vec<String>>,
    font_dirs: Option<Vec<String>>,
    load_system_fonts: bool,
) -> PyResult<Py<PyBytes>> {
    let font_files = font_files.unwrap_or_default();
    let font_dirs = font_dirs.unwrap_or_default();
    let png = py
        .detach(|| {
            render::render_svg_to_png(svg, scale, &font_files, &font_dirs, load_system_fonts)
        })
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
