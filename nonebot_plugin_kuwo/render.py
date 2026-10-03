from __future__ import annotations

import asyncio
import base64
import unicodedata
from collections.abc import Sequence
from html import escape
from pathlib import Path

import httpx
from nonebot import logger
from nonebot_plugin_alconna.uniseg import Image, UniMessage

from .config import Config, ListRenderMode
from .data_source import get_http_client
from .models import KuwoSearchSong
from .qmc import render_svg_to_png
from .utils import format_search_result_line

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


def _render_search_results_text(songs: Sequence[KuwoSearchSong]) -> str:
    logger.debug(
        "Rendering kuwo search results in text mode: song_count={}", len(songs)
    )
    return "\n".join(
        format_search_result_line(index, song.song_id, song.name, song.artist)
        for index, song in enumerate(songs, start=1)
    )


def resolve_font_sources(config: Config) -> tuple[list[str], list[str]]:
    """Collect the extra font files/directories the native renderer should load.

    Host fonts are always available through fontconfig; these entries are an
    escape hatch for minimal images (Docker, slim VPS) that ship no CJK font.
    """

    font_files: list[str] = []
    for raw_path in config.kuwo_render_font_files:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            logger.warning("Configured render font file does not exist: {}", path)
            continue
        font_files.append(str(path))

    font_dirs: list[str] = []
    for raw_path in config.kuwo_render_font_dirs:
        path = Path(raw_path).expanduser()
        if not path.is_dir():
            logger.warning("Configured render font directory does not exist: {}", path)
            continue
        font_dirs.append(str(path))

    if font_files or font_dirs:
        logger.debug(
            "Resolved extra render font sources: font_files={}, font_dirs={}",
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
            timeout=COVER_FETCH_TIMEOUT,
        ) as response:
            response.raise_for_status()

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
            async for chunk in response.aiter_bytes():
                payload.extend(chunk)
                if len(payload) > MAX_COVER_BYTES:
                    logger.warning(
                        "Search result cover exceeds {} bytes, using placeholder: "
                        "song_id={}, cover_url={}",
                        MAX_COVER_BYTES,
                        song.song_id,
                        cover_url,
                    )
                    return None
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
    return "".join(
        [
            (
                f'<rect x="{x}" y="{y}" width="{COVER_SIZE}" height="{COVER_SIZE}" '
                f'rx="{COVER_RADIUS}" fill="{COLOR_PLACEHOLDER}"/>'
            ),
            (
                f'<circle cx="{center_x}" cy="{center_y}" '
                f'r="{COVER_SIZE * 0.3}" fill="none" '
                f'stroke="{COLOR_ACCENT_DARK}" stroke-width="3" opacity="0.45"/>'
            ),
            (
                f'<circle cx="{center_x}" cy="{center_y}" '
                f'r="{COVER_SIZE * 0.08}" fill="{COLOR_ACCENT_DARK}" opacity="0.45"/>'
            ),
        ]
    )


