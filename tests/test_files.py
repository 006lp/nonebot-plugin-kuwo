from __future__ import annotations

import asyncio
import gzip
import importlib
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import respx


def import_file_module():
    return importlib.import_module("nonebot_plugin_kuwo.files")


def make_workspace_tmp_path(name: str) -> Path:
    path = (Path("tests") / ".tmp" / f"{name}_{uuid4().hex}").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_runtime_config(*, retention_days: int = 1, max_size_mb: int = 1024):
    config = importlib.import_module("nonebot_plugin_kuwo.config")
    return config.Config(
        kuwo_track_cache_retention_days=retention_days,
        kuwo_track_cache_max_size_mb=max_size_mb,
    )


@pytest.fixture(autouse=True)
async def isolate_file_operations(monkeypatch: pytest.MonkeyPatch):
    files = import_file_module()
    monkeypatch.setattr(files, "_track_file_operation_lock", asyncio.Lock())
    yield
    await importlib.import_module("nonebot_plugin_kuwo.data_source").close_http_client()


def test_resolve_track_file_extension_prefers_url_suffix() -> None:
    files = import_file_module()
    assert (
        files.resolve_track_file_extension(
            "http://example.com/track/F000003qKlqV1PVMB8.flac",
            "mflac",
        )
        == "flac"
    )


@pytest.mark.asyncio
@respx.mock
async def test_download_track_file_success(monkeypatch: pytest.MonkeyPatch) -> None:
    files = import_file_module()
    tmp_path = make_workspace_tmp_path("download_track_file_success")
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        files,
        "get_runtime_config",
        lambda: make_runtime_config(),
    )
    route = respx.get("http://example.com/song.flac").mock(
        return_value=httpx.Response(200, content=b"flac-bytes")
    )

    file_path = await files.download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert route.called
    assert (
        route.calls.last.request.headers["user-agent"]
        == files.TRACK_FILE_DOWNLOAD_HEADERS["User-Agent"]
    )
    assert file_path == (tmp_path / "553152678_2000.flac").resolve()
    assert file_path.read_bytes() == b"flac-bytes"

    await importlib.import_module("nonebot_plugin_kuwo.data_source").close_http_client()


@pytest.mark.asyncio
async def test_download_track_file_decrypts_mflac_to_flac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = import_file_module()
    tmp_path = make_workspace_tmp_path("download_track_file_decrypts_mflac")
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        files,
        "get_runtime_config",
        lambda: make_runtime_config(),
    )

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

    monkeypatch.setattr(files, "_download_file_to_path", fake_download_file_to_path)
    monkeypatch.setattr(files, "decrypt_mflac_file", fake_decrypt_mflac_file)

    file_path = await files.download_track_file(
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = import_file_module()
    tmp_path = make_workspace_tmp_path("download_track_file_missing_mflac_ekey")
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        files,
        "get_runtime_config",
        lambda: make_runtime_config(),
    )

    with pytest.raises(files.KuwoTrackResponseError, match="ekey is missing"):
        await files.download_track_file(
            "553152678",
            "http://example.com/song.mflac",
            "mflac",
            20201,
        )


@pytest.mark.asyncio
async def test_download_track_file_deletes_expired_cache_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = import_file_module()
    tmp_path = make_workspace_tmp_path(
        "download_track_file_deletes_expired_cache_entries"
    )
    expired_path = (tmp_path / "old_2000.flac").resolve()
    expired_path.write_bytes(b"expired")
    expired_at = time.time() - (2 * 24 * 60 * 60)
    os.utime(expired_path, (expired_at, expired_at))

    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        files,
        "get_runtime_config",
        lambda: make_runtime_config(retention_days=1, max_size_mb=0),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"fresh")
        return file_path

    monkeypatch.setattr(files, "_download_file_to_path", fake_download_file_to_path)

    file_path = await files.download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert not expired_path.exists()


