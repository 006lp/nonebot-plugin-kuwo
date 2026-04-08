from __future__ import annotations

import asyncio

import httpx
from pydantic import ValidationError

from .models import (
    KuwoSearchResponse,
    KuwoSearchSong,
    KuwoTrackLinkData,
    KuwoTrackLinkResponse,
    KuwoTrackResource,
)

SEARCH_API_URL = "http://search.kuwo.cn/r.s"
TRACK_API_URL = "https://nmobi.kuwo.cn/mobi.s"
COVER_API_URL = "http://artistpicserver.kuwo.cn/pic.web"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


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
        search_response = KuwoSearchResponse.model_validate(payload)
    except ValidationError as exc:
        raise KuwoSearchResponseError("search response schema mismatch") from exc
    return search_response.songs


async def get_song_media(rid: str, br: str) -> KuwoTrackResource:
    track_data, cover_url = await asyncio.gather(
        get_song_link(rid, br),
        get_song_cover(rid),
    )
    return KuwoTrackResource(
        rid=rid,
        bitrate=track_data.bitrate,
        duration=track_data.duration,
        direct_url=track_data.direct_url,
        cover_url=cover_url,
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
        track_response = KuwoTrackLinkResponse.model_validate(payload)
    except ValidationError as exc:
        raise KuwoTrackResponseError("track response schema mismatch") from exc

    if track_response.code != 200:
        raise KuwoTrackResponseError(f"track response code is {track_response.code}")
    return track_response.data


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
