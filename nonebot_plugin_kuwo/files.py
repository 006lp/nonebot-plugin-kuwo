from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from nonebot import logger, require

require("nonebot_plugin_localstore")

from nonebot_plugin_localstore import get_plugin_cache_dir

from .config import get_runtime_config
from .data_source import (
    KuwoTrackNetworkError,
    KuwoTrackResponseError,
    KuwoUnsupportedFormatError,
    get_http_client,
)
from .qmc import decrypt_mflac_file
from .utils import normalize_musicrid, wait_for_completion

TRACK_FILE_DOWNLOAD_HEADERS = {
    "User-Agent": "Lavf/57.83.100",
    "Accept-Encoding": "identity",
}
SUPPORTED_TRACK_FILE_FORMATS = {"mp3", "flac", "aac", "ogg", "wav"}
TRACK_CACHE_TEMP_SUFFIX = ".part"
MAX_TRACK_FILE_BYTES = 512 * 1024 * 1024
SECONDS_PER_DAY = 24 * 60 * 60

_track_file_operation_lock = asyncio.Lock()
_track_file_cache_dir: Path | None = None


def get_track_file_cache_dir() -> Path:
    global _track_file_cache_dir
    if _track_file_cache_dir is None:
        _track_file_cache_dir = get_plugin_cache_dir() / "tracks"
        logger.debug(
            "Resolved kuwo track cache directory: path={}",
            str(_track_file_cache_dir),
        )
    return _track_file_cache_dir


def initialize_track_cache_dir() -> Path:
    track_file_cache_dir = get_track_file_cache_dir()
    if not track_file_cache_dir.exists():
        track_file_cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(
            "Initialized kuwo track cache directory: path={}",
            str(track_file_cache_dir),
        )
    return track_file_cache_dir


def _get_track_file_temp_path(file_path: Path) -> Path:
    return file_path.with_name(f"{file_path.name}{TRACK_CACHE_TEMP_SUFFIX}")


def _delete_track_cache_path(file_path: Path, reason: str) -> None:
    try:
        file_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "Failed to delete kuwo track cache file: path={}, reason={}, error={}",
            str(file_path),
            reason,
            str(exc),
        )
        return

    logger.info(
        "Deleted kuwo track cache file: path={}, reason={}",
        str(file_path),
        reason,
    )


def _touch_track_cache_path(file_path: Path) -> None:
    try:
        os.utime(file_path, None)
    except OSError as exc:
        logger.debug(
            "Failed to refresh kuwo track cache timestamp: path={}, error={}",
            str(file_path),
            str(exc),
        )


def _cleanup_track_file_cache(
    track_file_cache_dir: Path,
    *,
    keep_paths: set[Path] | None = None,
) -> None:
    config = get_runtime_config()
    retention_days = config.kuwo_track_cache_retention_days
    max_size_mb = config.kuwo_track_cache_max_size_mb
    if retention_days <= 0 and max_size_mb <= 0:
        return

    keep = {path.resolve() for path in keep_paths or set()}
    kept_size = 0
    candidates: list[tuple[Path, int, float]] = []
    expire_before = (
        time.time() - (retention_days * SECONDS_PER_DAY) if retention_days > 0 else None
    )

    for file_path in track_file_cache_dir.iterdir():
        if file_path.is_symlink() or not file_path.is_file():
            continue

        try:
            resolved_path = file_path.resolve()
            stat = file_path.stat()
        except OSError as exc:
            logger.debug(
                "Failed to inspect kuwo track cache file: path={}, error={}",
                str(file_path),
                str(exc),
            )
            continue

        if stat.st_size <= 0:
            if resolved_path not in keep:
                _delete_track_cache_path(file_path, "empty cache file")
            continue

        if file_path.suffix == TRACK_CACHE_TEMP_SUFFIX:
            continue

        if resolved_path in keep:
            kept_size += stat.st_size
            continue

        if expire_before is not None and stat.st_mtime < expire_before:
            _delete_track_cache_path(
                file_path,
                f"expired cache file older than {retention_days} day(s)",
            )
            continue

        candidates.append((file_path, stat.st_size, stat.st_mtime))

    if max_size_mb <= 0:
        return

    max_size_bytes = max_size_mb * 1024 * 1024
    total_size = kept_size + sum(size for _, size, _ in candidates)
    if total_size <= max_size_bytes:
        return

    for file_path, file_size, _ in sorted(candidates, key=lambda item: item[2]):
        _delete_track_cache_path(file_path, f"cache size exceeds {max_size_mb}MB")
        total_size -= file_size
        if total_size <= max_size_bytes:
            break

    if total_size > max_size_bytes and keep:
        logger.warning(
            "Kuwo track cache still exceeds limit after cleanup: current_size_mb={}, "
            "limit_mb={}",
            round(total_size / 1024 / 1024, 2),
            max_size_mb,
        )


def resolve_track_file_extension(direct_url: str, format_name: str) -> str:
    extension = Path(urlparse(direct_url).path).suffix.lstrip(".").lower()
    if extension:
        return extension
    return format_name.strip().lower()


