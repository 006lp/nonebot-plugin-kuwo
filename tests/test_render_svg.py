from __future__ import annotations

import importlib
import struct
import xml.etree.ElementTree as ET

import httpx
import pytest


def modules():
    return (importlib.import_module('nonebot_plugin_kuwo.render'),
            importlib.import_module('nonebot_plugin_kuwo.models'))


def song():
    _, models = modules()
    return models.KuwoSearchSong(MUSICRID='MUSIC_123', NAME='中文 <Song> & "title"',
                               ARTIST='Artist & Singer', ALBUM='Album', DURATION='182',
                               web_albumpic_short='cover.png')


def test_actual_svg_renders_png():
    render, _ = modules()
    svg = render._build_search_results_svg([song()], [None])
    ET.fromstring(svg)
    assert '&lt;Song&gt; &amp;' in svg
    png = render.render_svg_to_png(svg, 2.0)
    assert png.startswith(b'\x89PNG\r\n\x1a\n')
    assert struct.unpack('>II', png[16:24]) == (1960, 628)


@pytest.mark.parametrize('scale', [0, -1, 9, float('nan'), float('inf')])
def test_invalid_scale(scale):
    render, _ = modules()
    with pytest.raises(ValueError):
        render.render_svg_to_png('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>', scale)


@pytest.mark.parametrize('svg', ['not XML', '<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="1"/>'])
def test_invalid_svg(svg):
    render, _ = modules()
    with pytest.raises(ValueError):
        render.render_svg_to_png(svg)


@pytest.mark.asyncio
async def test_render_failure_falls_back_to_text(monkeypatch):
    render, _ = modules()
    async def covers(songs):
        return [None]
    def fail(*args):
        raise ValueError('rasterizer failed')
    monkeypatch.setattr(render, '_fetch_cover_data_uris', covers)
    monkeypatch.setattr(render, 'render_svg_to_png', fail)
    result = await render.render_search_results([song()], render.ListRenderMode.IMAGE)
    assert result == '1. 123 中文 <Song> & "title"-Artist & Singer'


@pytest.mark.asyncio
@pytest.mark.parametrize('status, content_type, body, expected', [
    (200, 'image/png', b'cover', 'data:image/png;base64,Y292ZXI='),
    (200, 'text/html', b'error page', None),
    (404, 'image/png', b'cover', None),
    (200, 'image/png', b'x' * 17, None),
])
async def test_cover_responses(monkeypatch, status, content_type, body, expected):
    render, _ = modules()
    monkeypatch.setattr(render, '_MAX_COVER_BYTES', 16)
    def handler(request):
        return httpx.Response(status, headers={'content-type': content_type}, content=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await render._fetch_cover_data_uri(client, song()) == expected


def test_truncate_respects_full_width_characters():
    render, _ = modules()
    assert render._truncate("中" * 34, 34) == "中" * 16 + "…"
    assert render._truncate("A" * 34, 34) == "A" * 34
    assert render._truncate("短标题", 34) == "短标题"
