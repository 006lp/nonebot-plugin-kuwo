from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from html import escape
from pathlib import Path

from nonebot import logger, require
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from .config import ListRenderMode
from .models import KuwoSearchSong
from .utils import format_search_result_line

_HTML_RENDER_BASE_URI = Path(__file__).resolve().as_uri()


def _render_search_results_text(songs: Sequence[KuwoSearchSong]) -> str:
    logger.debug("Rendering kuwo search results in text mode: song_count={}", len(songs))
    return "\n".join(
        format_search_result_line(index, song.song_id, song.name, song.artist)
        for index, song in enumerate(songs, start=1)
    )


def _load_html_to_pic() -> Callable[..., Awaitable[bytes]]:
    logger.debug("Loading nonebot_plugin_htmlrender entrypoint")
    require("nonebot_plugin_htmlrender")
    from nonebot_plugin_htmlrender import html_to_pic

    logger.debug("nonebot_plugin_htmlrender loaded successfully")
    return html_to_pic


def _build_cover_block(song: KuwoSearchSong) -> str:
    if not song.album_cover_url:
        logger.debug(
            "Search result cover missing, using placeholder: song_id={}, name={}",
            song.song_id,
            song.name,
        )
        return '<div class="cover cover--placeholder">NO COVER</div>'
    logger.debug(
        "Search result cover resolved: song_id={}, cover_url={}",
        song.song_id,
        song.album_cover_url,
    )
    return (
        '<img class="cover" '
        f'src="{escape(song.album_cover_url, quote=True)}" '
        f'alt="{escape(song.name, quote=True)}" />'
    )


def _build_search_results_html(songs: Sequence[KuwoSearchSong]) -> str:
    logger.debug("Building kuwo search result html: song_count={}", len(songs))
    cards = []
    for index, song in enumerate(songs, start=1):
        cards.append(
            f"""
            <section class="song-card">
              <div class="song-index">{index:02d}</div>
              {_build_cover_block(song)}
              <div class="song-body">
                <div class="song-title">{escape(song.name)}</div>
                <div class="song-artist">{escape(song.artist)}</div>
                <div class="song-meta">ID {escape(song.song_id)} | {escape(song.album or "Unknown Album")}</div>
              </div>
              <div class="song-duration">{song.duration}s</div>
            </section>
            """
        )

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <style>
          :root {{
            color-scheme: light;
            --bg-start: #f6efe4;
            --bg-end: #dbe8f7;
            --panel: rgba(255, 255, 255, 0.88);
            --card: rgba(255, 255, 255, 0.96);
            --text-strong: #1f2937;
            --text-muted: #5b6473;
            --accent: #c26a2d;
            --accent-soft: #f4d2bc;
            --border: rgba(123, 93, 72, 0.12);
            --shadow: 0 18px 45px rgba(54, 62, 79, 0.12);
          }}

          * {{
            box-sizing: border-box;
          }}

          body {{
            margin: 0;
            padding: 36px;
            font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            color: var(--text-strong);
            background:
              radial-gradient(circle at top left, rgba(255, 255, 255, 0.75), transparent 40%),
              linear-gradient(135deg, var(--bg-start), var(--bg-end));
          }}

          .frame {{
            width: 980px;
            padding: 28px;
            border-radius: 30px;
            background: var(--panel);
            border: 1px solid rgba(255, 255, 255, 0.55);
            box-shadow: var(--shadow);
            backdrop-filter: blur(14px);
          }}

          .header {{
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 24px;
            margin-bottom: 24px;
          }}

          .eyebrow {{
            margin-bottom: 8px;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--accent);
          }}

          .title {{
            margin: 0;
            font-size: 34px;
            line-height: 1.1;
          }}

          .subtitle {{
            margin: 8px 0 0;
            font-size: 15px;
            color: var(--text-muted);
          }}

          .badge {{
            flex-shrink: 0;
            padding: 10px 16px;
            border-radius: 999px;
            background: linear-gradient(135deg, #ffffff, var(--accent-soft));
            border: 1px solid rgba(194, 106, 45, 0.16);
            font-size: 14px;
            font-weight: 700;
            color: var(--accent);
          }}

          .list {{
            display: grid;
            gap: 14px;
          }}

          .song-card {{
            display: grid;
            grid-template-columns: 64px 112px minmax(0, 1fr) auto;
            align-items: center;
            gap: 18px;
            padding: 16px;
            border-radius: 22px;
            background: var(--card);
            border: 1px solid var(--border);
            box-shadow: 0 10px 24px rgba(31, 41, 55, 0.06);
          }}

          .song-index {{
            width: 64px;
            text-align: center;
            font-size: 24px;
            font-weight: 800;
            color: var(--accent);
          }}

          .cover {{
            width: 112px;
            height: 112px;
            object-fit: cover;
            border-radius: 16px;
            background: linear-gradient(135deg, #f6d9c3, #e7eefb);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3);
          }}

          .cover--placeholder {{
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 12px;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.08em;
            color: #8f5a33;
          }}

          .song-body {{
            min-width: 0;
          }}

          .song-title {{
            font-size: 24px;
            font-weight: 800;
            line-height: 1.25;
            word-break: break-word;
          }}

          .song-artist {{
            margin-top: 6px;
            font-size: 18px;
            font-weight: 600;
            color: var(--text-muted);
            word-break: break-word;
          }}

          .song-meta {{
            margin-top: 10px;
            font-size: 15px;
            color: #677286;
            word-break: break-word;
          }}

          .song-duration {{
            padding: 10px 14px;
            border-radius: 999px;
            background: #f7efe8;
            border: 1px solid rgba(194, 106, 45, 0.14);
            font-size: 16px;
            font-weight: 700;
            color: #8f5a33;
            white-space: nowrap;
          }}
        </style>
      </head>
      <body>
        <main class="frame">
          <header class="header">
            <div>
              <div class="eyebrow">Kuwo Search</div>
              <h1 class="title">Kuwo Search Results</h1>
              <p class="subtitle">Rendered {len(songs)} tracks with sequence, song ID, artist, album, and duration.</p>
            </div>
            <div class="badge">{len(songs)} Tracks</div>
          </header>
          <section class="list">
            {"".join(cards)}
          </section>
        </main>
      </body>
    </html>
    """
    logger.debug("Built kuwo search result html successfully: html_length={}", len(html))
    return html


async def _render_search_results_image(songs: Sequence[KuwoSearchSong]) -> Message:
    logger.info("Rendering kuwo search results in image mode: song_count={}", len(songs))
    html_to_pic = _load_html_to_pic()
    html = _build_search_results_html(songs)
    logger.debug(
        "Calling html_to_pic for kuwo search results: template_path={}, viewport_width={}, wait_ms={}",
        _HTML_RENDER_BASE_URI,
        1040,
        200,
    )
    image_bytes = await html_to_pic(
        html=html,
        template_path=_HTML_RENDER_BASE_URI,
        viewport={"width": 1040, "height": 10},
        wait=200,
        device_scale_factor=2,
    )
    logger.info(
        "Rendered kuwo search result image successfully: byte_length={}",
        len(image_bytes),
    )
    message = Message(MessageSegment.image(image_bytes))
    logger.debug(
        "Built search result image message: segment_count={}, first_segment_type={}",
        len(message),
        message[0].type if message else "unknown",
    )
    return message


async def render_search_results(
    songs: Sequence[KuwoSearchSong],
    mode: ListRenderMode,
) -> str | Message:
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