async def _download_file_to_path(direct_url: str, file_path: Path) -> Path:
    temp_path = _get_track_file_temp_path(file_path)
    try:
        temp_path.unlink(missing_ok=True)
        client = await get_http_client()
        async with client.stream(
            "GET", direct_url, headers=TRACK_FILE_DOWNLOAD_HEADERS
        ) as response:
            response.raise_for_status()
            encoding = (
                response.headers.get("content-encoding", "identity").strip().lower()
            )
            if encoding not in {"", "identity"}:
                raise KuwoTrackResponseError("compressed track response is unsupported")
            content_length = response.headers.get("content-length")
            if (
                content_length
                and content_length.isdecimal()
                and int(content_length) > MAX_TRACK_FILE_BYTES
            ):
                raise KuwoTrackResponseError("track file exceeds the 512 MiB limit")
            downloaded = 0
            with temp_path.open("xb") as file:
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    downloaded += len(chunk)
                    if downloaded > MAX_TRACK_FILE_BYTES:
                        raise KuwoTrackResponseError(
                            "track file exceeds the 512 MiB limit"
                        )
                    file.write(chunk)
        if downloaded == 0:
            raise KuwoTrackResponseError("track file download is empty")
        temp_path.replace(file_path)
        return file_path
    except httpx.HTTPError as exc:
        raise KuwoTrackNetworkError("track file download failed") from exc
    except OSError as exc:
        raise KuwoTrackResponseError("track file write or finalize failed") from exc
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(
                "Failed to remove partial track download: path={}, error={}",
                temp_path,
                exc,
            )


def _track_cache_path(cache_dir: Path, filename: str) -> Path:
    path = cache_dir / filename
    resolved = path.resolve()
    if path.is_symlink() or resolved.parent != cache_dir:
        raise KuwoTrackResponseError("track cache path escapes the cache directory")
    return resolved


async def download_track_file(
    rid: str,
    direct_url: str,
    format_name: str,
    bitrate: int,
    ekey: str | None = None,
) -> Path:
    try:
        rid = normalize_musicrid(rid)
    except ValueError as exc:
        raise KuwoTrackResponseError("invalid track file rid") from exc
    if not isinstance(bitrate, int) or bitrate < 0:
        raise KuwoTrackResponseError("invalid track file bitrate")

    async with _track_file_operation_lock:
        extension = resolve_track_file_extension(direct_url, format_name)
        track_file_cache_dir = initialize_track_cache_dir().resolve()

        if extension == "mflac":
            if not ekey:
                raise KuwoTrackResponseError("track file ekey is missing")

            encrypted_path = _track_cache_path(
                track_file_cache_dir, f"{rid}_{bitrate}.mflac"
            )
            decrypted_path = _track_cache_path(
                track_file_cache_dir, f"{rid}_{bitrate}.flac"
            )
            decrypted_temp_path = _get_track_file_temp_path(decrypted_path)
            _cleanup_track_file_cache(
                track_file_cache_dir,
                keep_paths={encrypted_path, decrypted_path},
            )

            if decrypted_path.is_file() and decrypted_path.stat().st_size > 0:
                encrypted_path.unlink(missing_ok=True)
                _touch_track_cache_path(decrypted_path)
                logger.info(
                    "Reusing cached decrypted kuwo track file: rid={}, path={}",
                    rid,
                    str(decrypted_path),
                )
                return decrypted_path

            if not encrypted_path.is_file() or encrypted_path.stat().st_size <= 0:
                logger.info(
                    "Downloading encrypted kuwo track file: rid={}, format={}, path={}",
                    rid,
                    extension,
                    str(encrypted_path),
                )
                await _download_file_to_path(direct_url, encrypted_path)

            decrypted_temp_path.unlink(missing_ok=True)
            try:
                await wait_for_completion(
                    asyncio.to_thread(
                        decrypt_mflac_file, encrypted_path, decrypted_temp_path, ekey
                    )
                )
            except asyncio.CancelledError:
                _delete_track_cache_path(decrypted_temp_path, "cancelled decrypt")
                raise
            except (OSError, ValueError) as exc:
                decrypted_temp_path.unlink(missing_ok=True)
                raise KuwoTrackResponseError("track file decrypt failed") from exc

            if decrypted_temp_path.stat().st_size <= 0:
                decrypted_temp_path.unlink(missing_ok=True)
                raise KuwoTrackResponseError("track file decrypt is empty")

            try:
                decrypted_temp_path.replace(decrypted_path)
            except OSError as exc:
                decrypted_temp_path.unlink(missing_ok=True)
                raise KuwoTrackResponseError("track file finalize failed") from exc
            encrypted_path.unlink(missing_ok=True)
            _cleanup_track_file_cache(
                track_file_cache_dir,
                keep_paths={decrypted_path},
            )
            return decrypted_path

        if extension not in SUPPORTED_TRACK_FILE_FORMATS:
            raise KuwoUnsupportedFormatError(f"unsupported track format: {extension}")

        file_path = _track_cache_path(
            track_file_cache_dir, f"{rid}_{bitrate}.{extension}"
        )
        _cleanup_track_file_cache(track_file_cache_dir, keep_paths={file_path})
        if file_path.is_file() and file_path.stat().st_size > 0:
            _touch_track_cache_path(file_path)
            logger.info(
                "Reusing cached kuwo track file: rid={}, path={}",
                rid,
                str(file_path),
            )
            return file_path

        logger.info(
            "Downloading kuwo track file: rid={}, format={}, path={}",
            rid,
            extension,
            str(file_path),
        )
        downloaded_path = await _download_file_to_path(direct_url, file_path)
        _cleanup_track_file_cache(track_file_cache_dir, keep_paths={downloaded_path})
        return downloaded_path
