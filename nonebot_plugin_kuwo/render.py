from __future__ import annotations

import asyncio
import base64
import unicodedata
from collections.abc import Sequence
from html import escape

import httpx
from nonebot import logger
from nonebot_plugin_alconna.uniseg import Image, UniMessage

from ._qmc_rs import render_svg_to_png
from .config import ListRenderMode
from .models import KuwoSearchSong
from .utils import format_search_result_line

_SVG_WIDTH = 980
_SVG_HEADER_HEIGHT = 150
_SVG_ROW_HEIGHT = 136
_SVG_BOTTOM_PADDING = 28
_SVG_SCALE = 2.0
_COVER_SIZE = 104
_COVER_TIMEOUT = 5.0
_MAX_COVER_BYTES = 5 * 1024 * 1024


def _render_search_results_text(songs: Sequence[KuwoSearchSong]) -> str:
    logger.debug(
        "Rendering kuwo search results in text mode: song_count={}", len(songs)
    )
    return "\n".join(
        format_search_result_line(index, song.song_id, song.name, song.artist)
        for index, song in enumerate(songs, start=1)
    )


def _truncate(value: str | None, limit: int, fallback: str = "") -> str:
    text = (value or fallback).strip()
    def width(char: str) -> int:
        if unicodedata.combining(char):
            return 0
        return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1

    if sum(map(width, text)) <= limit:
        return text
    used = 0
    result: list[str] = []
    for char in text:
        used += width(char)
        if used > max(0, limit - 2):
            break
        result.append(char)
    return "".join(result) + "…"


def _format_duration(seconds: int) -> str:
    minutes, seconds = divmod(max(0, seconds), 60)
    return f"{minutes}:{seconds:02d}"


def _cover_placeholder(x: int, y: int) -> str:
    return f"""
      <rect x="{x}" y="{y}" width="{_COVER_SIZE}" height="{_COVER_SIZE}" rx="18"
            fill="#f2dfcf" />
      <circle cx="{x + 52}" cy="{y + 45}" r="24" fill="#d99867" opacity="0.35" />
      <path d="M{x + 35} {y + 73} C{x + 44} {y + 58}, {x + 60} {y + 58}, {x + 69} {y + 73}"
            fill="none" stroke="#a75d2b" stroke-width="5" stroke-linecap="round" opacity="0.55" />
    """


def _cover_image(data_uri: str | None, x: int, y: int, clip_id: str) -> str:
    if not data_uri:
        return _cover_placeholder(x, y)
    return f"""
      <defs>
        <clipPath id="{clip_id}">
          <rect x="{x}" y="{y}" width="{_COVER_SIZE}" height="{_COVER_SIZE}" rx="18" />
        </clipPath>
      </defs>
      <image href="{escape(data_uri, quote=True)}" x="{x}" y="{y}"
             width="{_COVER_SIZE}" height="{_COVER_SIZE}"
             preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip_id})" />
    """


async def _fetch_cover_data_uri(
    client: httpx.AsyncClient, song: KuwoSearchSong
) -> str | None:
    if not song.album_cover_url:
        return None

    try:
        async with client.stream("GET", song.album_cover_url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in {
                "image/png",
                "image/jpeg",
                "image/gif",
                "image/webp",
            }:
                logger.debug(
                    "Ignoring unsupported cover content type: song_id={}, content_type={}",
                    song.song_id,
                    content_type or "<missing>",
                )
                return None

            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > _MAX_COVER_BYTES:
                    logger.debug(
                        "Ignoring oversized cover: song_id={}, bytes>{}",
                        song.song_id,
                        _MAX_COVER_BYTES,
                    )
                    return None
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        logger.opt(exception=exc).debug(
            "Failed to fetch search result cover: song_id={}", song.song_id
        )
        return None

    encoded = base64.b64encode(b"".join(chunks)).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


async def _fetch_cover_data_uris(
    songs: Sequence[KuwoSearchSong],
) -> list[str | None]:
    timeout = httpx.Timeout(_COVER_TIMEOUT)
    limits = httpx.Limits(max_connections=min(10, max(1, len(songs))))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, limits=limits) as client:
        return list(await asyncio.gather(*(_fetch_cover_data_uri(client, song) for song in songs)))


