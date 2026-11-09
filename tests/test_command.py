from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from nonebot.compat import type_validate_python


def import_plugin_module():
    return importlib.import_module("nonebot_plugin_kuwo")


def import_config_module():
    return importlib.import_module("nonebot_plugin_kuwo.config")


def import_models_module():
    return importlib.import_module("nonebot_plugin_kuwo.models")


def import_render_module():
    return importlib.import_module("nonebot_plugin_kuwo.render")


def import_utils_module():
    return importlib.import_module("nonebot_plugin_kuwo.utils")


def import_uniseg_module():
    return importlib.import_module("nonebot_plugin_alconna.uniseg")


def import_music_share_module():
    return importlib.import_module("nonebot_plugin_alconna.builtins.uniseg.music_share")


class MatcherFinished(Exception):
    pass


class DummyMatcher:
    def __init__(self) -> None:
        self.message = None

    async def finish(self, message) -> None:
        self.message = message
        raise MatcherFinished


def build_search_song(**overrides: object):
    models = import_models_module()
    payload: dict[str, object] = {
        "MUSICRID": "MUSIC_553152678",
        "NAME": "Morning Dew Reflection.wav",
        "ARTIST": "rionos&Kangseoha&Kim Yoon",
        "ALBUM": "Morning Dew Reflection",
        "DURATION": "182",
    }
    payload.update(overrides)
    return type_validate_python(models.KuwoSearchSong, payload)


def make_arp(**all_matched_args: object):
    return type("Arp", (), {"all_matched_args": all_matched_args})()


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_mode", [None, "text", "TEXT"])
async def test_kwsearch_command_returns_text_results(
    monkeypatch: pytest.MonkeyPatch,
    requested_mode: str | None,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    dummy_matcher = DummyMatcher()
    command = plugin.kwsearch.command()
    config = config_module.Config(
        kuwo_search_limit=5,
        kuwo_list_render_mode="image" if requested_mode else "text",
    )
    original_mode = config.kuwo_list_render_mode

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 5
        return [build_search_song()]

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "kwsearch", dummy_matcher)
    monkeypatch.setattr(plugin, "get_runtime_config", lambda: config)

    options = f" -m {requested_mode}" if requested_mode else ""
    arp = command.parse(f"/kwsearch Morning Dew Reflection{options}")
    assert arp.matched
    with pytest.raises(MatcherFinished):
        await plugin.handle_kwsearch(arp)

    assert dummy_matcher.message == (
        "1. 553152678 Morning Dew Reflection.wav-rionos&Kangseoha&Kim Yoon"
    )
    assert config.kuwo_list_render_mode is original_mode


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_mode", [None, "image", "IMAGE"])
async def test_kwsearch_command_returns_image_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    requested_mode: str | None,
) -> None:
    plugin = import_plugin_module()
    render_module = import_render_module()
    config_module = import_config_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()
    command = plugin.kwsearch.command()
    config = config_module.Config(
        kuwo_search_limit=5,
        kuwo_list_render_mode="text" if requested_mode else "image",
        kuwo_render_custom_font="custom.ttf",
    )
    original_mode = config.kuwo_list_render_mode
    render_calls: dict[str, object] = {}
    cover_calls: dict[str, object] = {}
    font_path = tmp_path / "custom.ttf"
    font_path.touch()
    monkeypatch.setattr(render_module, "_render_config_dir", tmp_path)

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 5
        return [build_search_song(web_albumpic_short="120/s4s64/98/1370027605.jpg")]

    async def fake_fetch_cover(song):
        cover_calls["url"] = song.album_cover_url
        return "data:image/png;base64,AAAA"

    def fake_render_svg_to_png(svg: str, **kwargs) -> bytes:
        render_calls["svg"] = svg
        render_calls["scale"] = kwargs["scale"]
        render_calls["font_files"] = kwargs["font_files"]
        return b"rendered-image"

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(render_module, "_fetch_cover_data_uri", fake_fetch_cover)
    monkeypatch.setattr(render_module, "render_svg_to_png", fake_render_svg_to_png)
    monkeypatch.setattr(plugin, "kwsearch", dummy_matcher)
    monkeypatch.setattr(plugin, "get_runtime_config", lambda: config)

    options = f" --mode {requested_mode}" if requested_mode else ""
    arp = command.parse(f"/kwsearch Morning Dew Reflection{options}")
    assert arp.matched
    with pytest.raises(MatcherFinished):
        await plugin.handle_kwsearch(arp)

    assert dummy_matcher.message == uniseg.UniMessage(
        [uniseg.Image(raw=b"rendered-image")]
    )

    assert cover_calls["url"] == (
        "http://img1.kwcdn.kuwo.cn/star/albumcover/120/s4s64/98/1370027605.jpg"
    )
    assert "data:image/png;base64,AAAA" in render_calls["svg"]
    assert "3:02" in render_calls["svg"]
    assert render_calls["scale"] == 2.0
    assert render_calls["font_files"] == [str(font_path)]
    assert config.kuwo_list_render_mode is original_mode


