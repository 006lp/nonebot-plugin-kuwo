from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_extension():
    """Load the shared native extension only when one of its features is used."""
    try:
        from . import _qmc_rs

        return _qmc_rs
    except ImportError as exc:  # pragma: no cover - requires native build
        raise ImportError(
            "nonebot_plugin_kuwo Rust extension is missing. "
            "Run `uv run maturin develop` or install a built wheel."
        ) from exc


def render_svg_to_png(
    svg: str,
    *,
    scale: float = 1.0,
    font_files: list[str | Path] | None = None,
    font_dirs: list[str | Path] | None = None,
    load_system_fonts: bool = True,
) -> bytes:
    """Rasterise an SVG document into PNG bytes via the native resvg backend."""
    return load_extension().render_svg_to_png(
        svg,
        scale,
        [str(item) for item in font_files] if font_files else None,
        [str(item) for item in font_dirs] if font_dirs else None,
        load_system_fonts,
    )
