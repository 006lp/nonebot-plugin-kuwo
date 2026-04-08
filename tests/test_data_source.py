from __future__ import annotations

import httpx
import pytest
import respx

from nonebot_plugin_kuwo.data_source import (
    COVER_API_URL,
    DETAIL_API_URL,
    SEARCH_API_URL,
    TRACK_API_URL,
    KuwoSearchResponseError,
    close_http_client,
    get_song_detailed_media,
    get_song_media,
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

TRACK_RESPONSE = {
    "code": 200,
    "data": {
        "bitrate": 2000,
        "duration": 242,
        "format": "flac",
        "rid": 11713652,
        "url": "http://example.com/song.flac?bitrate$2000&format$flac",
    },
    "locationid": "1",
    "msg": "ok",
}

DETAIL_RESPONSE = {
    "Reason": "",
    "errorcode": 0,
    "errormsg": "MusicPay_OK",
    "result": "ok",
    "songs": [
        {
            "album": "Summer Pockets REFLECTION BLUE Original SoundTrack",
            "albumPic": "http://example.com/album.jpg",
            "artist": "VISUAL ARTS&Key Sounds Label&rionos",
            "duration": 410,
            "id": 320490745,
            "name": "ポケットをふくらませて ～Sea, you again～",
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


@pytest.mark.asyncio
@respx.mock
async def test_get_song_media_returns_direct_url_and_cover() -> None:
    respx.get(TRACK_API_URL).mock(return_value=httpx.Response(200, json=TRACK_RESPONSE))
    respx.get(COVER_API_URL).mock(
        return_value=httpx.Response(200, text="http://example.com/cover.jpg")
    )

    media = await get_song_media("11713652", "2000kflac")

    assert media.rid == "11713652"
    assert media.bitrate == 2000
    assert media.duration == 242
    assert media.direct_url == "http://example.com/song.flac"
    assert media.cover_url == "http://example.com/cover.jpg"

    await close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_get_song_detailed_media_returns_track_detail() -> None:
    respx.get(TRACK_API_URL).mock(return_value=httpx.Response(200, json=TRACK_RESPONSE))
    respx.get(DETAIL_API_URL).mock(
        return_value=httpx.Response(200, json=DETAIL_RESPONSE)
    )

    media = await get_song_detailed_media("320490745", "2000kflac")

    assert media.rid == "320490745"
    assert media.bitrate == 2000
    assert media.duration == 242
    assert media.direct_url == "http://example.com/song.flac"
    assert media.title == "ポケットをふくらませて ～Sea, you again～"
    assert media.artist == "VISUAL ARTS&Key Sounds Label&rionos"
    assert media.album == "Summer Pockets REFLECTION BLUE Original SoundTrack"
    assert media.cover_url == "http://example.com/album.jpg"

    await close_http_client()