def test_kw_command_parses_quality_option_after_spaced_keyword() -> None:
    plugin = import_plugin_module()

    result = plugin.kw.command().parse("/kw Morning Dew Reflection -q lossless")

    assert result.matched is True
    assert result.all_matched_args == {
        "keyword": ("Morning", "Dew", "Reflection"),
        "quality": "lossless",
    }


def test_kuwo_commands_block_following_matchers() -> None:
    plugin = import_plugin_module()

    assert plugin.kwsearch.block is True
    assert plugin.kw.block is True
    assert plugin.kwid.block is True


@pytest.mark.asyncio
async def test_kw_command_returns_cover_and_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    utils = import_utils_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 1
        return [build_search_song()]

    async def fake_get_song_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "2000kflac"
        return models.KuwoTrackResource(
            rid=rid,
            format="flac",
            ekey="sample-ekey",
            bitrate=2000,
            duration=242,
            direct_url="http://example.com/song.flac",
            cover_url="http://example.com/cover.jpg",
        )

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "get_song_media", fake_get_song_media)
    monkeypatch.setattr(plugin, "kw", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.TEXT,
            kuwo_track_render_mode=config_module.TrackRenderMode.TEXT,
            kuwo_default_quality="lossless",
        ),
    )

    expected = uniseg.UniMessage(
        [
            uniseg.Image(url="http://example.com/cover.jpg"),
            uniseg.Text(
                "\n"
                + utils.format_track_text(
                    rid="553152678",
                    bitrate=2000,
                    duration=242,
                    direct_url="http://example.com/song.flac",
                    ekey="sample-ekey",
                    title="Morning Dew Reflection.wav",
                    artist="rionos&Kangseoha&Kim Yoon",
                    album="Morning Dew Reflection",
                )
            ),
        ]
    )

    arp = make_arp(keyword=("Morning", "Dew", "Reflection"))

    with pytest.raises(MatcherFinished):
        await plugin.handle_kw(arp)

    assert dummy_matcher.message == expected


@pytest.mark.asyncio
async def test_kw_command_returns_music_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    music_share = import_music_share_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 1
        return [build_search_song()]

    async def fake_get_song_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "320kmp3"
        return models.KuwoTrackResource(
            rid=rid,
            format="mp3",
            bitrate=320,
            duration=242,
            direct_url="http://example.com/song.mp3",
            cover_url="http://example.com/cover.jpg",
        )

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "get_song_media", fake_get_song_media)
    monkeypatch.setattr(plugin, "kw", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.IMAGE,
            kuwo_track_render_mode=config_module.TrackRenderMode.CARD,
            kuwo_default_quality="standard",
        ),
    )

    expected = uniseg.UniMessage(
        [
            music_share.MusicShare(
                kind=music_share.MusicShareKind.KuwoMusic,
                url="http://example.com/song.mp3",
                audio="http://example.com/song.mp3",
                title="Morning Dew Reflection.wav",
                content="rionos&Kangseoha&Kim Yoon | Morning Dew Reflection",
                thumbnail="http://example.com/cover.jpg",
            )
        ]
    )

    arp = make_arp(keyword=("Morning", "Dew", "Reflection"), quality="exhigh")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kw(arp)

    assert dummy_matcher.message == expected


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("detail_state", ["available", "missing", "network_error"])
async def test_kw_card_uses_kwid_detail_cover_or_falls_back_to_search(
    monkeypatch: pytest.MonkeyPatch, detail_state: str
) -> None:
    plugin = import_plugin_module()
    config = import_config_module()
    source = importlib.import_module("nonebot_plugin_kuwo.data_source")
    kw_arp = plugin.kw.command().parse("/kw otherside")
    kwid_arp = plugin.kwid.command().parse("/kwid 652507745")
    assert kw_arp.matched and kwid_arp.matched
    by_keyword = DummyMatcher()
    by_id = DummyMatcher()
    monkeypatch.setattr(plugin, "kw", by_keyword)
    monkeypatch.setattr(plugin, "kwid", by_id)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config.Config(kuwo_track_render_mode="card"),
    )
    song = {
        "MUSICRID": "MUSIC_652507745",
        "NAME": "Otherside",
        "ARTIST": "Minecraft&Peter Hont",
        "ALBUM": "Minecraft Dungeons II (Original Game Soundtrack)",
        "DURATION": "211",
        "web_albumpic_short": "120/s4s13/34/357706223.jpg",
    }
    detail_cover = "http://img1.kuwo.cn/star/albumcover/120/s4s13/34/357706223.jpg"
    search_cover = (
        "http://img1.kwcdn.kuwo.cn/star/albumcover/120/s4s13/34/357706223.jpg"
    )
    respx.get(source.SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json={"TOTAL": "1", "abslist": [song]})
    )
    respx.get(source.TRACK_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "rid": 652507745,
                    "bitrate": 128,
                    "duration": 211,
                    "format": "mp3",
                    "url": "http://example.com/otherside.mp3",
                },
            },
        )
    )
    route = respx.get(source.DETAIL_API_URL)
    if detail_state == "network_error":
        route.mock(side_effect=httpx.ConnectError("detail unavailable"))
    else:
        route.mock(
            return_value=httpx.Response(
                200,
                json={
                    "errorcode": 0,
                    "result": "ok",
                    "songs": [
                        {
                            "id": 652507745,
                            "name": song["NAME"],
                            "artist": song["ARTIST"],
                            "album": song["ALBUM"],
                            "albumPic": detail_cover
                            if detail_state == "available"
                            else None,
                        }
                    ],
                },
            )
        )
    try:
        with pytest.raises(MatcherFinished):
            await plugin.handle_kw(kw_arp)
        card = by_keyword.message[0]
        assert card.audio == "http://example.com/otherside.mp3"
        if detail_state == "available":
            with pytest.raises(MatcherFinished):
                await plugin.handle_kwid(kwid_arp)
            assert card.thumbnail == by_id.message[0].thumbnail == detail_cover
            assert by_keyword.message == by_id.message
        else:
            assert card.thumbnail == search_cover
    finally:
        await source.close_http_client()


