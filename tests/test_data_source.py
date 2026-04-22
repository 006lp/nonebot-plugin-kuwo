from __future__ import annotations

import os
from pathlib import Path
import time
from uuid import uuid4

import httpx
import pytest
import respx

from nonebot_plugin_kuwo.config import Config
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


def make_runtime_config(
    *,
    retention_days: int = 1,
    max_size_mb: int = 1024,
) -> Config:
    return Config(
        kuwo_track_cache_retention_days=retention_days,
        kuwo_track_cache_max_size_mb=max_size_mb,
    )


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
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source.get_runtime_config",
        lambda: make_runtime_config(),
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
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source.get_runtime_config",
        lambda: make_runtime_config(),
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
        assert target_path == (tmp_path / "553152678_20201.flac.part").resolve()
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
    assert not (tmp_path / "553152678_20201.mflac").exists()


@pytest.mark.asyncio
async def test_download_track_file_raises_when_mflac_ekey_missing(
    monkeypatch,
) -> None:
    tmp_path = make_workspace_tmp_path("download_track_file_raises_when_mflac_ekey_missing")
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._get_track_file_cache_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source.get_runtime_config",
        lambda: make_runtime_config(),
    )

    with pytest.raises(KuwoTrackResponseError, match="ekey is missing"):
        await download_track_file(
            "553152678",
            "http://example.com/song.mflac",
            "mflac",
            20201,
        )


@pytest.mark.asyncio
async def test_download_track_file_deletes_expired_cache_entries(monkeypatch) -> None:
    tmp_path = make_workspace_tmp_path("download_track_file_deletes_expired_cache_entries")
    expired_path = (tmp_path / "old_2000.flac").resolve()
    expired_path.write_bytes(b"expired")
    expired_at = time.time() - (2 * 24 * 60 * 60)
    os.utime(expired_path, (expired_at, expired_at))

    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._get_track_file_cache_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source.get_runtime_config",
        lambda: make_runtime_config(retention_days=1, max_size_mb=0),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"fresh")
        return file_path

    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._download_file_to_path",
        fake_download_file_to_path,
    )

    file_path = await download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert not expired_path.exists()


@pytest.mark.asyncio
async def test_download_track_file_prunes_cache_by_size_after_download(
    monkeypatch,
) -> None:
    tmp_path = make_workspace_tmp_path(
        "download_track_file_prunes_cache_by_size_after_download"
    )
    oldest_path = (tmp_path / "oldest_2000.flac").resolve()
    older_path = (tmp_path / "older_2000.flac").resolve()
    oldest_path.write_bytes(b"a" * (500 * 1024))
    older_path.write_bytes(b"b" * (400 * 1024))

    now = time.time()
    os.utime(oldest_path, (now - 200, now - 200))
    os.utime(older_path, (now - 100, now - 100))

    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._get_track_file_cache_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source.get_runtime_config",
        lambda: make_runtime_config(retention_days=0, max_size_mb=1),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"c" * (300 * 1024))
        return file_path

    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._download_file_to_path",
        fake_download_file_to_path,
    )

    file_path = await download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert not oldest_path.exists()
    assert older_path.exists()


@pytest.mark.asyncio
async def test_download_track_file_skips_cache_cleanup_when_disabled(
    monkeypatch,
) -> None:
    tmp_path = make_workspace_tmp_path("download_track_file_skips_cache_cleanup_when_disabled")
    old_path = (tmp_path / "old_2000.flac").resolve()
    old_path.write_bytes(b"a" * (700 * 1024))
    old_at = time.time() - (3 * 24 * 60 * 60)
    os.utime(old_path, (old_at, old_at))

    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._get_track_file_cache_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source.get_runtime_config",
        lambda: make_runtime_config(retention_days=0, max_size_mb=0),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"fresh")
        return file_path

    monkeypatch.setattr(
        "nonebot_plugin_kuwo.data_source._download_file_to_path",
        fake_download_file_to_path,
    )

    file_path = await download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert old_path.exists()
