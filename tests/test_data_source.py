from __future__ import annotations

import importlib
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import respx


def import_config_module():
    return importlib.import_module("nonebot_plugin_kuwo.config")


def import_data_source_module():
    return importlib.import_module("nonebot_plugin_kuwo.data_source")


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
):
    config_module = import_config_module()
    return config_module.Config(
        kuwo_track_cache_retention_days=retention_days,
        kuwo_track_cache_max_size_mb=max_size_mb,
    )


def fake_replace_path(source: Path, target: Path) -> Path:
    target.write_bytes(source.read_bytes())
    return target


@pytest.mark.asyncio
@respx.mock
async def test_search_songs_success() -> None:
    data_source = import_data_source_module()
    route = respx.get(data_source.SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json=SEARCH_RESPONSE)
    )

    songs = await data_source.search_songs("Morning Dew Reflection", 5)

    assert route.called
    assert len(songs) == 1
    assert songs[0].song_id == "553152678"
    assert songs[0].artist == "rionos&Kangseoha&Kim Yoon"

    await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_search_songs_raises_on_invalid_payload() -> None:
    data_source = import_data_source_module()
    respx.get(data_source.SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json={"foo": "bar"})
    )

    with pytest.raises(data_source.KuwoSearchResponseError):
        await data_source.search_songs("Morning Dew Reflection", 5)

    await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_get_song_media_returns_direct_url_and_cover() -> None:
    data_source = import_data_source_module()
    respx.get(data_source.TRACK_API_URL).mock(
        return_value=httpx.Response(200, json=TRACK_RESPONSE)
    )
    respx.get(data_source.COVER_API_URL).mock(
        return_value=httpx.Response(200, text="http://example.com/cover.jpg")
    )

    media = await data_source.get_song_media("11713652", "2000kflac")

    assert media.rid == "11713652"
    assert media.format == "flac"
    assert media.bitrate == 2000
    assert media.duration == 242
    assert media.direct_url == "http://example.com/song.flac"
    assert media.cover_url == "http://example.com/cover.jpg"

    await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_get_song_detailed_media_returns_track_detail() -> None:
    data_source = import_data_source_module()
    respx.get(data_source.TRACK_API_URL).mock(
        return_value=httpx.Response(200, json=TRACK_RESPONSE)
    )
    respx.get(data_source.DETAIL_API_URL).mock(
        return_value=httpx.Response(200, json=DETAIL_RESPONSE)
    )

    media = await data_source.get_song_detailed_media("320490745", "2000kflac")

    assert media.rid == "320490745"
    assert media.format == "flac"
    assert media.bitrate == 2000
    assert media.duration == 242
    assert media.direct_url == "http://example.com/song.flac"
    assert media.title == "ポケットをふくらませて ～Sea, you again～"
    assert media.artist == "VISUAL ARTS&Key Sounds Label&rionos"
    assert media.album == "Summer Pockets REFLECTION BLUE Original SoundTrack"
    assert media.cover_url == "http://example.com/album.jpg"

    await data_source.close_http_client()


def test_resolve_track_file_extension_prefers_url_suffix() -> None:
    data_source = import_data_source_module()
    assert (
        data_source.resolve_track_file_extension(
            "http://example.com/track/F000003qKlqV1PVMB8.flac",
            "mflac",
        )
        == "flac"
    )


@pytest.mark.asyncio
@respx.mock
async def test_download_track_file_success(monkeypatch: pytest.MonkeyPatch) -> None:
    data_source = import_data_source_module()
    tmp_path = make_workspace_tmp_path("download_track_file_success")
    monkeypatch.setattr(data_source, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        data_source,
        "get_runtime_config",
        lambda: make_runtime_config(),
    )
    monkeypatch.setattr(data_source, "_remove_path", lambda path: None)
    monkeypatch.setattr(data_source, "_replace_path", fake_replace_path)
    route = respx.get("http://example.com/song.flac").mock(
        return_value=httpx.Response(200, content=b"flac-bytes")
    )

    file_path = await data_source.download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert route.called
    assert file_path == (tmp_path / "553152678_2000.flac").resolve()
    assert file_path.read_bytes() == b"flac-bytes"

    await data_source.close_http_client()