@pytest.mark.asyncio
async def test_kw_command_returns_record_and_forces_standard_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 1
        return [build_search_song()]

    async def fake_get_song_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "128kmp3"
        return models.KuwoTrackResource(
            rid=rid,
            format="mp3",
            bitrate=128,
            duration=242,
            direct_url="http://example.com/song.mp3",
            cover_url="http://example.com/cover.jpg",
        )

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "get_song_media", fake_get_song_media)
    monkeypatch.setattr(plugin, "kw", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.TEXT,
            kuwo_track_render_mode=config_module.TrackRenderMode.RECORD,
            kuwo_default_quality="lossless",
        ),
    )

    arp = make_arp(keyword=("Morning", "Dew", "Reflection"), quality="lossless")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kw(arp)

    assert dummy_matcher.message == uniseg.UniMessage(
        [uniseg.Voice(url="http://example.com/song.mp3")]
    )


@pytest.mark.asyncio
async def test_kw_command_returns_file_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()
    expected_path = Path("C:/tmp/553152678_2000.flac")

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 1
        return [build_search_song()]

    async def fake_get_song_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "2000kflac"
        return models.KuwoTrackResource(
            rid=rid,
            format="flac",
            bitrate=2000,
            duration=242,
            direct_url="http://example.com/song.flac",
            cover_url="http://example.com/cover.jpg",
        )

    async def fake_download_track_file(
        rid: str,
        direct_url: str,
        format_name: str,
        bitrate: int,
        ekey: str | None = None,
    ) -> Path:
        assert rid == "553152678"
        assert direct_url == "http://example.com/song.flac"
        assert format_name == "flac"
        assert bitrate == 2000
        assert ekey is None
        return expected_path

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "get_song_media", fake_get_song_media)
    monkeypatch.setattr(plugin, "download_track_file", fake_download_track_file)
    monkeypatch.setattr(plugin, "kw", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.TEXT,
            kuwo_track_render_mode=config_module.TrackRenderMode.FILE,
            kuwo_default_quality="lossless",
        ),
    )

    arp = make_arp(keyword=("Morning", "Dew", "Reflection"), quality="lossless")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kw(arp)

    assert dummy_matcher.message == uniseg.UniMessage(
        [
            uniseg.File(
                path=expected_path,
                name="[lossless]Morning Dew Reflection - rionos&Kangseoha&Kim Yoon.flac",
            )
        ]
    )


@pytest.mark.asyncio
async def test_kw_command_returns_file_segment_for_mflac_after_decrypt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()
    expected_path = Path("C:/tmp/553152678_20201.flac")

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 1
        return [build_search_song()]

    async def fake_get_song_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "20201kmflac"
        return models.KuwoTrackResource(
            rid=rid,
            format="mflac",
            ekey="sample-ekey",
            bitrate=20201,
            duration=242,
            direct_url="http://example.com/song.mflac",
            cover_url="http://example.com/cover.jpg",
        )

    async def fake_download_track_file(
        rid: str,
        direct_url: str,
        format_name: str,
        bitrate: int,
        ekey: str | None = None,
    ) -> Path:
        assert rid == "553152678"
        assert direct_url == "http://example.com/song.mflac"
        assert format_name == "mflac"
        assert bitrate == 20201
        assert ekey == "sample-ekey"
        return expected_path

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "get_song_media", fake_get_song_media)
    monkeypatch.setattr(plugin, "download_track_file", fake_download_track_file)
    monkeypatch.setattr(plugin, "kw", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.TEXT,
            kuwo_track_render_mode=config_module.TrackRenderMode.FILE,
            kuwo_default_quality="hifi",
        ),
    )

    arp = make_arp(keyword=("Morning", "Dew", "Reflection"), quality="hifi")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kw(arp)

    assert dummy_matcher.message == uniseg.UniMessage(
        [
            uniseg.File(
                path=expected_path,
                name="[hifi]Morning Dew Reflection - rionos&Kangseoha&Kim Yoon.flac",
            )
        ]
    )


