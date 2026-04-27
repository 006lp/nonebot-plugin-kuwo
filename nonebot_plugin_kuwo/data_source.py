# ruff: noqa: E402
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from nonebot import logger, require
from nonebot.compat import type_validate_python
from pydantic import ValidationError

require("nonebot_plugin_localstore")

from nonebot_plugin_localstore import get_plugin_cache_dir

from .config import get_runtime_config
from .models import (
    KuwoDetailedTrackResource,
    KuwoSearchResponse,
    KuwoSearchSong,
    KuwoTrackDetail,
    KuwoTrackDetailResponse,
    KuwoTrackLinkData,
    KuwoTrackLinkResponse,
    KuwoTrackResource,
)
from .qmc import decrypt_mflac_file

SEARCH_API_URL = "http://search.kuwo.cn/r.s"
TRACK_API_URL = "https://nmobi.kuwo.cn/mobi.s"
COVER_API_URL = "http://artistpicserver.kuwo.cn/pic.web"
DETAIL_API_URL = "http://musicpay.kuwo.cn/music.pay"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
SUPPORTED_TRACK_FILE_FORMATS = {"mp3", "flac", "aac", "ogg", "wav"}
TRACK_CACHE_TEMP_SUFFIX = ".part"
SECONDS_PER_DAY = 24 * 60 * 60

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()
_track_file_operation_lock = asyncio.Lock()
_track_file_cache_dir: Path | None = None


class KuwoSearchError(Exception):
    """Base exception for Kuwo search failures."""


class KuwoSearchNetworkError(KuwoSearchError):
    """Raised when the remote search service is unavailable."""


class KuwoSearchResponseError(KuwoSearchError):
    """Raised when the remote response cannot be parsed."""


class KuwoTrackError(Exception):
    """Base exception for track resource failures."""


class KuwoTrackNetworkError(KuwoTrackError):
    """Raised when the remote track service is unavailable."""


class KuwoTrackResponseError(KuwoTrackError):
    """Raised when the remote track response cannot be parsed."""


class KuwoUnsupportedFormatError(KuwoTrackError):
    """Raised when the track format cannot be sent as a playable file yet."""


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


async def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    headers={"X-Forwarded-For": "49.7.250.26"},
                )
    return _client


