from __future__ import annotations

import asyncio

import httpx
from pydantic import ValidationError

from .models import KuwoSearchResponse, KuwoSearchSong

SEARCH_API_URL = "http://search.kuwo.cn/r.s"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


class KuwoSearchError(Exception):
    """Base exception for Kuwo search failures."""


class KuwoSearchNetworkError(KuwoSearchError):
    """Raised when the remote search service is unavailable."""


class KuwoSearchResponseError(KuwoSearchError):
    """Raised when the remote response cannot be parsed."""


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