@pytest.mark.asyncio
async def test_kwid_command_returns_cover_and_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    utils = import_utils_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()

    async def fake_get_song_detailed_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "128kmp3"
        return models.KuwoDetailedTrackResource(
            rid=rid,
            format="mp3",
            ekey="sample-ekey",
            bitrate=128,
            duration=182,
            direct_url="http://example.com/song.mp3",
            cover_url="http://example.com/album.jpg",
            title="Pocket wo Fukurasete ~Sea, you again~",
            artist="VISUAL ARTS&Key Sounds Label&rionos",
            album="Summer Pockets REFLECTION BLUE Original SoundTrack",
        )

    monkeypatch.setattr(plugin, "get_song_detailed_media", fake_get_song_detailed_media)
    monkeypatch.setattr(plugin, "kwid", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.TEXT,
            kuwo_track_render_mode=config_module.TrackRenderMode.TEXT,
            kuwo_default_quality="standard",
        ),
    )

    expected = uniseg.UniMessage(
        [
            uniseg.Image(url="http://example.com/album.jpg"),
            uniseg.Text(
                "\n"
                + utils.format_track_text(
                    rid="553152678",
                    bitrate=128,
                    duration=182,
                    direct_url="http://example.com/song.mp3",
                    ekey="sample-ekey",
                    title="Pocket wo Fukurasete ~Sea, you again~",
                    artist="VISUAL ARTS&Key Sounds Label&rionos",
                    album="Summer Pockets REFLECTION BLUE Original SoundTrack",
                )
            ),
        ]
    )

    arp = make_arp(rid="MUSIC_553152678")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kwid(arp)

    assert dummy_matcher.message == expected


@pytest.mark.asyncio
async def test_kwid_command_returns_music_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    music_share = import_music_share_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()

    async def fake_get_song_detailed_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "2000kflac"
        return models.KuwoDetailedTrackResource(
            rid=rid,
            format="flac",
            bitrate=2000,
            duration=182,
            direct_url="http://example.com/song-lossless.flac",
            cover_url="http://example.com/album.jpg",
            title="Pocket wo Fukurasete ~Sea, you again~",
            artist="VISUAL ARTS&Key Sounds Label&rionos",
            album="Summer Pockets REFLECTION BLUE Original SoundTrack",
        )

    monkeypatch.setattr(plugin, "get_song_detailed_media", fake_get_song_detailed_media)
    monkeypatch.setattr(plugin, "kwid", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.IMAGE,
            kuwo_track_render_mode=config_module.TrackRenderMode.CARD,
            kuwo_default_quality="standard",
        ),
    )

    expected = uniseg.UniMessage(
        [
            music_share.MusicShare(
                kind=music_share.MusicShareKind.KuwoMusic,
                url="http://example.com/song-lossless.flac",
                audio="http://example.com/song-lossless.flac",
                title="Pocket wo Fukurasete ~Sea, you again~",
                content=(
                    "VISUAL ARTS&Key Sounds Label&rionos | "
                    "Summer Pockets REFLECTION BLUE Original SoundTrack"
                ),
                thumbnail="http://example.com/album.jpg",
            )
        ]
    )

    arp = make_arp(rid="MUSIC_553152678", quality="hifi")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kwid(arp)

    assert dummy_matcher.message == expected


@pytest.mark.asyncio
async def test_kwid_command_returns_record_and_forces_standard_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()

    async def fake_get_song_detailed_media(rid: str, br: str):
        assert rid == "553152678"
        assert br == "128kmp3"
        return models.KuwoDetailedTrackResource(
            rid=rid,
            format="mp3",
            bitrate=128,
            duration=182,
            direct_url="http://example.com/song.mp3",
            cover_url="http://example.com/album.jpg",
            title="Pocket wo Fukurasete ~Sea, you again~",
            artist="VISUAL ARTS&Key Sounds Label&rionos",
            album="Summer Pockets REFLECTION BLUE Original SoundTrack",
        )

    monkeypatch.setattr(plugin, "get_song_detailed_media", fake_get_song_detailed_media)
    monkeypatch.setattr(plugin, "kwid", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.TEXT,
            kuwo_track_render_mode=config_module.TrackRenderMode.RECORD,
            kuwo_default_quality="lossless",
        ),
    )

    arp = make_arp(rid="MUSIC_553152678")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kwid(arp)

    assert dummy_matcher.message == uniseg.UniMessage(
        [uniseg.Voice(url="http://example.com/song.mp3")]
    )