async def initialize_http_client() -> None:
    await get_http_client()


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def search_songs(keyword: str, limit: int) -> list[KuwoSearchSong]:
    client = await get_http_client()
    params = {
        "allpay": 1,
        "all": keyword,
        "pn": 0,
        "rn": limit,
        "vipver": 1,
        "show_copyright_off": 1,
        "correct": 1,
        "ft": "music",
        "encoding": "utf8",
        "rformat": "json",
        "vermerge": 1,
        "mobi": 1,
        "issubtitle": 1,
    }
    logger.debug(
        "Requesting kuwo search api: keyword={}, limit={}, url={}",
        keyword,
        limit,
        SEARCH_API_URL,
    )
    try:
        response = await client.get(SEARCH_API_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise KuwoSearchNetworkError("search request failed") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise KuwoSearchResponseError("search response is not valid json") from exc

    try:
        search_response = type_validate_python(KuwoSearchResponse, payload)
    except ValidationError as exc:
        raise KuwoSearchResponseError("search response schema mismatch") from exc
    logger.info(
        "Kuwo search api succeeded: keyword={}, song_count={}",
        keyword,
        len(search_response.songs),
    )
    return search_response.songs


async def get_song_media(rid: str, br: str) -> KuwoTrackResource:
    track_data, cover_url = await asyncio.gather(
        get_song_link(rid, br),
        get_song_cover(rid),
    )
    return KuwoTrackResource(
        rid=rid,
        format=track_data.format,
        ekey=track_data.ekey,
        bitrate=track_data.bitrate,
        duration=track_data.duration,
        direct_url=track_data.direct_url,
        cover_url=cover_url,
    )


async def get_song_detailed_media(rid: str, br: str) -> KuwoDetailedTrackResource:
    track_data, detail = await asyncio.gather(
        get_song_link(rid, br),
        get_song_detail(rid),
    )
    return KuwoDetailedTrackResource(
        rid=rid,
        format=track_data.format,
        ekey=track_data.ekey,
        bitrate=track_data.bitrate,
        duration=track_data.duration,
        direct_url=track_data.direct_url,
        cover_url=detail.cover_url,
        title=detail.name,
        artist=detail.artist,
        album=detail.album,
    )


async def get_song_link(rid: str, br: str) -> KuwoTrackLinkData:
    client = await get_http_client()
    params = {
        "f": "web",
        "source": "kwplayer_ar_8.5.5.0_keluze.apk",
        "type": "convert_url_with_sign",
        "rid": rid,
        "br": br,
        "user": 10082,
    }
    try:
        response = await client.get(TRACK_API_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise KuwoTrackNetworkError("track request failed") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise KuwoTrackResponseError("track response is not valid json") from exc

    try:
        track_response = type_validate_python(KuwoTrackLinkResponse, payload)
    except ValidationError as exc:
        raise KuwoTrackResponseError("track response schema mismatch") from exc

    if track_response.code != 200:
        raise KuwoTrackResponseError(f"track response code is {track_response.code}")
    return track_response.data


async def get_song_detail(rid: str) -> KuwoTrackDetail:
    client = await get_http_client()
    params = {
        "src": "kwplayer_ar_11.3.1.1_40.apk",
        "op": "query",
        "action": "play",
        "ids": rid,
    }
    try:
        response = await client.get(DETAIL_API_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise KuwoTrackNetworkError("track detail request failed") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise KuwoTrackResponseError("track detail response is not valid json") from exc

    try:
        detail_response = type_validate_python(KuwoTrackDetailResponse, payload)
    except ValidationError as exc:
        raise KuwoTrackResponseError("track detail response schema mismatch") from exc

    if detail_response.errorcode != 0:
        raise KuwoTrackResponseError(
            f"track detail response error is {detail_response.errorcode}"
        )
    if detail_response.result.lower() != "ok" or not detail_response.songs:
        raise KuwoTrackResponseError("track detail response missing songs")
    return detail_response.songs[0]


async def get_song_cover(rid: str) -> str | None:
    client = await get_http_client()
    params = {
        "type": "rid_pic",
        "pictype": "url",
        "size": 700,
        "rid": rid,
    }
    try:
        response = await client.get(COVER_API_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    cover_url = response.text.strip().strip('"')
    return cover_url or None


def _get_track_file_temp_path(file_path: Path) -> Path:
    return file_path.with_name(f"{file_path.name}{TRACK_CACHE_TEMP_SUFFIX}")


def _remove_path(file_path: Path) -> None:
    file_path.unlink(missing_ok=True)


def _replace_path(source_path: Path, target_path: Path) -> Path:
    return source_path.replace(target_path)


def _delete_track_cache_path(file_path: Path, reason: str) -> None:
    try:
        _remove_path(file_path)
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
        time.time() - (retention_days * SECONDS_PER_DAY)
        if retention_days > 0
        else None
    )

    for file_path in track_file_cache_dir.iterdir():
        if not file_path.is_file():
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

        candidates.append((resolved_path, stat.st_size, stat.st_mtime))

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
    _remove_path(temp_path)
    client = await get_http_client()
    try:
        async with client.stream("GET", direct_url) as response:
            response.raise_for_status()
            with temp_path.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    file.write(chunk)
    except httpx.HTTPError as exc:
        _remove_path(temp_path)
        raise KuwoTrackNetworkError("track file download failed") from exc
    except OSError as exc:
        _remove_path(temp_path)
        raise KuwoTrackResponseError("track file write failed") from exc

    if temp_path.stat().st_size <= 0:
        _remove_path(temp_path)
        raise KuwoTrackResponseError("track file download is empty")

    try:
        _replace_path(temp_path, file_path)
    except OSError as exc:
        _remove_path(temp_path)
        raise KuwoTrackResponseError("track file finalize failed") from exc
    return file_path


async def download_track_file(
    rid: str,
    direct_url: str,
    format_name: str,
    bitrate: int,
    ekey: str | None = None,
) -> Path:
    async with _track_file_operation_lock:
        extension = resolve_track_file_extension(direct_url, format_name)
        track_file_cache_dir = initialize_track_cache_dir()

        if extension == "mflac":
            if not ekey:
                raise KuwoTrackResponseError("track file ekey is missing")

            encrypted_path = (track_file_cache_dir / f"{rid}_{bitrate}.mflac").resolve()
            decrypted_path = (track_file_cache_dir / f"{rid}_{bitrate}.flac").resolve()
            decrypted_temp_path = _get_track_file_temp_path(decrypted_path)
            _cleanup_track_file_cache(
                track_file_cache_dir,
                keep_paths={encrypted_path, decrypted_path},
            )

            if decrypted_path.is_file() and decrypted_path.stat().st_size > 0:
                _remove_path(encrypted_path)
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

            _remove_path(decrypted_temp_path)
            try:
                decrypt_mflac_file(encrypted_path, decrypted_temp_path, ekey)
            except (OSError, ValueError) as exc:
                _remove_path(decrypted_temp_path)
                raise KuwoTrackResponseError("track file decrypt failed") from exc

            if decrypted_temp_path.stat().st_size <= 0:
                _remove_path(decrypted_temp_path)
                raise KuwoTrackResponseError("track file decrypt is empty")

            try:
                _replace_path(decrypted_temp_path, decrypted_path)
            except OSError as exc:
                _remove_path(decrypted_temp_path)
                raise KuwoTrackResponseError("track file finalize failed") from exc
            _remove_path(encrypted_path)
            _cleanup_track_file_cache(
                track_file_cache_dir,
                keep_paths={decrypted_path},
            )
            return decrypted_path

        if extension not in SUPPORTED_TRACK_FILE_FORMATS:
            raise KuwoUnsupportedFormatError(f"unsupported track format: {extension}")

        file_path = (track_file_cache_dir / f"{rid}_{bitrate}.{extension}").resolve()
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
