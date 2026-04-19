from __future__ import annotations

import nonebug
import pytest
from nonebot.adapters.onebot.v11 import (
    Adapter,
    Bot,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)

from nonebot_plugin_kuwo.config import Config, ListRenderMode, TrackRenderMode
from nonebot_plugin_kuwo.models import (
    KuwoDetailedTrackResource,
    KuwoSearchSong,
    KuwoTrackResource,
)
from nonebot_plugin_kuwo.utils import format_track_text


def make_private_event(message: str) -> PrivateMessageEvent:
    return PrivateMessageEvent.model_validate(
        {
            "time": 0,
            "self_id": 1,
            "post_type": "message",
            "sub_type": "friend",
            "user_id": 10001,
            "message_type": "private",
            "message_id": 1,
            "message": message,
            "original_message": message,
            "raw_message": message,
            "font": 0,
            "sender": {
                "user_id": 10001,
                "nickname": "tester",
            },
            "to_me": True,
        }
    )


class MatcherFinished(Exception):
    pass


class DummyMatcher:
    def __init__(self) -> None:
        self.message = None

    async def finish(self, message) -> None:
        self.message = message
        raise MatcherFinished


@pytest.mark.asyncio
async def test_kwsearch_command_returns_text_results(
    app: nonebug.App,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_kuwo

    kwsearch = nonebot_plugin_kuwo.kwsearch

    async def fake_search(keyword: str, limit: int) -> list[KuwoSearchSong]:
        assert keyword == "Morning Dew Reflection"
        assert limit == 5
        return [
            KuwoSearchSong.model_validate(
                {
                    "MUSICRID": "MUSIC_553152678",
                    "NAME": "Morning Dew Reflection.wav",
                    "ARTIST": "rionos&Kangseoha&Kim Yoon",
                    "ALBUM": "Morning Dew Reflection",
                    "DURATION": "182",
                }
            )
        ]

    monkeypatch.setattr(nonebot_plugin_kuwo, "search_songs", fake_search)
    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_runtime_config",
        lambda: Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=ListRenderMode.TEXT,
            kuwo_track_render_mode=TrackRenderMode.TEXT,
            kuwo_default_quality="standard",
        ),
    )

    event = make_private_event("/kwsearch Morning Dew Reflection")

    async with app.test_matcher(kwsearch) as ctx:
        adapter = ctx.create_adapter(base=Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter, self_id="1")
        ctx.receive_event(bot, event)
        ctx.should_call_send(
            event,
            "1. 553152678 Morning Dew Reflection.wav-rionos&Kangseoha&Kim Yoon",
            bot=bot,
        )


@pytest.mark.asyncio
async def test_kwsearch_command_returns_image_results(
    app: nonebug.App,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_kuwo
    import nonebot_plugin_kuwo.render as render_module

    kwsearch = nonebot_plugin_kuwo.kwsearch
    render_calls: dict[str, str] = {}

    async def fake_search(keyword: str, limit: int) -> list[KuwoSearchSong]:
        assert keyword == "Morning Dew Reflection"
        assert limit == 5
        return [
            KuwoSearchSong.model_validate(
                {
                    "MUSICRID": "MUSIC_553152678",
                    "NAME": "Morning Dew Reflection.wav",
                    "ARTIST": "rionos&Kangseoha&Kim Yoon",
                    "ALBUM": "Morning Dew Reflection",
                    "DURATION": "182",
                    "web_albumpic_short": "120/s4s64/98/1370027605.jpg",
                }
            )
        ]

    async def fake_html_to_pic(**kwargs) -> bytes:
        render_calls["html"] = kwargs["html"]
        render_calls["template_path"] = kwargs["template_path"]
        return b"rendered-image"

    monkeypatch.setattr(nonebot_plugin_kuwo, "search_songs", fake_search)
    monkeypatch.setattr(render_module, "_load_html_to_pic", lambda: fake_html_to_pic)
    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_runtime_config",
        lambda: Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=ListRenderMode.IMAGE,
            kuwo_track_render_mode=TrackRenderMode.TEXT,
            kuwo_default_quality="standard",
        ),
    )

    event = make_private_event("/kwsearch Morning Dew Reflection")
    expected = Message([MessageSegment.image(b"rendered-image")])

    async with app.test_matcher(kwsearch) as ctx:
        adapter = ctx.create_adapter(base=Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter, self_id="1")
        ctx.receive_event(bot, event)
        ctx.should_call_send(event, expected, bot=bot)

    assert (
        "http://img1.kwcdn.kuwo.cn/star/albumcover/120/s4s64/98/1370027605.jpg"
        in render_calls["html"]
    )
    assert render_calls["template_path"].startswith("file://")


