from __future__ import annotations

import asyncio
import base64
import importlib
import re
import struct
import threading
import zlib
from pathlib import Path
from xml.etree import ElementTree

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


def import_native_module():
    return importlib.import_module("nonebot_plugin_kuwo._native")


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


class FakeStreamResponse:
    def __init__(
        self,
        content: bytes,
        *,
        content_type: str = "image/png",
        status_code: int = 200,
    ) -> None:
        self.content = content
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.body_read = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")

    async def aiter_bytes(self, **kwargs):
        self.body_read = True
        chunk_size = max(1, len(self.content) // 3)
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start : start + chunk_size]


class FakeStreamClient:
    def __init__(self, response: FakeStreamResponse | None = None) -> None:
        self.response = response
        self.requested: list[str] = []

    def stream(self, method: str, url: str, **kwargs: object):
        self.requested.append(url)
        if self.response is None:
            raise httpx.ConnectError("boom")
        return _AsyncContext(self.response)


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def patch_cover_client(
    monkeypatch: pytest.MonkeyPatch, client: FakeStreamClient
) -> None:
    render = import_render_module()

    async def fake_get_http_client():
        return client

    monkeypatch.setattr(render, "get_http_client", fake_get_http_client)


def test_native_renderer_scales_output() -> None:
    native = import_native_module()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
        '<rect width="100" height="50" fill="#c26a2d"/>'
        "</svg>"
    )

    assert png_size(native.render_svg_to_png(svg)) == (100, 50)
    assert png_size(native.render_svg_to_png(svg, scale=2.0)) == (200, 100)


@pytest.mark.parametrize("scale", [0.0, -1.0, 9.0, float("nan"), float("inf")])
def test_native_renderer_rejects_invalid_scale(scale: float) -> None:
    native = import_native_module()
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'

    with pytest.raises(ValueError):
        native.render_svg_to_png(svg, scale=scale)


def test_native_renderer_rejects_oversized_document() -> None:
    native = import_native_module()
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="10"/>'

    with pytest.raises(ValueError):
        native.render_svg_to_png(svg)


def test_truncate_counts_cjk_as_two_units() -> None:
    render = import_render_module()

    assert render._truncate("Summer Pockets", 40) == "Summer Pockets"
    assert render._truncate("夏日口袋", 6) == "夏日…"
    assert render._truncate("   ", 4) == ""


def test_truncate_reserves_room_for_the_ellipsis() -> None:
    render = import_render_module()

    assert render._truncate("夏日口袋", 4) == "夏…"
    assert render._truncate("", 40, "Unknown Track") == "Unknown Track"


def test_format_duration_pads_seconds() -> None:
    render = import_render_module()

    assert render._format_duration(0) == "0:00"
    assert render._format_duration(61) == "1:01"
    assert render._format_duration(182) == "3:02"
    assert render._format_duration(-5) == "0:00"


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
    assert "3:02" in svg
    assert "1:01" in svg
    assert "553152678" in svg
    assert "2 Tracks" in svg


def test_build_search_results_svg_draws_vector_placeholder() -> None:
    render = import_render_module()
    svg = render._build_search_results_svg([build_search_song()], [None])

    assert "NO COVER" not in svg
    assert "<circle" in svg
    assert "cover-clip-1" not in svg


