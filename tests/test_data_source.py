from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import respx

from nonebot_plugin_kuwo.data_source import (
    COVER_API_URL,
    DETAIL_API_URL,
    SEARCH_API_URL,
    TRACK_API_URL,
    KuwoSearchResponseError,
    KuwoTrackResponseError,
    close_http_client,
    download_track_file,
    get_song_detailed_media,
    get_song_media,
    resolve_track_file_extension,
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


def make_workspace_tmp_path(name: str) -> Path:
    tmp_path = (Path("tests") / ".tmp" / f"{name}_{uuid4().hex}").resolve()
    tmp_path.mkdir(parents=True, exist_ok=True)
    return tmp_path


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
    assert media.format == "flac"
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
    assert media.format == "flac"
    assert media.bitrate == 2000
    assert media.duration == 242
    assert media.direct_url == "http://example.com/song.flac"
    assert media.title == "ポケットをふくらませて ～Sea, you again～"
    assert media.artist == "VISUAL ARTS&Key Sounds Label&rionos"
    assert media.album == "Summer Pockets REFLECTION BLUE Original SoundTrack"
    assert media.cover_url == "http://example.com/album.jpg"

    await close_http_client()


def test_resolve_track_file_extension_prefers_url_suffix() -> None:
    assert (
        resolve_track_file_extension(
            "http://example.com/track/F000003qKlqV1PVMB8.flac",
            "mflac",
        )
        == "flac"
    )


@pytest.mark.asyncio
@respx.mock
async def test_download_track_file_success(monkeypatch) -> None:
    tmp_path = make_workspace_tmp_path("download_track_file_success")
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._get_track_file_cache_dir",
        lambda: tmp_path,
    )
    route = respx.get("http://example.com/song.flac").mock(
        return_value=httpx.Response(200, content=b"flac-bytes")
    )

    file_path = await download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert route.called
    assert file_path == (tmp_path / "553152678_2000.flac").resolve()
    assert file_path.read_bytes() == b"flac-bytes"

    await close_http_client()


@pytest.mark.asyncio
async def test_download_track_file_decrypts_mflac_to_flac(
    monkeypatch,
) -> None:
    tmp_path = make_workspace_tmp_path("download_track_file_decrypts_mflac")
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._get_track_file_cache_dir",
        lambda: tmp_path,
    )

    async def fake_download_file_to_path(direct_url: str, file_path):
        assert direct_url == "http://example.com/song.mflac"
        file_path.write_bytes(b"encrypted-mflac")
        return file_path

    def fake_decrypt_mflac_file(
        source_path,
        target_path,
        ekey: str,
        chunk_size: int = 65536,
    ):
        assert source_path == (tmp_path / "553152678_20201.mflac").resolve()
        assert target_path == (tmp_path / "553152678_20201.flac").resolve()
        assert ekey == "test-ekey"
        assert chunk_size == 65536
        target_path.write_bytes(b"fLaCdecoded")
        return target_path

    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._download_file_to_path",
        fake_download_file_to_path,
    )
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source.decrypt_mflac_file",
        fake_decrypt_mflac_file,
    )

    file_path = await download_track_file(
        "553152678",
        "http://example.com/song.mflac",
        "mflac",
        20201,
        ekey="test-ekey",
    )

    assert file_path == (tmp_path / "553152678_20201.flac").resolve()
    assert file_path.read_bytes() == b"fLaCdecoded"


@pytest.mark.asyncio
async def test_download_track_file_raises_when_mflac_ekey_missing(
    monkeypatch,
) -> None:
    tmp_path = make_workspace_tmp_path("download_track_file_raises_when_mflac_ekey_missing")
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._get_track_file_cache_dir",
        lambda: tmp_path,
    )

    with pytest.raises(KuwoTrackResponseError, match="ekey is missing"):
        await download_track_file(
            "553152678",
            "http://example.com/song.mflac",
            "mflac",
            20201,
        )
