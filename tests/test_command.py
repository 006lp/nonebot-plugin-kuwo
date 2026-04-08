from __future__ import annotations

import nonebug
import pytest
from nonebot.adapters.onebot.v11 import Adapter, Bot, PrivateMessageEvent

from nonebot_plugin_kuwo.config import Config, SearchRenderMode
from nonebot_plugin_kuwo.models import KuwoSearchSong


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
            kuwo_search_render_mode=SearchRenderMode.TEXT,
            kuwo_default_quality="128kmp3",
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
