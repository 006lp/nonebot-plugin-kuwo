from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast


@lru_cache(maxsize=1)
def load_extension() -> ModuleType:
    """Load the shared native extension only when one of its features is used."""
    try:
        return import_module("nonebot_plugin_kuwo._qmc_rs")
    except ImportError as exc:  # pragma: no cover - requires native build
        raise ImportError(
            "nonebot_plugin_kuwo Rust extension is missing. "
            "Run `uv run maturin develop` or install a built wheel."
        ) from exc


class _SvgExtension(Protocol):
    def render_svg_to_png(
        self,
        svg: str,
        scale: float = 1.0,
        font_files: list[str] | None = None,
        font_dirs: list[str] | None = None,
        load_system_fonts: bool = True,
    ) -> bytes: ...


def render_svg_to_png(
    svg: str,
    *,
    scale: float = 1.0,
    font_files: list[str | Path] | None = None,
    font_dirs: list[str | Path] | None = None,
    load_system_fonts: bool = True,
) -> bytes:
    """Rasterise an SVG document into PNG bytes via the native resvg backend."""
    extension = cast(_SvgExtension, load_extension())
    return extension.render_svg_to_png(
        svg,
        scale,
        [str(item) for item in font_files] if font_files else None,
        [str(item) for item in font_dirs] if font_dirs else None,
        load_system_fonts,
    )
