from __future__ import annotations

import importlib
import re
import struct
from pathlib import Path

import httpx
import pytest
from nonebot.compat import type_validate_python

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
COVER_PATH = "120/s4s64/98/1370027605.jpg"
COVER_URL = f"http://img1.kwcdn.kuwo.cn/star/albumcover/{COVER_PATH}"


def import_render_module():
    return importlib.import_module("nonebot_plugin_kuwo.render")


def import_config_module():
    return importlib.import_module("nonebot_plugin_kuwo.config")


def import_models_module():
    return importlib.import_module("nonebot_plugin_kuwo.models")


def import_qmc_module():
    return importlib.import_module("nonebot_plugin_kuwo.qmc")


def import_uniseg_module():
    return importlib.import_module("nonebot_plugin_alconna.uniseg")


def build_search_song(**overrides: object):
    models = import_models_module()
    payload: dict[str, object] = {
        "MUSICRID": "MUSIC_553152678",
        "NAME": "Summer Pockets",
        "ARTIST": "rionos",
        "ALBUM": "Summer Pockets",
        "DURATION": "182",
    }
    payload.update(overrides)
    return type_validate_python(models.KuwoSearchSong, payload)


def png_size(data: bytes) -> tuple[int, int]:
    assert data.startswith(PNG_MAGIC)
    return struct.unpack(">II", data[16:24])


def canvas_height(svg: str) -> int:
    match = re.search(r'height="(\d+)"', svg)
    assert match is not None
    return int(match.group(1))


def test_native_renderer_scales_output() -> None:
    qmc = import_qmc_module()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
        '<rect width="100" height="50" fill="#c26a2d"/>'
        "</svg>"
    )

    assert png_size(qmc.render_svg_to_png(svg)) == (100, 50)
    assert png_size(qmc.render_svg_to_png(svg, scale=2.0)) == (200, 100)


def test_native_renderer_rejects_invalid_scale() -> None:
    qmc = import_qmc_module()
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'

    with pytest.raises(ValueError):
        qmc.render_svg_to_png(svg, scale=0.0)


def test_truncate_counts_cjk_as_two_units() -> None:
    render = import_render_module()

    assert render._truncate("Summer Pockets", 40) == "Summer Pockets"
    assert render._truncate("夏日口袋", 4) == "夏日…"
    assert render._truncate("   ", 4) == ""


def test_sniff_image_mime_detects_supported_formats() -> None:
    render = import_render_module()

    assert render._sniff_image_mime(PNG_MAGIC + b"rest") == "image/png"
    assert render._sniff_image_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert render._sniff_image_mime(b"GIF89a-rest") == "image/gif"
    assert render._sniff_image_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert render._sniff_image_mime(b"<html></html>") is None


def test_build_search_results_svg_embeds_cover_and_metadata() -> None:
    render = import_render_module()
    songs = [
        build_search_song(),
        build_search_song(
            MUSICRID="MUSIC_1",
            NAME="夏日口袋",
            ARTIST="rionos",
            DURATION="61",
        ),
    ]

    svg = render._build_search_results_svg(
        songs,
        ["data:image/png;base64,AAAA", None],
    )

    assert "data:image/png;base64,AAAA" in svg
    assert "Summer Pockets" in svg
    assert "夏日口袋" in svg
    assert "NO COVER" in svg
    assert "553152678" in svg
    assert "182s" in svg
    assert "2 Tracks" in svg


def test_build_search_results_svg_grows_with_row_count() -> None:
    render = import_render_module()
    single = render._build_search_results_svg([build_search_song()], [None])
    double = render._build_search_results_svg(
        [build_search_song(), build_search_song()],
        [None, None],
    )

    assert canvas_height(double) - canvas_height(single) == (
        render.ROW_HEIGHT + render.ROW_GAP
    )


def test_build_search_results_svg_escapes_song_fields() -> None:
    render = import_render_module()
    svg = render._build_search_results_svg(
        [build_search_song(NAME="A & B <live>")],
        [None],
    )

    assert "A &amp; B &lt;live&gt;" in svg
    assert "<live>" not in svg