@pytest.mark.asyncio
async def test_kw_command_returns_cover_and_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_kuwo

    dummy_matcher = DummyMatcher()

    async def fake_search(keyword: str, limit: int) -> list[KuwoSearchSong]:
        assert keyword == "Morning Dew Reflection"
        assert limit == 1
        return [
            KuwoSearchSong.model_validate(
                {
                    "MUSICRID": "MUSIC_553152678",
                    "NAME": "Morning Dew Reflection.wav",
                    "ARTIST": "rionos&Kangseoha&Kim Yoon",
                    "ALBUM": "Morning Dew Reflection",
                    "DURATION": "182",
                }
            )
        ]

    async def fake_get_song_media(rid: str, br: str) -> KuwoTrackResource:
        assert rid == "553152678"
        assert br == "2000kflac"
        return KuwoTrackResource(
            rid=rid,
            bitrate=2000,
            duration=242,
            direct_url="http://example.com/song.flac",
            cover_url="http://example.com/cover.jpg",
        )

    monkeypatch.setattr(nonebot_plugin_kuwo, "search_songs", fake_search)
    monkeypatch.setattr(nonebot_plugin_kuwo, "get_song_media", fake_get_song_media)
    monkeypatch.setattr(nonebot_plugin_kuwo, "kw", dummy_matcher)
    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_runtime_config",
        lambda: Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=ListRenderMode.TEXT,
            kuwo_track_render_mode=TrackRenderMode.TEXT,
            kuwo_default_quality="lossless",
        ),
    )

    expected = Message(
        [
            MessageSegment.image("http://example.com/cover.jpg"),
            MessageSegment.text(
                "\n"
                + format_track_text(
                    rid="553152678",
                    bitrate=2000,
                    duration=242,
                    direct_url="http://example.com/song.flac",
                    title="Morning Dew Reflection.wav",
                    artist="rionos&Kangseoha&Kim Yoon",
                    album="Morning Dew Reflection",
                )
            ),
        ]
    )

    arp = type(
        "Arp", (), {"all_matched_args": {"keyword": ("Morning", "Dew", "Reflection")}}
    )()

    with pytest.raises(MatcherFinished):
        await nonebot_plugin_kuwo.handle_kw(arp)

    assert dummy_matcher.message == expected


@pytest.mark.asyncio
async def test_kw_command_returns_music_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_kuwo

    dummy_matcher = DummyMatcher()

    async def fake_search(keyword: str, limit: int) -> list[KuwoSearchSong]:
        assert keyword == "Morning Dew Reflection"
        assert limit == 1
        return [
            KuwoSearchSong.model_validate(
                {
                    "MUSICRID": "MUSIC_553152678",
                    "NAME": "Morning Dew Reflection.wav",
                    "ARTIST": "rionos&Kangseoha&Kim Yoon",
                    "ALBUM": "Morning Dew Reflection",
                    "DURATION": "182",
                }
            )
        ]

    async def fake_get_song_media(rid: str, br: str) -> KuwoTrackResource:
        assert rid == "553152678"
        assert br == "128kmp3"
        return KuwoTrackResource(
            rid=rid,
            bitrate=128,
            duration=242,
            direct_url="http://example.com/song.mp3",
            cover_url="http://example.com/cover.jpg",
        )

    monkeypatch.setattr(nonebot_plugin_kuwo, "search_songs", fake_search)
    monkeypatch.setattr(nonebot_plugin_kuwo, "get_song_media", fake_get_song_media)
    monkeypatch.setattr(nonebot_plugin_kuwo, "kw", dummy_matcher)
    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_runtime_config",
        lambda: Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=ListRenderMode.IMAGE,
            kuwo_track_render_mode=TrackRenderMode.CARD,
            kuwo_default_quality="standard",
        ),
    )

    expected = Message(
        [
            MessageSegment.music_custom(
                url="http://example.com/song.mp3",
                audio="http://example.com/song.mp3",
                title="Morning Dew Reflection.wav",
                content="rionos&Kangseoha&Kim Yoon | Morning Dew Reflection",
                img_url="http://example.com/cover.jpg",
            )
        ]
    )

    arp = type(
        "Arp", (), {"all_matched_args": {"keyword": ("Morning", "Dew", "Reflection")}}
    )()

    with pytest.raises(MatcherFinished):
        await nonebot_plugin_kuwo.handle_kw(arp)

    assert dummy_matcher.message == expected


