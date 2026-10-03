from __future__ import annotations

import asyncio
import base64
import re
import unicodedata
from collections.abc import Sequence
from html import escape
from pathlib import Path

import httpx
from nonebot import logger
from nonebot_plugin_alconna.uniseg import Image, UniMessage

from ._native import render_svg_to_png
from .config import ListRenderMode
from .data_source import get_http_client
from .models import KuwoSearchSong
from .utils import format_search_result_line, wait_for_completion

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"

CANVAS_WIDTH = 920
CANVAS_MARGIN = 26
PANEL_PADDING = 26
PANEL_RADIUS = 26

HEADER_HEIGHT = 88
ROW_HEIGHT = 104
ROW_GAP = 12
ROW_RADIUS = 18
COVER_SIZE = 80
COVER_RADIUS = 12
INDEX_COLUMN_WIDTH = 56
BODY_GAP = 18
DURATION_BADGE_WIDTH = 76
COUNT_BADGE_WIDTH = 132
TEXT_BLOCK_GAP = 12

IMAGE_SCALE = 2.0
COVER_FETCH_TIMEOUT = 8.0
MAX_COVER_BYTES = 5 * 1024 * 1024
BUNDLED_FONT_PATH = Path(__file__).with_name("fonts") / "LXGWWenKaiMono-Regular.ttf"

TITLE_MAX_UNITS = 44
ARTIST_MAX_UNITS = 56
META_MAX_UNITS = 64

COLOR_TEXT_STRONG = "#1f2937"
COLOR_TEXT_MUTED = "#5b6473"
COLOR_TEXT_SOFT = "#677286"
COLOR_ACCENT = "#c26a2d"
COLOR_ACCENT_DARK = "#8f5a33"
COLOR_PANEL = "#ffffff"
COLOR_CARD = "#ffffff"
COLOR_BORDER = "#e7ddd2"
COLOR_BADGE = "#f7efe8"
COLOR_BADGE_BORDER = "#f0dccb"
COLOR_PLACEHOLDER = "#f6d9c3"

_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
_INVALID_XML_CHARACTERS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]"
)
_image_render_lock = asyncio.Lock()


def _render_search_results_text(songs: Sequence[KuwoSearchSong]) -> str:
    logger.debug(
        "Rendering kuwo search results in text mode: song_count={}", len(songs)
    )
    return "\n".join(
        format_search_result_line(index, song.song_id, song.name, song.artist)
        for index, song in enumerate(songs, start=1)
    )