@pytest.mark.asyncio
async def test_download_track_file_decrypts_mflac_to_flac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_source = import_data_source_module()
    tmp_path = make_workspace_tmp_path("download_track_file_decrypts_mflac")
    removed_paths: list[Path] = []
    monkeypatch.setattr(data_source, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        data_source,
        "get_runtime_config",
        lambda: make_runtime_config(),
    )
    monkeypatch.setattr(data_source, "_remove_path", lambda path: removed_paths.append(path))
    monkeypatch.setattr(data_source, "_replace_path", fake_replace_path)

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        assert direct_url == "http://example.com/song.mflac"
        file_path.write_bytes(b"encrypted-mflac")
        return file_path

    def fake_decrypt_mflac_file(
        source_path: Path,
        target_path: Path,
        ekey: str,
        chunk_size: int = 65536,
    ) -> Path:
        assert source_path == (tmp_path / "553152678_20201.mflac").resolve()
        assert target_path == (tmp_path / "553152678_20201.flac.part").resolve()
        assert ekey == "test-ekey"
        assert chunk_size == 65536
        target_path.write_bytes(b"fLaCdecoded")
        return target_path

    monkeypatch.setattr(data_source, "_download_file_to_path", fake_download_file_to_path)
    monkeypatch.setattr(data_source, "decrypt_mflac_file", fake_decrypt_mflac_file)

    file_path = await data_source.download_track_file(
        "553152678",
        "http://example.com/song.mflac",
        "mflac",
        20201,
        ekey="test-ekey",
    )

    assert file_path == (tmp_path / "553152678_20201.flac").resolve()
    assert file_path.read_bytes() == b"fLaCdecoded"
    assert (tmp_path / "553152678_20201.mflac").resolve() in removed_paths


@pytest.mark.asyncio
async def test_download_track_file_raises_when_mflac_ekey_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_source = import_data_source_module()
    tmp_path = make_workspace_tmp_path("download_track_file_missing_mflac_ekey")
    monkeypatch.setattr(data_source, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        data_source,
        "get_runtime_config",
        lambda: make_runtime_config(),
    )

    with pytest.raises(data_source.KuwoTrackResponseError, match="ekey is missing"):
        await data_source.download_track_file(
            "553152678",
            "http://example.com/song.mflac",
            "mflac",
            20201,
        )


@pytest.mark.asyncio
async def test_download_track_file_deletes_expired_cache_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_source = import_data_source_module()
    tmp_path = make_workspace_tmp_path("download_track_file_deletes_expired_cache_entries")
    deleted_paths: list[Path] = []
    expired_path = (tmp_path / "old_2000.flac").resolve()
    expired_path.write_bytes(b"expired")
    expired_at = time.time() - (2 * 24 * 60 * 60)
    os.utime(expired_path, (expired_at, expired_at))

    monkeypatch.setattr(data_source, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        data_source,
        "get_runtime_config",
        lambda: make_runtime_config(retention_days=1, max_size_mb=0),
    )
    monkeypatch.setattr(
        data_source,
        "_delete_track_cache_path",
        lambda path, reason: deleted_paths.append(path.resolve()),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"fresh")
        return file_path

    monkeypatch.setattr(data_source, "_download_file_to_path", fake_download_file_to_path)

    file_path = await data_source.download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert expired_path in deleted_paths


@pytest.mark.asyncio
async def test_download_track_file_prunes_cache_by_size_after_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_source = import_data_source_module()
    tmp_path = make_workspace_tmp_path(
        "download_track_file_prunes_cache_by_size_after_download"
    )
    deleted_paths: list[Path] = []
    oldest_path = (tmp_path / "oldest_2000.flac").resolve()
    older_path = (tmp_path / "older_2000.flac").resolve()
    oldest_path.write_bytes(b"a" * (500 * 1024))
    older_path.write_bytes(b"b" * (400 * 1024))

    now = time.time()
    os.utime(oldest_path, (now - 200, now - 200))
    os.utime(older_path, (now - 100, now - 100))

    monkeypatch.setattr(data_source, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        data_source,
        "get_runtime_config",
        lambda: make_runtime_config(retention_days=0, max_size_mb=1),
    )
    monkeypatch.setattr(
        data_source,
        "_delete_track_cache_path",
        lambda path, reason: deleted_paths.append(path.resolve()),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"c" * (300 * 1024))
        return file_path

    monkeypatch.setattr(data_source, "_download_file_to_path", fake_download_file_to_path)

    file_path = await data_source.download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert oldest_path in deleted_paths
    assert older_path not in deleted_paths


@pytest.mark.asyncio
async def test_download_track_file_skips_cache_cleanup_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_source = import_data_source_module()
    tmp_path = make_workspace_tmp_path("download_track_file_skips_cache_cleanup_when_disabled")
    deleted_paths: list[Path] = []
    old_path = (tmp_path / "old_2000.flac").resolve()
    old_path.write_bytes(b"a" * (700 * 1024))
    old_at = time.time() - (3 * 24 * 60 * 60)
    os.utime(old_path, (old_at, old_at))

    monkeypatch.setattr(data_source, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        data_source,
        "get_runtime_config",
        lambda: make_runtime_config(retention_days=0, max_size_mb=0),
    )
    monkeypatch.setattr(
        data_source,
        "_delete_track_cache_path",
        lambda path, reason: deleted_paths.append(path.resolve()),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"fresh")
        return file_path

    monkeypatch.setattr(data_source, "_download_file_to_path", fake_download_file_to_path)

    file_path = await data_source.download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert old_path.exists()
    assert not deleted_paths