@pytest.mark.asyncio
async def test_kwid_command_returns_cover_and_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_kuwo

    dummy_matcher = DummyMatcher()

    async def fake_get_song_detailed_media(
        rid: str, br: str
    ) -> KuwoDetailedTrackResource:
        assert rid == "553152678"
        assert br == "128kmp3"
        return KuwoDetailedTrackResource(
            rid=rid,
            bitrate=128,
            duration=182,
            direct_url="http://example.com/song.mp3",
            cover_url="http://example.com/album.jpg",
            title="Pocket wo Fukurasete ~Sea, you again~",
            artist="VISUAL ARTS&Key Sounds Label&rionos",
            album="Summer Pockets REFLECTION BLUE Original SoundTrack",
        )

    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_song_detailed_media",
        fake_get_song_detailed_media,
    )
    monkeypatch.setattr(nonebot_plugin_kuwo, "kwid", dummy_matcher)
    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_runtime_config",
        lambda: Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=ListRenderMode.TEXT,
            kuwo_track_render_mode=TrackRenderMode.TEXT,
            kuwo_default_quality="standard",
        ),
    )

    expected = Message(
        [
            MessageSegment.image("http://example.com/album.jpg"),
            MessageSegment.text(
                "\n"
                + format_track_text(
                    rid="553152678",
                    bitrate=128,
                    duration=182,
                    direct_url="http://example.com/song.mp3",
                    title="Pocket wo Fukurasete ~Sea, you again~",
                    artist="VISUAL ARTS&Key Sounds Label&rionos",
                    album="Summer Pockets REFLECTION BLUE Original SoundTrack",
                )
            ),
        ]
    )

    arp = type("Arp", (), {"all_matched_args": {"rid": "MUSIC_553152678"}})()

    with pytest.raises(MatcherFinished):
        await nonebot_plugin_kuwo.handle_kwid(arp)

    assert dummy_matcher.message == expected


@pytest.mark.asyncio
async def test_kwid_command_returns_music_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_kuwo

    dummy_matcher = DummyMatcher()

    async def fake_get_song_detailed_media(
        rid: str, br: str
    ) -> KuwoDetailedTrackResource:
        assert rid == "553152678"
        assert br == "128kmp3"
        return KuwoDetailedTrackResource(
            rid=rid,
            bitrate=128,
            duration=182,
            direct_url="http://example.com/song.mp3",
            cover_url="http://example.com/album.jpg",
            title="Pocket wo Fukurasete ~Sea, you again~",
            artist="VISUAL ARTS&Key Sounds Label&rionos",
            album="Summer Pockets REFLECTION BLUE Original SoundTrack",
        )

    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_song_detailed_media",
        fake_get_song_detailed_media,
    )
    monkeypatch.setattr(nonebot_plugin_kuwo, "kwid", dummy_matcher)
    monkeypatch.setattr(
        nonebot_plugin_kuwo,
        "get_runtime_config",
        lambda: Config(
            kuwo_search_limit=5,
            kuwo_list_render_mode=ListRenderMode.IMAGE,
            kuwo_track_render_mode=TrackRenderMode.CARD,
            kuwo_default_quality="standard",
        ),
    )

    expected = Message(
        [
            MessageSegment.music_custom(
                url="http://example.com/song.mp3",
                audio="http://example.com/song.mp3",
                title="Pocket wo Fukurasete ~Sea, you again~",
                content=(
                    "VISUAL ARTS&Key Sounds Label&rionos | "
                    "Summer Pockets REFLECTION BLUE Original SoundTrack"
                ),
                img_url="http://example.com/album.jpg",
            )
        ]
    )

    arp = type("Arp", (), {"all_matched_args": {"rid": "MUSIC_553152678"}})()

    with pytest.raises(MatcherFinished):
        await nonebot_plugin_kuwo.handle_kwid(arp)

    assert dummy_matcher.message == expected