def test_resolve_font_sources_filters_missing_paths(tmp_path: Path) -> None:
    render = import_render_module()
    config_module = import_config_module()
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"")

    config = config_module.Config(
        kuwo_render_font_files=[str(font_file), str(tmp_path / "missing.ttf")],
        kuwo_render_font_dirs=[str(tmp_path), str(tmp_path / "missing-dir")],
    )

    font_files, font_dirs = render.resolve_font_sources(config)

    assert font_files == [str(font_file)]
    assert font_dirs == [str(tmp_path)]


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_returns_none_without_cover() -> None:
    render = import_render_module()

    assert await render._fetch_cover_data_uri(build_search_song()) is None


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_returns_none_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()

    class FailingClient:
        async def get(self, url: str, timeout: float | None = None):
            raise httpx.ConnectError("boom")

    async def fake_get_http_client():
        return FailingClient()

    monkeypatch.setattr(render, "get_http_client", fake_get_http_client)

    song = build_search_song(web_albumpic_short=COVER_PATH)

    assert await render._fetch_cover_data_uri(song) is None


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_rejects_unsupported_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()

    class HtmlResponse:
        content = b"<html></html>"
        headers = {"content-type": "text/html"}

        def raise_for_status(self) -> None:
            return None

    class HtmlClient:
        async def get(self, url: str, timeout: float | None = None):
            return HtmlResponse()

    async def fake_get_http_client():
        return HtmlClient()

    monkeypatch.setattr(render, "get_http_client", fake_get_http_client)

    song = build_search_song(web_albumpic_short=COVER_PATH)

    assert await render._fetch_cover_data_uri(song) is None


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_encodes_cover_as_data_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    cover_bytes = PNG_MAGIC + b"fake-cover"
    requested: list[str] = []

    class CoverResponse:
        content = cover_bytes
        headers = {"content-type": "image/png"}

        def raise_for_status(self) -> None:
            return None

    class CoverClient:
        async def get(self, url: str, timeout: float | None = None):
            requested.append(url)
            return CoverResponse()

    async def fake_get_http_client():
        return CoverClient()

    monkeypatch.setattr(render, "get_http_client", fake_get_http_client)

    song = build_search_song(web_albumpic_short=COVER_PATH)
    data_uri = await render._fetch_cover_data_uri(song)

    assert requested == [COVER_URL]
    assert data_uri is not None
    assert data_uri.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_render_search_results_image_mode_returns_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    config_module = import_config_module()
    uniseg = import_uniseg_module()
    calls: dict[str, object] = {}

    async def fake_fetch_cover(song):
        calls["cover_song_id"] = song.song_id
        return "data:image/png;base64,AAAA"

    def fake_render_svg_to_png(svg: str, **kwargs) -> bytes:
        calls["svg"] = svg
        calls["kwargs"] = kwargs
        return b"native-image"

    monkeypatch.setattr(render, "_fetch_cover_data_uri", fake_fetch_cover)
    monkeypatch.setattr(render, "render_svg_to_png", fake_render_svg_to_png)

    message = await render.render_search_results(
        [build_search_song()],
        config_module.ListRenderMode.IMAGE,
        config_module.Config(),
    )

    assert message == uniseg.UniMessage([uniseg.Image(raw=b"native-image")])
    assert calls["cover_song_id"] == "553152678"
    assert calls["kwargs"] == {
        "scale": render.IMAGE_SCALE,
        "font_files": [],
        "font_dirs": [],
    }


@pytest.mark.asyncio
async def test_render_search_results_falls_back_to_text_when_render_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    config_module = import_config_module()

    async def fake_fetch_cover(song):
        return None

    def broken_render_svg_to_png(svg: str, **kwargs) -> bytes:
        raise ValueError("native renderer exploded")

    monkeypatch.setattr(render, "_fetch_cover_data_uri", fake_fetch_cover)
    monkeypatch.setattr(render, "render_svg_to_png", broken_render_svg_to_png)

    result = await render.render_search_results(
        [build_search_song()],
        config_module.ListRenderMode.IMAGE,
        config_module.Config(),
    )

    assert result == "1. 553152678 Summer Pockets-rionos"


@pytest.mark.asyncio
async def test_render_search_results_text_mode_skips_cover_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    config_module = import_config_module()
    downloads: list[str] = []

    async def fake_fetch_cover(song):
        downloads.append(song.song_id)
        return None

    monkeypatch.setattr(render, "_fetch_cover_data_uri", fake_fetch_cover)

    result = await render.render_search_results(
        [build_search_song()],
        config_module.ListRenderMode.TEXT,
        config_module.Config(),
    )

    assert result == "1. 553152678 Summer Pockets-rionos"
    assert downloads == []