@pytest.mark.asyncio
async def test_kwid_command_returns_file_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()
    expected_path = Path("C:/tmp/320490745_2000.flac")

    async def fake_get_song_detailed_media(rid: str, br: str):
        assert rid == "320490745"
        assert br == "2000kflac"
        return models.KuwoDetailedTrackResource(
            rid=rid,
            format="flac",
            bitrate=2000,
            duration=182,
            direct_url="http://example.com/song.flac",
            cover_url="http://example.com/album.jpg",
            title="Pocket wo Fukurasete ~Sea, you again~",
            artist="VISUAL ARTS&Key Sounds Label&rionos",
            album="Summer Pockets REFLECTION BLUE Original SoundTrack",
        )

    async def fake_download_track_file(
        rid: str,
        direct_url: str,
        format_name: str,
        bitrate: int,
        ekey: str | None = None,
    ) -> Path:
        assert rid == "320490745"
        assert direct_url == "http://example.com/song.flac"
        assert format_name == "flac"
        assert bitrate == 2000
        assert ekey is None
        return expected_path

    monkeypatch.setattr(plugin, "get_song_detailed_media", fake_get_song_detailed_media)
    monkeypatch.setattr(plugin, "download_track_file", fake_download_track_file)
    monkeypatch.setattr(plugin, "kwid", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.TEXT,
            kuwo_track_render_mode=config_module.TrackRenderMode.FILE,
            kuwo_default_quality="lossless",
        ),
    )

    arp = make_arp(rid="320490745")

    with pytest.raises(MatcherFinished):
        await plugin.handle_kwid(arp)

    assert dummy_matcher.message == uniseg.UniMessage(
        [
            uniseg.File(
                path=expected_path,
                name=(
                    "[lossless]Pocket wo Fukurasete ~Sea, you again~ - "
                    "VISUAL ARTS&Key Sounds Label&rionos.flac"
                ),
            )
        ]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("command_name", ["kw", "kwid"])
@pytest.mark.parametrize(
    ("requested_quality", "expected_bitrate"),
    [
        ("standard", "128kmp3"),
        ("exhigh", "320kmp3"),
        ("lossless", "2000kflac"),
        ("hires", "2000kflac"),
        ("hifi", "2000kflac"),
        ("sur", "2000kflac"),
        ("jymaster", "2000kflac"),
    ],
)
async def test_card_commands_apply_quality_cap(
    monkeypatch: pytest.MonkeyPatch,
    command_name: str,
    requested_quality: str,
    expected_bitrate: str,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    dummy_matcher = DummyMatcher()
    command = getattr(plugin, command_name).command()

    async def fake_search(keyword: str, limit: int):
        return [build_search_song()]

    async def fake_get_media(rid: str, br: str):
        assert br == expected_bitrate
        return models.KuwoDetailedTrackResource(
            rid=rid,
            format="flac",
            bitrate=2000,
            duration=182,
            direct_url="http://example.com/song.flac",
        )

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "get_song_media", fake_get_media)
    monkeypatch.setattr(plugin, "get_song_detailed_media", fake_get_media)
    monkeypatch.setattr(plugin, command_name, dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(kuwo_track_render_mode="card"),
    )

    argument = "Morning Dew Reflection" if command_name == "kw" else "553152678"
    arp = command.parse(f"/{command_name} {argument} -q {requested_quality}")
    assert arp.matched
    with pytest.raises(MatcherFinished):
        await getattr(plugin, f"handle_{command_name}")(arp)

    assert dummy_matcher.message[0].audio == "http://example.com/song.flac"


@pytest.mark.asyncio
@pytest.mark.parametrize("command_name", ["kw", "kwid"])
@pytest.mark.parametrize("render_mode", ["text", "file"])
@pytest.mark.parametrize("requested_mode", [None, "text", "file"])
async def test_track_commands_preserve_failure_messages(
    monkeypatch: pytest.MonkeyPatch,
    command_name: str,
    render_mode: str,
    requested_mode: str | None,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    dummy_matcher = DummyMatcher()
    command = getattr(plugin, command_name).command()

    async def fake_search(keyword: str, limit: int):
        return [build_search_song()]

    async def failing_get_media(rid: str, br: str):
        raise plugin.KuwoTrackError("remote failure")

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "get_song_media", failing_get_media)
    monkeypatch.setattr(plugin, "get_song_detailed_media", failing_get_media)
    monkeypatch.setattr(plugin, command_name, dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(kuwo_track_render_mode=render_mode),
    )

    argument = "Morning" if command_name == "kw" else "553152678"
    options = f" -m {requested_mode}" if requested_mode else ""
    arp = command.parse(f"/{command_name} {argument}{options}")
    assert arp.matched
    with pytest.raises(MatcherFinished):
        await getattr(plugin, f"handle_{command_name}")(arp)

    expected = "获取播放链接失败" if command_name == "kw" else "获取歌曲信息失败"
    if (requested_mode or render_mode) == "file":
        expected = "下载歌曲文件失败"
    assert dummy_matcher.message == expected


@pytest.mark.parametrize("command_name", ["kwsearch", "kw搜索", "kw", "kwid"])
@pytest.mark.parametrize("mode_option", ["-m", "--mode"])
@pytest.mark.parametrize("options_first", [False, True])
def test_commands_parse_mode_option(
    command_name: str, mode_option: str, options_first: bool
) -> None:
    plugin = import_plugin_module()
    matcher_name = "kwsearch" if command_name == "kw搜索" else command_name
    argument = "553152678" if command_name == "kwid" else "Morning Dew Reflection"
    mode = "image" if matcher_name == "kwsearch" else "file"
    options = f"{mode_option} {mode}"
    arguments = f"{options} {argument}" if options_first else f"{argument} {options}"

    result = (
        getattr(plugin, matcher_name).command().parse(f"/{command_name} {arguments}")
    )

    assert result.matched, result.error_info
    expected_args = (
        {"rid": argument}
        if command_name == "kwid"
        else {"keyword": ("Morning", "Dew", "Reflection")}
    )
    assert result.all_matched_args == {**expected_args, "mode": mode}


@pytest.mark.parametrize("command_name", ["kw", "kwid"])
@pytest.mark.parametrize("long_options", [False, True])
@pytest.mark.parametrize("options_first", [False, True])
@pytest.mark.parametrize("quality_first", [False, True])
def test_track_commands_parse_mode_with_quality(
    command_name: str, long_options: bool, options_first: bool, quality_first: bool
) -> None:
    plugin = import_plugin_module()
    argument = "553152678" if command_name == "kwid" else "Morning Dew Reflection"
    mode_option = "--mode" if long_options else "-m"
    quality_option = "--quality" if long_options else "-q"
    mode = f"{mode_option} file"
    quality = f"{quality_option} lossless"
    options = f"{quality} {mode}" if quality_first else f"{mode} {quality}"
    arguments = f"{options} {argument}" if options_first else f"{argument} {options}"

    result = (
        getattr(plugin, command_name).command().parse(f"/{command_name} {arguments}")
    )

    assert result.matched, result.error_info
    expected_args = (
        {"rid": argument}
        if command_name == "kwid"
        else {"keyword": ("Morning", "Dew", "Reflection")}
    )
    assert result.all_matched_args == {
        **expected_args,
        "mode": "file",
        "quality": "lossless",
    }


@pytest.mark.parametrize("command_name", ["kwsearch", "kw", "kwid"])
@pytest.mark.parametrize("mode_option", ["-m", "--mode"])
def test_commands_reject_mode_option_without_value(
    command_name: str, mode_option: str
) -> None:
    plugin = import_plugin_module()
    argument = "553152678" if command_name == "kwid" else "Morning Dew Reflection"

    result = (
        getattr(plugin, command_name)
        .command()
        .parse(f"/{command_name} {argument} {mode_option}")
    )

    assert not result.matched


@pytest.mark.asyncio
@pytest.mark.parametrize("command_name", ["kwsearch", "kw", "kwid"])
@pytest.mark.parametrize("unknown_mode", [False, True])
async def test_commands_reject_invalid_mode_before_network_requests(
    monkeypatch: pytest.MonkeyPatch, command_name: str, unknown_mode: bool
) -> None:
    plugin = import_plugin_module()
    config = import_config_module().Config()
    dummy_matcher = DummyMatcher()
    argument = "553152678" if command_name == "kwid" else "Morning Dew Reflection"
    mode = "card" if command_name == "kwsearch" else "image"
    if unknown_mode:
        mode = "unknown"
    arp = (
        getattr(plugin, command_name)
        .command()
        .parse(f"/{command_name} {argument} -m {mode}")
    )
    assert arp.matched
    remote_call = AsyncMock(side_effect=AssertionError("unexpected network request"))
    monkeypatch.setattr(plugin, "search_songs", remote_call)
    monkeypatch.setattr(plugin, "get_song_media", remote_call)
    monkeypatch.setattr(plugin, "get_song_detailed_media", remote_call)
    monkeypatch.setattr(plugin, "get_runtime_config", lambda: config)
    monkeypatch.setattr(plugin, command_name, dummy_matcher)

    with pytest.raises(MatcherFinished):
        await getattr(plugin, f"handle_{command_name}")(arp)

    expected = (
        "搜索列表输出支持：text、image"
        if command_name == "kwsearch"
        else "单曲输出支持：text、card、record、file"
    )
    assert dummy_matcher.message == expected
    remote_call.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("command_name", ["kw", "kwid"])
@pytest.mark.parametrize(
    ("mode", "expected_bitrate", "effective_quality"),
    [
        ("text", "4000kflac", "hires"),
        ("card", "2000kflac", "lossless"),
        ("record", "128kmp3", "standard"),
        ("file", "4000kflac", "hires"),
    ],
)
async def test_track_commands_override_mode_and_preserve_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command_name: str,
    mode: str,
    expected_bitrate: str,
    effective_quality: str,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    uniseg = import_uniseg_module()
    music_share = import_music_share_module()
    default_mode = "file" if mode == "record" else "record"
    config = config_module.Config(
        kuwo_track_render_mode=default_mode, kuwo_default_quality="hires"
    )
    original_list_mode = config.kuwo_list_render_mode
    dummy_matcher = DummyMatcher()
    argument = "553152678" if command_name == "kwid" else "Morning Dew Reflection"
    arp = (
        getattr(plugin, command_name)
        .command()
        .parse(f"/{command_name} {argument} --mode {mode.upper()} -q hires")
    )
    assert arp.matched
    format_name = "mp3" if mode == "record" else "flac"
    direct_url = f"http://example.com/song.{format_name}"
    media = models.KuwoDetailedTrackResource(
        rid="553152678",
        format=format_name,
        bitrate=int(expected_bitrate.split("k")[0]),
        duration=182,
        direct_url=direct_url,
        cover_url="http://example.com/cover.jpg",
        title="Morning Dew Reflection.wav",
        artist="rionos&Kangseoha&Kim Yoon",
        album="Morning Dew Reflection",
    )
    get_media = AsyncMock(return_value=media)
    file_path = tmp_path / "song.flac"
    download = AsyncMock(return_value=file_path)
    monkeypatch.setattr(
        plugin, "search_songs", AsyncMock(return_value=[build_search_song()])
    )
    monkeypatch.setattr(plugin, "get_song_media", get_media)
    monkeypatch.setattr(plugin, "get_song_detailed_media", get_media)
    monkeypatch.setattr(plugin, "download_track_file", download)
    monkeypatch.setattr(plugin, "get_runtime_config", lambda: config)
    monkeypatch.setattr(plugin, command_name, dummy_matcher)

    with pytest.raises(MatcherFinished):
        await getattr(plugin, f"handle_{command_name}")(arp)

    get_media.assert_awaited_once_with("553152678", expected_bitrate)
    message = dummy_matcher.message
    if mode == "text":
        assert isinstance(message[0], uniseg.Image)
        assert direct_url in str(message)
    elif mode == "card":
        assert isinstance(message[0], music_share.MusicShare)
        assert message[0].kind is music_share.MusicShareKind.KuwoMusic
        assert message[0].id is None
        assert message[0].audio == direct_url
    elif mode == "record":
        assert message == uniseg.UniMessage([uniseg.Voice(url=direct_url)])
    else:
        download.assert_awaited_once_with(
            rid=media.rid,
            direct_url=direct_url,
            format_name="flac",
            bitrate=4000,
            ekey=None,
        )
        assert message == uniseg.UniMessage(
            [
                uniseg.File(
                    path=file_path,
                    name=(
                        f"[{effective_quality}]Morning Dew Reflection - "
                        "rionos&Kangseoha&Kim Yoon.flac"
                    ),
                )
            ]
        )
    if mode != "file":
        download.assert_not_awaited()
    assert config.kuwo_track_render_mode.value == default_mode
    assert config.kuwo_list_render_mode is original_list_mode
    assert config.kuwo_default_quality is config_module.KuwoQuality.HIRES


@pytest.mark.asyncio
async def test_concurrent_mode_overrides_leave_next_command_using_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    models = import_models_module()
    uniseg = import_uniseg_module()
    music_share = import_music_share_module()
    config = config_module.Config(
        kuwo_track_render_mode="file", kuwo_default_quality="hires"
    )
    command = plugin.kwid.command()
    record_arp = command.parse("/kwid 1 -m record")
    card_arp = command.parse("/kwid 2 -m card")
    default_arp = command.parse("/kwid 3")
    assert record_arp.matched and card_arp.matched and default_arp.matched
    ready = asyncio.Event()
    requests: dict[str, str] = {}

    async def get_media(rid: str, br: str):
        requests[rid] = br
        if len(requests) == 2:
            ready.set()
        await ready.wait()
        format_name = "mp3" if rid == "1" else "flac"
        return models.KuwoDetailedTrackResource(
            rid=rid,
            format=format_name,
            bitrate=int(br.split("k")[0]),
            duration=182,
            direct_url=f"http://example.com/{rid}.{format_name}",
        )

    dummy_matcher = DummyMatcher()
    finish = AsyncMock(side_effect=MatcherFinished)
    file_path = tmp_path / "default.flac"
    download = AsyncMock(return_value=file_path)
    monkeypatch.setattr(plugin, "get_runtime_config", lambda: config)
    monkeypatch.setattr(plugin, "get_song_detailed_media", get_media)
    monkeypatch.setattr(plugin, "download_track_file", download)
    monkeypatch.setattr(plugin, "kwid", dummy_matcher)
    monkeypatch.setattr(dummy_matcher, "finish", finish)

    outcomes = await asyncio.wait_for(
        asyncio.gather(
            plugin.handle_kwid(record_arp),
            plugin.handle_kwid(card_arp),
            return_exceptions=True,
        ),
        timeout=5,
    )

    assert all(isinstance(outcome, MatcherFinished) for outcome in outcomes)
    assert requests == {"1": "128kmp3", "2": "2000kflac"}
    messages = [call.args[0][0] for call in finish.call_args_list]
    assert any(
        isinstance(message, uniseg.Voice) and message.url == "http://example.com/1.mp3"
        for message in messages
    )
    assert any(
        isinstance(message, music_share.MusicShare)
        and message.audio == "http://example.com/2.flac"
        for message in messages
    )
    download.assert_not_awaited()

    with pytest.raises(MatcherFinished):
        await plugin.handle_kwid(default_arp)

    assert requests["3"] == "4000kflac"
    download.assert_awaited_once()
    assert finish.call_args.args[0][0].path == file_path
    assert config.kuwo_track_render_mode is config_module.TrackRenderMode.FILE
    assert config.kuwo_list_render_mode is config_module.ListRenderMode.TEXT
    assert config.kuwo_default_quality is config_module.KuwoQuality.HIRES


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("command_name", ["kw", "kwid"])
async def test_file_mode_option_reuses_download_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command_name: str
) -> None:
    plugin = import_plugin_module()
    files = importlib.import_module("nonebot_plugin_kuwo.files")
    models = import_models_module()
    config = import_config_module().Config()
    dummy_matcher = DummyMatcher()
    argument = "553152678" if command_name == "kwid" else "Morning Dew Reflection"
    arp = (
        getattr(plugin, command_name)
        .command()
        .parse(f"/{command_name} {argument} -m file")
    )
    assert arp.matched
    media = models.KuwoDetailedTrackResource(
        rid="553152678",
        format="mp3",
        bitrate=128,
        duration=182,
        direct_url="http://example.com/song.mp3",
        title="Morning Dew Reflection.wav",
        artist="rionos&Kangseoha&Kim Yoon",
    )
    monkeypatch.setattr(
        plugin, "search_songs", AsyncMock(return_value=[build_search_song()])
    )
    monkeypatch.setattr(plugin, "get_song_media", AsyncMock(return_value=media))
    monkeypatch.setattr(
        plugin, "get_song_detailed_media", AsyncMock(return_value=media)
    )
    monkeypatch.setattr(plugin, "get_runtime_config", lambda: config)
    monkeypatch.setattr(plugin, command_name, dummy_matcher)
    monkeypatch.setattr(files, "get_runtime_config", lambda: config)
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(files, "_track_file_operation_lock", asyncio.Lock())
    route = respx.get(media.direct_url).mock(
        return_value=httpx.Response(200, content=b"audio-bytes")
    )

    try:
        for _ in range(2):
            with pytest.raises(MatcherFinished):
                await getattr(plugin, f"handle_{command_name}")(arp)

            assert dummy_matcher.message[0].path == tmp_path / "553152678_128.mp3"
        assert route.call_count == 1
        assert (tmp_path / "553152678_128.mp3").read_bytes() == b"audio-bytes"
    finally:
        await plugin.close_http_client()