def test_build_search_results_svg_clips_text_block() -> None:
    render = import_render_module()
    svg = render._build_search_results_svg([build_search_song()], [None])

    assert '<clipPath id="text-clip-1">' in svg
    assert '<g clip-path="url(#text-clip-1)">' in svg


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
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"")

    font_files, font_dirs = render.resolve_font_sources(
        [str(font_file), str(tmp_path / "missing.ttf")],
        [str(tmp_path), str(tmp_path / "missing-dir")],
    )

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
    patch_cover_client(monkeypatch, FakeStreamClient(None))

    song = build_search_song(web_albumpic_short=COVER_PATH)

    assert await render._fetch_cover_data_uri(song) is None


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_rejects_non_image_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    response = FakeStreamResponse(b"<html></html>", content_type="text/html")
    patch_cover_client(monkeypatch, FakeStreamClient(response))

    song = build_search_song(web_albumpic_short=COVER_PATH)

    assert await render._fetch_cover_data_uri(song) is None
    assert response.body_read is False


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_rejects_mislabelled_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    response = FakeStreamResponse(b"<html></html>", content_type="image/png")
    patch_cover_client(monkeypatch, FakeStreamClient(response))

    song = build_search_song(web_albumpic_short=COVER_PATH)

    assert await render._fetch_cover_data_uri(song) is None


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_rejects_oversized_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    monkeypatch.setattr(render, "MAX_COVER_BYTES", 64)
    response = FakeStreamResponse(PNG_MAGIC + b"x" * 512)
    patch_cover_client(monkeypatch, FakeStreamClient(response))

    song = build_search_song(web_albumpic_short=COVER_PATH)

    assert await render._fetch_cover_data_uri(song) is None


@pytest.mark.asyncio
async def test_fetch_cover_data_uri_encodes_cover_as_data_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    client = FakeStreamClient(FakeStreamResponse(PNG_MAGIC + b"fake-cover"))
    patch_cover_client(monkeypatch, client)

    song = build_search_song(web_albumpic_short=COVER_PATH)
    data_uri = await render._fetch_cover_data_uri(song)

    assert client.requested == [COVER_URL]
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
        calls["thread"] = threading.current_thread().name
        return b"native-image"

    monkeypatch.setattr(render, "_fetch_cover_data_uri", fake_fetch_cover)
    monkeypatch.setattr(render, "render_svg_to_png", fake_render_svg_to_png)

    message = await render.render_search_results(
        [build_search_song()],
        config_module.ListRenderMode.IMAGE,
    )

    assert message == uniseg.UniMessage([uniseg.Image(raw=b"native-image")])
    assert calls["cover_song_id"] == "553152678"
    assert calls["kwargs"] == {
        "scale": render.IMAGE_SCALE,
        "font_files": [],
        "font_dirs": [],
    }
    assert calls["thread"] != threading.main_thread().name


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

    monkeypatch.setattr(render, "_fetch_cover_data_uri", fake_fetch_cover)

    result = await render.render_search_results(
        [build_search_song()],
        config_module.ListRenderMode.TEXT,
    )

    assert result == "1. 553152678 Summer Pockets-rionos"
    assert downloads == []


@pytest.mark.parametrize("width,height,scale", [(10000, 10000, 1), (1000, 1000, 3)])
def test_native_renderer_rejects_excessive_total_pixels(
    width: int, height: int, scale: float
) -> None:
    native = import_native_module()
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"/>'
    with pytest.raises(ValueError, match="pixel limit"):
        native.render_svg_to_png(svg, scale=scale, load_system_fonts=False)


def test_native_renderer_rejects_excessive_svg_bytes() -> None:
    native = import_native_module()
    with pytest.raises(ValueError, match="byte limit"):
        native.render_svg_to_png(" " * (16 * 1024 * 1024 + 1))


def test_native_renderer_reports_missing_fonts_for_text() -> None:
    native = import_native_module()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
        '<text x="0" y="20">夏日口袋</text></svg>'
    )
    with pytest.raises(ValueError, match="no fonts available"):
        native.render_svg_to_png(svg, load_system_fonts=False)


