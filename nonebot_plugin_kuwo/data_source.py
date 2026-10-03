from __future__ import annotations

import asyncio
import secrets
import string
from urllib.parse import urlparse

import httpx
from nonebot import logger
from nonebot.compat import type_validate_python
from pydantic import ValidationError

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

SEARCH_API_URL = "http://search.kuwo.cn/r.s"
TRACK_API_URL = "https://changenotice.kuwo.cn/mobi.s"
COVER_API_URL = "http://artistpicserver.kuwo.cn/pic.web"
DETAIL_API_URL = "http://musicpay.kuwo.cn/music.pay"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
TRACK_USER_ALPHABET = string.ascii_lowercase + string.digits
TRACK_USER_LENGTH = 16

_client: httpx.AsyncClient | None = None
_track_proxy_client: httpx.AsyncClient | None = None
_track_proxy_client_url: str | None = None
_client_lock = asyncio.Lock()
_track_proxy_client_lock = asyncio.Lock()


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


async def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
    return _client


def redact_proxy_url(proxy_url: str) -> str:
    parsed = urlparse(proxy_url)
    if not parsed.username and not parsed.password:
        return proxy_url

    host = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    return proxy_url.replace(parsed.netloc, f"***@{host}", 1)


async def get_track_proxy_http_client(proxy_url: str) -> httpx.AsyncClient:
    global _track_proxy_client, _track_proxy_client_url
    if _track_proxy_client is None or _track_proxy_client_url != proxy_url:
        async with _track_proxy_client_lock:
            if _track_proxy_client is not None and _track_proxy_client_url != proxy_url:
                await _track_proxy_client.aclose()
                _track_proxy_client = None
                _track_proxy_client_url = None

            if _track_proxy_client is None:
                _track_proxy_client = httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    proxy=proxy_url,
                )
                _track_proxy_client_url = proxy_url
                logger.info(
                    "Initialized kuwo track proxy http client: proxy={}",
                    redact_proxy_url(proxy_url),
                )
    return _track_proxy_client


async def initialize_http_client() -> None:
    await get_http_client()
    proxy_url = get_runtime_config().kuwo_track_proxy_url
    if proxy_url:
        await get_track_proxy_http_client(proxy_url)


async def close_http_client() -> None:
    global _client, _track_proxy_client, _track_proxy_client_url
    if _client is not None:
        await _client.aclose()
        _client = None
    if _track_proxy_client is not None:
        await _track_proxy_client.aclose()
        _track_proxy_client = None
        _track_proxy_client_url = None


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
    return search_response.songs[:limit]


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
    proxy_url = get_runtime_config().kuwo_track_proxy_url
    client = (
        await get_track_proxy_http_client(proxy_url)
        if proxy_url
        else await get_http_client()
    )
    params = {
        "f": "web",
        "source": "kwplayer_ar_8.5.5.0_keluze.apk",
        "type": "convert_url_with_sign",
        "rid": rid,
        "br": br,
        "user": generate_track_user(),
    }
    logger.debug(
        "Requesting kuwo track api: rid={}, br={}, url={}, proxy={}",
        rid,
        br,
        TRACK_API_URL,
        redact_proxy_url(proxy_url) if proxy_url else "<disabled>",
    )
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


def generate_track_user() -> str:
    return "".join(
        secrets.choice(TRACK_USER_ALPHABET) for _ in range(TRACK_USER_LENGTH)
    )


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
    except httpx.HTTPError as exc:
        logger.debug(
            "Kuwo song cover request failed; omitting cover: rid={}, error={}", rid, exc
        )
        return None

    cover_url = response.text.strip().strip('"')
    return cover_url or None
