from __future__ import annotations

import httpx
import pytest
import respx

from nonebot_plugin_kuwo.data_source import (
    SEARCH_API_URL,
    KuwoSearchResponseError,
    close_http_client,
    search_songs,
)

SEARCH_RESPONSE = {
    "TOTAL": "1",
    "abslist": [
        {
            "MUSICRID": "MUSIC_553152678",
            "NAME": "Morning Dew Reflection.wav",
            "ARTIST": "rionos&Kangseoha&Kim Yoon",
            "ALBUM": "Morning Dew Reflection",
            "DURATION": "182",
        }
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_search_songs_success() -> None:
    route = respx.get(SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json=SEARCH_RESPONSE)
    )

    songs = await search_songs("Morning Dew Reflection", 5)

    assert route.called
    assert len(songs) == 1
    assert songs[0].song_id == "553152678"
    assert songs[0].artist == "rionos&Kangseoha&Kim Yoon"

    await close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_search_songs_raises_on_invalid_payload() -> None:
    respx.get(SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json={"foo": "bar"})
    )

    with pytest.raises(KuwoSearchResponseError):
        await search_songs("Morning Dew Reflection", 5)

    await close_http_client()