def make_cover_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    # Valid, highly compressible RGBA data exercises the decoded pixel limit.
    row = b"\x00" + b"\x00\xff\x00\xff" * width
    return (
        PNG_MAGIC
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize("width,height", [(4097, 1), (2049, 2049)])
def test_native_renderer_skips_oversized_covers(width: int, height: int) -> None:
    native = import_native_module()
    render = import_render_module()
    songs = [build_search_song()]
    png = make_cover_png(width, height)
    assert len(png) < render.MAX_COVER_BYTES
    uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    rendered = native.render_svg_to_png(render._build_search_results_svg(songs, [uri]))
    placeholder = native.render_svg_to_png(
        render._build_search_results_svg(songs, [None])
    )
    assert rendered == placeholder


def test_native_renderer_renders_valid_embedded_cover() -> None:
    native = import_native_module()
    render = import_render_module()
    songs = [build_search_song()]
    uri = "data:image/png;base64," + base64.b64encode(make_cover_png(2, 2)).decode()
    rendered = native.render_svg_to_png(render._build_search_results_svg(songs, [uri]))
    placeholder = native.render_svg_to_png(
        render._build_search_results_svg(songs, [None])
    )
    assert rendered != placeholder


def test_search_results_svg_removes_invalid_xml_characters() -> None:
    render = import_render_module()
    svg = render._build_search_results_svg(
        [build_search_song(NAME="夏日\x00口袋", ARTIST="A\ud800&B", ALBUM="<live>")],
        [None],
    )
    root = ElementTree.fromstring(svg)
    text = "".join(root.itertext())
    assert "夏日口袋" in text
    assert "A&B" in text
    assert "<live>" in text


@pytest.mark.asyncio
async def test_render_search_results_falls_back_without_fonts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    native = import_native_module()
    config = import_config_module()

    def render_without_fonts(svg: str, **kwargs) -> bytes:
        return native.render_svg_to_png(svg, load_system_fonts=False)

    monkeypatch.setattr(render, "render_svg_to_png", render_without_fonts)
    message = await render.render_search_results(
        [build_search_song()], config.ListRenderMode.IMAGE
    )
    assert message == "1. 553152678 Summer Pockets-rionos"


@pytest.mark.asyncio
async def test_render_serializes_native_work_and_keeps_slot_on_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    config = import_config_module()
    monkeypatch.setattr(render, "_image_render_lock", asyncio.Lock())
    started = threading.Event()
    release = threading.Event()
    active = 0
    peak = 0

    def slow_render(svg: str, **kwargs) -> bytes:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started.set()
        assert release.wait(timeout=5)
        active -= 1
        return b"native-image"

    monkeypatch.setattr(render, "render_svg_to_png", slow_render)
    first = asyncio.create_task(
        render.render_search_results([build_search_song()], config.ListRenderMode.IMAGE)
    )
    second = None
    try:
        assert await asyncio.to_thread(started.wait, 2)
        first.cancel()
        second = asyncio.create_task(
            render.render_search_results(
                [build_search_song()], config.ListRenderMode.IMAGE
            )
        )
        await asyncio.sleep(0.05)
        assert not first.done()
        assert active == 1
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (first, second) if task is not None),
            return_exceptions=True,
        )
    assert first.cancelled()
    assert peak == 1


@pytest.mark.asyncio
async def test_cover_rejects_compressed_response_before_reading_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = import_render_module()
    response = FakeStreamResponse(PNG_MAGIC + b"cover")
    response.headers["content-encoding"] = "gzip"
    patch_cover_client(monkeypatch, FakeStreamClient(response))
    assert (
        await render._fetch_cover_data_uri(
            build_search_song(web_albumpic_short=COVER_PATH)
        )
        is None
    )
    assert response.body_read is False


@pytest.mark.asyncio
async def test_fetch_cover_follows_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    render = import_render_module()
    cover = make_cover_png(2, 2)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".jpg"):
            return httpx.Response(302, headers={"location": "/cover.png"})
        return httpx.Response(200, content=cover, headers={"content-type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

        async def fake_get_http_client():
            return client

        monkeypatch.setattr(render, "get_http_client", fake_get_http_client)
        uri = await render._fetch_cover_data_uri(
            build_search_song(web_albumpic_short=COVER_PATH)
        )
    assert uri == "data:image/png;base64," + base64.b64encode(cover).decode()