def _build_search_results_svg(
    songs: Sequence[KuwoSearchSong], cover_data_uris: Sequence[str | None]
) -> str:
    height = _SVG_HEADER_HEIGHT + len(songs) * _SVG_ROW_HEIGHT + _SVG_BOTTOM_PADDING
    rows: list[str] = []

    for index, (song, cover_data_uri) in enumerate(zip(songs, cover_data_uris, strict=True), start=1):
        y = _SVG_HEADER_HEIGHT + (index - 1) * _SVG_ROW_HEIGHT
        card_y = y + 4
        cover_y = y + 14
        clip_id = f"cover-clip-{index}"
        title = escape(_truncate(song.name, 34, "Unknown Track"))
        artist = escape(_truncate(song.artist, 42, "Unknown Artist"))
        album = escape(_truncate(song.album, 45, "Unknown Album"))
        song_id = escape(song.song_id)
        duration = _format_duration(song.duration)

        rows.append(
            f"""
    <g>
      <rect x="28" y="{card_y}" width="924" height="120" rx="24" fill="#ffffff" fill-opacity="0.94" />
      <text x="61" y="{y + 73}" class="index">{index:02d}</text>
      {_cover_image(cover_data_uri, 112, cover_y, clip_id)}
      <defs>
        <clipPath id="text-clip-{index}">
          <rect x="240" y="{y + 16}" width="590" height="90" />
        </clipPath>
      </defs>
      <g clip-path="url(#text-clip-{index})">
      <text x="240" y="{y + 44}" class="title">{title}</text>
      <text x="240" y="{y + 72}" class="artist">{artist}</text>
      <text x="240" y="{y + 99}" class="meta">ID {song_id} · {album}</text>
      </g>
      <rect x="850" y="{y + 43}" width="74" height="34" rx="17" fill="#f7eee7" />
      <text x="887" y="{y + 66}" class="duration" text-anchor="middle">{duration}</text>
    </g>
            """
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_SVG_WIDTH}" height="{height}" viewBox="0 0 {_SVG_WIDTH} {height}">
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f8f0e7" />
      <stop offset="1" stop-color="#dce9f8" />
    </linearGradient>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="10" stdDeviation="18" flood-color="#39465b" flood-opacity="0.12" />
    </filter>
    <style>
      text {{ font-family: "Noto Sans CJK SC", "Noto Sans SC", "Microsoft YaHei", "PingFang SC", "Arial", sans-serif; }}
      .eyebrow {{ font-size: 14px; font-weight: 700; letter-spacing: 2px; fill: #bd6a31; }}
      .heading {{ font-size: 34px; font-weight: 800; fill: #202938; }}
      .subtitle {{ font-size: 15px; fill: #657083; }}
      .badge {{ font-size: 14px; font-weight: 700; fill: #a55a2a; }}
      .index {{ font-size: 24px; font-weight: 800; fill: #c16a31; text-anchor: middle; }}
      .title {{ font-size: 23px; font-weight: 800; fill: #202938; }}
      .artist {{ font-size: 17px; font-weight: 600; fill: #5e697b; }}
      .meta {{ font-size: 14px; fill: #737f92; }}
      .duration {{ font-size: 15px; font-weight: 700; fill: #8e572f; }}
    </style>
  </defs>

  <rect width="100%" height="100%" fill="url(#background)" />
  <rect x="18" y="18" width="944" height="{height - 36}" rx="32" fill="#ffffff" fill-opacity="0.66" filter="url(#shadow)" />

  <text x="48" y="59" class="eyebrow">KUWO SEARCH</text>
  <text x="48" y="98" class="heading">Kuwo Search Results</text>
  <text x="48" y="126" class="subtitle">Sequence · song ID · artist · album · duration</text>
  <rect x="844" y="63" width="92" height="38" rx="19" fill="#f5dbc8" />
  <text x="890" y="88" class="badge" text-anchor="middle">{len(songs)} Tracks</text>

  {''.join(rows)}
</svg>"""


async def _render_search_results_image(songs: Sequence[KuwoSearchSong]) -> UniMessage:
    logger.info("Rendering kuwo search results in image mode: song_count={}", len(songs))
    cover_data_uris = await _fetch_cover_data_uris(songs)
    svg = _build_search_results_svg(songs, cover_data_uris)
    image_bytes = await asyncio.to_thread(render_svg_to_png, svg, _SVG_SCALE)
    logger.info(
        "Rendered kuwo search result image successfully: byte_length={}",
        len(image_bytes),
    )
    return UniMessage([Image(raw=image_bytes)])


async def render_search_results(
    songs: Sequence[KuwoSearchSong],
    mode: ListRenderMode,
) -> str | UniMessage:
    logger.info(
        "Starting kuwo search result render: mode={}, song_count={}",
        mode.value,
        len(songs),
    )
    if mode is ListRenderMode.IMAGE:
        try:
            return await _render_search_results_image(songs)
        except Exception as exc:  # pragma: no cover - fallback branch
            logger.opt(exception=exc).warning(
                "Search result image rendering failed; fallback to text mode"
            )

    rendered_text = _render_search_results_text(songs)
    logger.debug(
        "Returning kuwo search text render result: text_length={}",
        len(rendered_text),
    )
    return rendered_text
