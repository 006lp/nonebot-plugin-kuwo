from __future__ import annotations

import importlib
from pathlib import Path

import pytest
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
async def test_kwsearch_command_returns_text_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    dummy_matcher = DummyMatcher()

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 5
        return [build_search_song()]

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(plugin, "kwsearch", dummy_matcher)
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

    with pytest.raises(MatcherFinished):
        await plugin.handle_kwsearch(make_arp(keyword=("Morning", "Dew", "Reflection")))

    assert dummy_matcher.message == (
        "1. 553152678 Morning Dew Reflection.wav-rionos&Kangseoha&Kim Yoon"
    )


@pytest.mark.asyncio
async def test_kwsearch_command_returns_image_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = import_plugin_module()
    render_module = import_render_module()
    config_module = import_config_module()
    uniseg = import_uniseg_module()
    dummy_matcher = DummyMatcher()
    render_calls: dict[str, object] = {}
    cover_calls: dict[str, object] = {}

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
        return b"rendered-image"

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(render_module, "_fetch_cover_data_uri", fake_fetch_cover)
    monkeypatch.setattr(render_module, "render_svg_to_png", fake_render_svg_to_png)
    monkeypatch.setattr(plugin, "kwsearch", dummy_matcher)
    monkeypatch.setattr(
        plugin,
        "get_runtime_config",
        lambda: config_module.Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=config_module.ListRenderMode.IMAGE,
            kuwo_track_render_mode=config_module.TrackRenderMode.TEXT,
            kuwo_default_quality="standard",
        ),
    )

    with pytest.raises(MatcherFinished):
        await plugin.handle_kwsearch(make_arp(keyword=("Morning", "Dew", "Reflection")))

    assert dummy_matcher.message == uniseg.UniMessage(
        [uniseg.Image(raw=b"rendered-image")]
    )

    assert cover_calls["url"] == (
        "http://img1.kwcdn.kuwo.cn/star/albumcover/120/s4s64/98/1370027605.jpg"
    )
    assert "data:image/png;base64,AAAA" in render_calls["svg"]
    assert "3:02" in render_calls["svg"]
    assert render_calls["scale"] == 2.0


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
                kind=music_share.MusicShareKind.Custom,
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
                kind=music_share.MusicShareKind.Custom,
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
async def test_track_commands_preserve_failure_messages(
    monkeypatch: pytest.MonkeyPatch, command_name: str, render_mode: str
) -> None:
    plugin = import_plugin_module()
    config_module = import_config_module()
    dummy_matcher = DummyMatcher()

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

    arp = make_arp(keyword=("Morning",), rid="553152678")
    with pytest.raises(MatcherFinished):
        await getattr(plugin, f"handle_{command_name}")(arp)

    expected = "获取播放链接失败" if command_name == "kw" else "获取歌曲信息失败"
    if render_mode == "file":
        expected = "下载歌曲文件失败"
    assert dummy_matcher.message == expected