def _build_cover_block(
    *,
    index: int,
    x: float,
    y: float,
    data_uri: str | None,
) -> str:
    clip_id = f"cover-clip-{index}"
    clip = (
        f'<clipPath id="{clip_id}">'
        f'<rect x="{x}" y="{y}" width="{COVER_SIZE}" height="{COVER_SIZE}" '
        f'rx="{COVER_RADIUS}"/>'
        f"</clipPath>"
    )
    if data_uri:
        body = (
            f'<image x="{x}" y="{y}" width="{COVER_SIZE}" height="{COVER_SIZE}" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip_id})" '
            f'xlink:href="{data_uri}"/>'
        )
        return clip + body

    return clip + _build_cover_placeholder(x, y)


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

    text_clip_x = body_x
    text_clip_width = max(badge_x - TEXT_BLOCK_GAP - body_x, 1.0)
    text_clip_y = row_y + 14
    text_clip_height = ROW_HEIGHT - 28

    album = _truncate(song.album, META_MAX_UNITS, "Unknown Album")
    meta = f"ID {escape(song.song_id)} | {escape(album)}"

    return "".join(
        [
            (
                f'<rect x="{content_x}" y="{row_y}" width="{content_width}" '
                f'height="{ROW_HEIGHT}" rx="{ROW_RADIUS}" fill="{COLOR_CARD}" '
                f'stroke="{COLOR_BORDER}"/>'
            ),
            (
                f'<text x="{content_x + INDEX_COLUMN_WIDTH / 2}" '
                f'y="{row_y + ROW_HEIGHT / 2 + 9}" text-anchor="middle" '
                f'font-size="24" font-weight="800" fill="{COLOR_ACCENT}">'
                f"{index:02d}</text>"
            ),
            _build_cover_block(
                index=index,
                x=cover_x,
                y=cover_y,
                data_uri=data_uri,
            ),
            (
                f'<clipPath id="text-clip-{index}">'
                f'<rect x="{text_clip_x}" y="{text_clip_y}" '
                f'width="{text_clip_width}" height="{text_clip_height}"/>'
                f"</clipPath>"
            ),
            f'<g clip-path="url(#text-clip-{index})">',
            (
                f'<text x="{body_x}" y="{row_y + 38}" font-size="21" '
                f'font-weight="800" fill="{COLOR_TEXT_STRONG}">'
                f"{escape(_truncate(song.name, TITLE_MAX_UNITS, 'Unknown Track'))}</text>"
            ),
            (
                f'<text x="{body_x}" y="{row_y + 64}" font-size="16" '
                f'font-weight="600" fill="{COLOR_TEXT_MUTED}">'
                f"{escape(_truncate(song.artist, ARTIST_MAX_UNITS, 'Unknown Artist'))}"
                f"</text>"
            ),
            (
                f'<text x="{body_x}" y="{row_y + 86}" font-size="13" '
                f'fill="{COLOR_TEXT_SOFT}">{meta}</text>'
            ),
            "</g>",
            (
                f'<rect x="{badge_x}" y="{badge_y}" width="{DURATION_BADGE_WIDTH}" '
                f'height="32" rx="16" fill="{COLOR_BADGE}" '
                f'stroke="{COLOR_BADGE_BORDER}"/>'
            ),
            (
                f'<text x="{badge_x + DURATION_BADGE_WIDTH / 2}" y="{badge_y + 21}" '
                f'text-anchor="middle" font-size="14" font-weight="700" '
                f'fill="{COLOR_ACCENT_DARK}">{_format_duration(song.duration)}</text>'
            ),
        ]
    )


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

    rows = []
    for index, song in enumerate(songs, start=1):
        row_y = content_y + HEADER_HEIGHT + (index - 1) * (ROW_HEIGHT + ROW_GAP)
        rows.append(
            _build_song_row(
                song=song,
                index=index,
                row_y=row_y,
                content_x=content_x,
                content_width=content_width,
                data_uri=cover_data_uris[index - 1],
            )
        )

    count_badge_x = content_x + content_width - COUNT_BADGE_WIDTH

    header = "".join(
        [
            (
                f'<text x="{content_x}" y="{content_y + 16}" font-size="13" '
                f'font-weight="700" letter-spacing="2" fill="{COLOR_ACCENT}">'
                f"KUWO SEARCH</text>"
            ),
            (
                f'<text x="{content_x}" y="{content_y + 54}" font-size="30" '
                f'font-weight="800" fill="{COLOR_TEXT_STRONG}">'
                f"Kuwo Search Results</text>"
            ),
            (
                f'<rect x="{count_badge_x}" y="{content_y + 22}" '
                f'width="{COUNT_BADGE_WIDTH}" height="34" rx="17" '
                f'fill="{COLOR_BADGE}" stroke="{COLOR_BADGE_BORDER}"/>'
            ),
            (
                f'<text x="{count_badge_x + COUNT_BADGE_WIDTH / 2}" '
                f'y="{content_y + 44}" text-anchor="middle" font-size="14" '
                f'font-weight="700" fill="{COLOR_ACCENT_DARK}">'
                f"{song_count} Tracks</text>"
            ),
        ]
    )

    panel_x = CANVAS_MARGIN
    panel_width = CANVAS_WIDTH - CANVAS_MARGIN * 2
    panel_height = canvas_height - CANVAS_MARGIN * 2

    svg = "".join(
        [
            (
                f'<svg xmlns="{SVG_NAMESPACE}" xmlns:xlink="{XLINK_NAMESPACE}" '
                f'width="{CANVAS_WIDTH}" height="{canvas_height}" '
                f'viewBox="0 0 {CANVAS_WIDTH} {canvas_height}" '
                f'font-family="sans-serif">'
            ),
            "<defs>",
            '<linearGradient id="canvas-bg" x1="0" y1="0" x2="1" y2="1">',
            '<stop offset="0" stop-color="#f6efe4"/>',
            '<stop offset="1" stop-color="#dbe8f7"/>',
            "</linearGradient>",
            "</defs>",
            (
                f'<rect width="{CANVAS_WIDTH}" height="{canvas_height}" '
                f'fill="url(#canvas-bg)"/>'
            ),
            (
                f'<rect x="{panel_x}" y="{panel_x}" width="{panel_width}" '
                f'height="{panel_height}" rx="{PANEL_RADIUS}" fill="{COLOR_PANEL}" '
                f'fill-opacity="0.9" stroke="{COLOR_BORDER}"/>'
            ),
            header,
            "".join(rows),
            "</svg>",
        ]
    )

    logger.debug(
        "Built kuwo search result svg successfully: svg_length={}, canvas_height={}",
        len(svg),
        canvas_height,
    )
    return svg


async def _render_search_results_image(
    songs: Sequence[KuwoSearchSong],
    config: Config,
) -> UniMessage:
    logger.info(
        "Rendering kuwo search results in image mode: song_count={}", len(songs)
    )

    cover_data_uris = await asyncio.gather(
        *(_fetch_cover_data_uri(song) for song in songs)
    )
    svg = _build_search_results_svg(songs, cover_data_uris)

    font_files, font_dirs = resolve_font_sources(config)
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
    config: Config,
) -> str | UniMessage:
    logger.info(
        "Starting kuwo search result render: mode={}, song_count={}",
        mode.value,
        len(songs),
    )
    if mode is ListRenderMode.IMAGE:
        # Third-party rendering failures must fall back to text and are logged below.
        try:
            return await _render_search_results_image(songs, config)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.opt(exception=exc).warning(
                "Search result image rendering failed; fallback to text mode"
            )

    rendered_text = _render_search_results_text(songs)
    logger.debug(
        "Returning kuwo search text render result: text_length={}",
        len(rendered_text),
    )
    return rendered_text