@pytest.mark.asyncio
@pytest.mark.parametrize("command_name", ["kwsearch", "kw"])
@pytest.mark.parametrize(
    ("error_name", "expected"),
    [
        ("KuwoSearchNetworkError", "搜索服务暂时不可用，请稍后再试"),
        ("KuwoSearchResponseError", "搜索结果解析失败"),
    ],
)
async def test_mode_option_preserves_search_error_messages(
    monkeypatch: pytest.MonkeyPatch,
    command_name: str,
    error_name: str,
    expected: str,
) -> None:
    plugin = import_plugin_module()
    config = import_config_module().Config()
    dummy_matcher = DummyMatcher()
    mode = "image" if command_name == "kwsearch" else "card"
    arp = (
        getattr(plugin, command_name)
        .command()
        .parse(f"/{command_name} Morning Dew Reflection -m {mode}")
    )
    assert arp.matched
    search = AsyncMock(side_effect=getattr(plugin, error_name)("remote failure"))
    monkeypatch.setattr(plugin, "search_songs", search)
    monkeypatch.setattr(plugin, "get_runtime_config", lambda: config)
    monkeypatch.setattr(plugin, command_name, dummy_matcher)

    with pytest.raises(MatcherFinished):
        await getattr(plugin, f"handle_{command_name}")(arp)

    assert dummy_matcher.message == expected