@pytest.mark.asyncio
async def test_download_track_file_prunes_cache_by_size_after_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = import_file_module()
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

    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        files,
        "get_runtime_config",
        lambda: make_runtime_config(retention_days=0, max_size_mb=1),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"c" * (300 * 1024))
        return file_path

    monkeypatch.setattr(files, "_download_file_to_path", fake_download_file_to_path)

    file_path = await files.download_track_file(
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = import_file_module()
    tmp_path = make_workspace_tmp_path(
        "download_track_file_skips_cache_cleanup_when_disabled"
    )
    old_path = (tmp_path / "old_2000.flac").resolve()
    old_path.write_bytes(b"a" * (700 * 1024))
    old_at = time.time() - (3 * 24 * 60 * 60)
    os.utime(old_path, (old_at, old_at))

    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    monkeypatch.setattr(
        files,
        "get_runtime_config",
        lambda: make_runtime_config(retention_days=0, max_size_mb=0),
    )

    async def fake_download_file_to_path(direct_url: str, file_path: Path) -> Path:
        file_path.write_bytes(b"fresh")
        return file_path

    monkeypatch.setattr(files, "_download_file_to_path", fake_download_file_to_path)

    file_path = await files.download_track_file(
        "553152678",
        "http://example.com/song.flac",
        "flac",
        2000,
    )

    assert file_path.exists()
    assert old_path.exists()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("declared_size", [True, False])
async def test_download_rejects_oversized_files_and_cleans_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, declared_size: bool
) -> None:
    files = import_file_module()
    monkeypatch.setattr(files, "MAX_TRACK_FILE_BYTES", 8)
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"12345678"
            yield b"9"

    headers = {"content-length": "9"} if declared_size else {}
    respx.get("http://example.com/song.flac").mock(
        return_value=httpx.Response(200, stream=Body(), headers=headers)
    )
    with pytest.raises(files.KuwoTrackResponseError, match="limit"):
        await files.download_track_file(
            "123", "http://example.com/song.flac", "flac", 2000
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("kind", ["empty", "network", "compressed"])
async def test_failed_downloads_never_leave_cached_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    files = import_file_module()
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    route = respx.get("http://example.com/song.flac")
    expected = files.KuwoTrackResponseError
    if kind == "network":
        route.mock(side_effect=httpx.ConnectError("unavailable"))
        expected = files.KuwoTrackNetworkError
    elif kind == "compressed":
        route.mock(
            return_value=httpx.Response(
                200,
                stream=httpx.ByteStream(gzip.compress(b"compressed")),
                headers={"content-encoding": "gzip"},
            )
        )
    else:
        route.mock(return_value=httpx.Response(200, content=b""))
    with pytest.raises(expected):
        await files.download_track_file(
            "123", "http://example.com/song.flac", "flac", 2000
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_cancelled_download_cleans_partial_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = import_file_module()
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    started = asyncio.Event()

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * (64 * 1024)
            started.set()
            await asyncio.Event().wait()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Body())
        )
    ) as client:

        async def get_client():
            return client

        monkeypatch.setattr(files, "get_http_client", get_client)
        task = asyncio.create_task(
            files.download_track_file(
                "123", "http://example.com/song.flac", "flac", 2000
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_download_rejects_path_traversal_before_creating_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = import_file_module()
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(files, "_track_file_cache_dir", cache_dir)
    with pytest.raises(files.KuwoTrackResponseError, match="rid"):
        await files.download_track_file(
            "../outside", "http://example.com/song.flac", "flac", 2000
        )
    assert not cache_dir.exists()


def test_cache_rejects_resolved_paths_outside_its_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = import_file_module()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    target = tmp_path / "outside.flac"
    target.write_bytes(b"keep me")
    monkeypatch.setattr(Path, "resolve", lambda self: target)
    with pytest.raises(files.KuwoTrackResponseError, match="escapes"):
        files._track_cache_path(cache_dir, "123_2000.flac")
    assert target.read_bytes() == b"keep me"


def test_cache_cleanup_skips_symlinks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = import_file_module()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    link = cache_dir / "linked.flac"
    target = tmp_path / "outside.flac"
    target.write_bytes(b"keep me")
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    monkeypatch.setattr(
        files, "get_runtime_config", lambda: make_runtime_config(max_size_mb=1)
    )
    real_resolve = Path.resolve

    def resolve(self, *args, **kwargs):
        if self == link:
            raise AssertionError("cleanup must skip symlinks before resolving them")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    files._cleanup_track_file_cache(cache_dir)
    assert target.read_bytes() == b"keep me"
    assert link.is_symlink()


@pytest.mark.asyncio
async def test_decryption_runs_off_loop_and_holds_lock_when_cancelled_twice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = import_file_module()
    monkeypatch.setattr(files, "_track_file_cache_dir", tmp_path)
    (tmp_path / "123_20201.mflac").write_bytes(b"encrypted")
    started = threading.Event()
    release = threading.Event()
    threads = []

    def decrypt(source: Path, target: Path, ekey: str):
        threads.append(threading.current_thread().name)
        started.set()
        assert release.wait(5)
        target.write_bytes(b"fLaCdecoded")
        return target

    async def download(url: str, target: Path):
        target.write_bytes(b"flac-bytes")
        return target

    monkeypatch.setattr(files, "decrypt_mflac_file", decrypt)
    monkeypatch.setattr(files, "_download_file_to_path", download)
    first = asyncio.create_task(
        files.download_track_file(
            "123", "http://example.com/song.mflac", "mflac", 20201, ekey="key"
        )
    )
    second = None
    try:
        assert await asyncio.to_thread(started.wait, 2)
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()
        second = asyncio.create_task(
            files.download_track_file(
                "456", "http://example.com/song.flac", "flac", 2000
            )
        )
        await asyncio.sleep(0.05)
        assert not first.done()
        assert not second.done()
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (first, second) if task is not None),
            return_exceptions=True,
        )
    assert first.cancelled()
    assert second is not None and second.result().read_bytes() == b"flac-bytes"
    assert len(threads) == 1
    assert threads[0] != threading.main_thread().name
    assert not (tmp_path / "123_20201.flac.part").exists()
    assert not (tmp_path / "123_20201.flac").exists()