def resolve_font_sources(
    extra_files: Sequence[str], extra_dirs: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Use custom font sources when present, otherwise the bundled CJK font."""

    font_files: list[str] = []
    for raw_path in extra_files:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            logger.warning("Configured render font file does not exist: {}", path)
            continue
        font_files.append(str(path))

    font_dirs: list[str] = []
    for raw_path in extra_dirs:
        path = Path(raw_path).expanduser()
        if not path.is_dir():
            logger.warning("Configured render font directory does not exist: {}", path)
            continue
        font_dirs.append(str(path))

    if not font_files and not font_dirs:
        if BUNDLED_FONT_PATH.is_file():
            font_files.append(str(BUNDLED_FONT_PATH))
        else:
            logger.warning("Bundled render font is missing: {}", BUNDLED_FONT_PATH)

    logger.debug(
        "Resolved render font sources: font_files={}, font_dirs={}",
        font_files,
        font_dirs,
    )
    return font_files, font_dirs


def _character_width(character: str) -> int:
    if unicodedata.combining(character):
        return 0
    return 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1


def _truncate(value: str | None, max_units: int, fallback: str = "") -> str:
    text = (value or fallback).strip()
    if not text:
        return ""

    if sum(_character_width(character) for character in text) <= max_units:
        return text

    budget = max(max_units - _character_width("…"), 0)
    consumed = 0
    kept: list[str] = []
    for character in text:
        width = _character_width(character)
        if consumed + width > budget:
            break
        kept.append(character)
        consumed += width
    return "".join(kept).rstrip() + "…"


def _format_duration(seconds: int) -> str:
    minutes, remainder = divmod(max(0, seconds), 60)
    return f"{minutes}:{remainder:02d}"


def _svg_text(value: str) -> str:
    return escape(_INVALID_XML_CHARACTERS.sub("", value))


def _sniff_image_mime(data: bytes) -> str | None:
    for signature, mime in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _fetch_cover_data_uri(song: KuwoSearchSong) -> str | None:
    cover_url = song.album_cover_url
    if not cover_url:
        logger.debug(
            "Search result cover missing, using placeholder: song_id={}, name={}",
            song.song_id,
            song.name,
        )
        return None

    client = await get_http_client()
    try:
        async with client.stream(
            "GET",
            cover_url,
            headers={"Accept-Encoding": "identity"},
            timeout=COVER_FETCH_TIMEOUT,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()

            if response.headers.get(
                "content-encoding", "identity"
            ).strip().lower() not in {"", "identity"}:
                logger.warning(
                    "Compressed cover response rejected: song_id={}", song.song_id
                )
                return None

            content_type = (
                response.headers.get("content-type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            if content_type and not content_type.startswith("image/"):
                logger.warning(
                    "Search result cover is not an image: song_id={}, "
                    "cover_url={}, content_type={}",
                    song.song_id,
                    cover_url,
                    content_type,
                )
                return None

            payload = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                if len(payload) + len(chunk) > MAX_COVER_BYTES:
                    logger.warning(
                        "Search result cover exceeds {} bytes, using placeholder: "
                        "song_id={}, cover_url={}",
                        MAX_COVER_BYTES,
                        song.song_id,
                        cover_url,
                    )
                    return None
                payload.extend(chunk)
    except httpx.HTTPError as exc:
        logger.warning(
            "Failed to download search result cover: song_id={}, cover_url={}, error={}",
            song.song_id,
            cover_url,
            exc,
        )
        return None

    data = bytes(payload)
    mime = _sniff_image_mime(data)
    if mime is None:
        logger.warning(
            "Search result cover payload is not a supported image: song_id={}, "
            "cover_url={}, content_type={}",
            song.song_id,
            cover_url,
            content_type or "<missing>",
        )
        return None

    logger.debug(
        "Search result cover resolved: song_id={}, cover_url={}, byte_length={}",
        song.song_id,
        cover_url,
        len(data),
    )
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _build_cover_placeholder(x: float, y: float) -> str:
    center_x = x + COVER_SIZE / 2
    center_y = y + COVER_SIZE / 2
    return f"""
    <rect x="{x}" y="{y}" width="{COVER_SIZE}" height="{COVER_SIZE}"
          rx="{COVER_RADIUS}" fill="{COLOR_PLACEHOLDER}"/>
    <circle cx="{center_x}" cy="{center_y}" r="{COVER_SIZE * 0.3}"
            fill="none" stroke="{COLOR_ACCENT_DARK}" stroke-width="3" opacity="0.45"/>
    <circle cx="{center_x}" cy="{center_y}" r="{COVER_SIZE * 0.08}"
            fill="{COLOR_ACCENT_DARK}" opacity="0.45"/>
    """


def _build_cover_block(
    *,
    index: int,
    x: float,
    y: float,
    data_uri: str | None,
) -> str:
    placeholder = _build_cover_placeholder(x, y)
    if not data_uri:
        return placeholder

    # Keep the placeholder underneath if the native decoder rejects the cover.
    return f"""
    {placeholder}
    <clipPath id="cover-clip-{index}">
      <rect x="{x}" y="{y}" width="{COVER_SIZE}" height="{COVER_SIZE}"
            rx="{COVER_RADIUS}"/>
    </clipPath>
    <image x="{x}" y="{y}" width="{COVER_SIZE}" height="{COVER_SIZE}"
           preserveAspectRatio="xMidYMid slice" clip-path="url(#cover-clip-{index})"
           xlink:href="{_svg_text(data_uri)}"/>
    """


def _build_song_row(
    *,
    song: KuwoSearchSong,
    index: int,
    row_y: float,
    content_x: float,
    content_width: float,
    data_uri: str | None,
) -> str:
    cover_x = content_x + INDEX_COLUMN_WIDTH
    cover_y = row_y + (ROW_HEIGHT - COVER_SIZE) / 2
    body_x = cover_x + COVER_SIZE + BODY_GAP
    badge_x = content_x + content_width - 16 - DURATION_BADGE_WIDTH
    badge_y = row_y + (ROW_HEIGHT - 32) / 2
    text_clip_width = max(badge_x - TEXT_BLOCK_GAP - body_x, 1.0)
    title = _svg_text(_truncate(song.name, TITLE_MAX_UNITS, "Unknown Track"))
    artist = _svg_text(_truncate(song.artist, ARTIST_MAX_UNITS, "Unknown Artist"))
    album = _svg_text(_truncate(song.album, META_MAX_UNITS, "Unknown Album"))
    meta = f"ID {_svg_text(song.song_id)} | {album}"
    cover = _build_cover_block(index=index, x=cover_x, y=cover_y, data_uri=data_uri)

    return f"""
    <rect x="{content_x}" y="{row_y}" width="{content_width}" height="{ROW_HEIGHT}"
          rx="{ROW_RADIUS}" fill="{COLOR_CARD}" stroke="{COLOR_BORDER}"/>
    <text x="{content_x + INDEX_COLUMN_WIDTH / 2}" y="{row_y + ROW_HEIGHT / 2 + 9}"
          text-anchor="middle" font-size="24" font-weight="800"
          fill="{COLOR_ACCENT}">{index:02d}</text>
    {cover}
    <clipPath id="text-clip-{index}">
      <rect x="{body_x}" y="{row_y + 14}" width="{text_clip_width}"
            height="{ROW_HEIGHT - 28}"/>
    </clipPath>
    <g clip-path="url(#text-clip-{index})">
      <text x="{body_x}" y="{row_y + 38}" font-size="21" font-weight="800"
            fill="{COLOR_TEXT_STRONG}">{title}</text>
      <text x="{body_x}" y="{row_y + 64}" font-size="16" font-weight="600"
            fill="{COLOR_TEXT_MUTED}">{artist}</text>
      <text x="{body_x}" y="{row_y + 86}" font-size="13"
            fill="{COLOR_TEXT_SOFT}">{meta}</text>
    </g>
    <rect x="{badge_x}" y="{badge_y}" width="{DURATION_BADGE_WIDTH}" height="32"
          rx="16" fill="{COLOR_BADGE}" stroke="{COLOR_BADGE_BORDER}"/>
    <text x="{badge_x + DURATION_BADGE_WIDTH / 2}" y="{badge_y + 21}"
          text-anchor="middle" font-size="14" font-weight="700"
          fill="{COLOR_ACCENT_DARK}">{_format_duration(song.duration)}</text>
    """


def _build_search_results_svg(
    songs: Sequence[KuwoSearchSong],
    cover_data_uris: Sequence[str | None],
) -> str:
    logger.debug("Building kuwo search result svg: song_count={}", len(songs))
    song_count = len(songs)
    rows_height = song_count * ROW_HEIGHT + max(song_count - 1, 0) * ROW_GAP
    canvas_height = CANVAS_MARGIN * 2 + PANEL_PADDING * 2 + HEADER_HEIGHT + rows_height
    content_x = CANVAS_MARGIN + PANEL_PADDING
    content_width = CANVAS_WIDTH - content_x * 2
    content_y = CANVAS_MARGIN + PANEL_PADDING
    rows = "".join(
        _build_song_row(
            song=song,
            index=index,
            row_y=content_y + HEADER_HEIGHT + (index - 1) * (ROW_HEIGHT + ROW_GAP),
            content_x=content_x,
            content_width=content_width,
            data_uri=data_uri,
        )
        for index, (song, data_uri) in enumerate(
            zip(songs, cover_data_uris, strict=True), start=1
        )
    )
    count_badge_x = content_x + content_width - COUNT_BADGE_WIDTH
    panel_width = CANVAS_WIDTH - CANVAS_MARGIN * 2
    panel_height = canvas_height - CANVAS_MARGIN * 2
    svg = f"""
    <svg xmlns="{SVG_NAMESPACE}" xmlns:xlink="{XLINK_NAMESPACE}"
         width="{CANVAS_WIDTH}" height="{canvas_height}"
         viewBox="0 0 {CANVAS_WIDTH} {canvas_height}" font-family="sans-serif">
      <defs>
        <linearGradient id="canvas-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#f6efe4"/>
          <stop offset="1" stop-color="#dbe8f7"/>
        </linearGradient>
      </defs>
      <rect width="{CANVAS_WIDTH}" height="{canvas_height}" fill="url(#canvas-bg)"/>
      <rect x="{CANVAS_MARGIN}" y="{CANVAS_MARGIN}" width="{panel_width}"
            height="{panel_height}" rx="{PANEL_RADIUS}" fill="{COLOR_PANEL}"
            fill-opacity="0.9" stroke="{COLOR_BORDER}"/>
      <text x="{content_x}" y="{content_y + 16}" font-size="13" font-weight="700"
            letter-spacing="2" fill="{COLOR_ACCENT}">KUWO SEARCH</text>
      <text x="{content_x}" y="{content_y + 54}" font-size="30" font-weight="800"
            fill="{COLOR_TEXT_STRONG}">Kuwo Search Results</text>
      <rect x="{count_badge_x}" y="{content_y + 22}" width="{COUNT_BADGE_WIDTH}"
            height="34" rx="17" fill="{COLOR_BADGE}" stroke="{COLOR_BADGE_BORDER}"/>
      <text x="{count_badge_x + COUNT_BADGE_WIDTH / 2}" y="{content_y + 44}"
            text-anchor="middle" font-size="14" font-weight="700"
            fill="{COLOR_ACCENT_DARK}">{song_count} Tracks</text>
      {rows}
    </svg>
    """
    logger.debug(
        "Built kuwo search result svg successfully: svg_length={}, canvas_height={}",
        len(svg),
        canvas_height,
    )
    return svg


async def _render_search_results_image(
    songs: Sequence[KuwoSearchSong],
    extra_files: Sequence[str],
    extra_dirs: Sequence[str],
) -> UniMessage:
    logger.info(
        "Rendering kuwo search results in image mode: song_count={}", len(songs)
    )

    cover_data_uris = await asyncio.gather(
        *(_fetch_cover_data_uri(song) for song in songs)
    )
    svg = _build_search_results_svg(songs, cover_data_uris)

    font_files, font_dirs = resolve_font_sources(extra_files, extra_dirs)
    logger.debug(
        "Calling native svg renderer for kuwo search results: svg_length={}, "
        "scale={}, font_files={}, font_dirs={}",
        len(svg),
        IMAGE_SCALE,
        font_files,
        font_dirs,
    )
    image_bytes = await asyncio.to_thread(
        render_svg_to_png,
        svg,
        scale=IMAGE_SCALE,
        font_files=font_files,
        font_dirs=font_dirs,
    )
    logger.info(
        "Rendered kuwo search result image successfully: byte_length={}",
        len(image_bytes),
    )
    return UniMessage([Image(raw=image_bytes)])


async def render_search_results(
    songs: Sequence[KuwoSearchSong],
    mode: ListRenderMode,
    *,
    font_files: Sequence[str] = (),
    font_dirs: Sequence[str] = (),
) -> str | UniMessage:
    logger.info(
        "Starting kuwo search result render: mode={}, song_count={}",
        mode.value,
        len(songs),
    )
    if mode is ListRenderMode.IMAGE:
        # Third-party rendering failures must fall back to text and are logged below.
        try:
            # Bound cover buffers and native work across simultaneous commands.
            async with _image_render_lock:
                return await wait_for_completion(
                    _render_search_results_image(songs, font_files, font_dirs)
                )
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=exc).warning(
                "Search result image rendering failed; fallback to text mode"
            )

    rendered_text = _render_search_results_text(songs)
    logger.debug(
        "Returning kuwo search text render result: text_length={}",
        len(rendered_text),
    )
    return rendered_text
