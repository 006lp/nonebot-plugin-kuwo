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
    return importlib.import_module(
        "nonebot_plugin_alconna.builtins.uniseg.music_share"
    )


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
    render_calls: dict[str, str] = {}

    async def fake_search(keyword: str, limit: int):
        assert keyword == "Morning Dew Reflection"
        assert limit == 5
        return [build_search_song(web_albumpic_short="120/s4s64/98/1370027605.jpg")]

    async def fake_html_to_pic(**kwargs) -> bytes:
        render_calls["html"] = kwargs["html"]
        render_calls["template_path"] = kwargs["template_path"]
        return b"rendered-image"

    monkeypatch.setattr(plugin, "search_songs", fake_search)
    monkeypatch.setattr(render_module, "html_to_pic", fake_html_to_pic)
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

    assert (
        "http://img1.kwcdn.kuwo.cn/star/albumcover/120/s4s64/98/1370027605.jpg"
        in render_calls["html"]
    )
    assert render_calls["template_path"].startswith("file://")


def test_kw_command_parses_quality_option_after_spaced_keyword() -> None:
    plugin = import_plugin_module()

    result = plugin.kw.command().parse("/kw Morning Dew Reflection -q lossless")

    assert result.matched is True
    assert result.all_matched_args == {
        "keyword": ("Morning", "Dew", "Reflection"),
        "quality": "lossless",
    }


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
        [uniseg.File(path=expected_path, name=expected_path.name)]
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
        [uniseg.File(path=expected_path, name=expected_path.name)]
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
        [uniseg.File(path=expected_path, name=expected_path.name)]
    )
