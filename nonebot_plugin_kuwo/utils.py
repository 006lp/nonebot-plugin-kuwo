from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from nonebot_plugin_alconna.builtins.uniseg.music_share import (
    MusicShare,
    MusicShareKind,
)
from nonebot_plugin_alconna.uniseg import File, Image, Text, UniMessage, Voice

from .config import TrackRenderMode

_MUSICRID_RE = re.compile(r"(?:MUSIC_)?(?P<song_id>\d+)$")


def normalize_musicrid(value: str) -> str:
    match = _MUSICRID_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid musicrid: {value}")
    return match.group("song_id")


def join_keyword_parts(parts: Sequence[str]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def format_search_result_line(index: int, song_id: str, name: str, artist: str) -> str:
    return f"{index}. {song_id} {name}-{artist}"


def strip_url_query(url: str) -> str:
    return url.split("?", maxsplit=1)[0]


def format_track_text(
    *,
    rid: str,
    bitrate: int,
    duration: int,
    direct_url: str,
    ekey: str | None = None,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
) -> str:
    lines: list[str] = []
    if title and artist:
        lines.append(f"{title} - {artist}")
    elif title:
        lines.append(title)
    else:
        lines.append(f"歌曲 ID：{rid}")

    if album:
        lines.append(f"专辑：{album}")

    lines.append(f"时长：{duration}s")
    lines.append(f"码率：{bitrate} kbps")
    if ekey:
        lines.append(f"ekey：{ekey}")
    lines.append(f"直链：{direct_url}")
    return "\n".join(lines)


def format_track_card_content(
    *,
    artist: str | None = None,
    album: str | None = None,
    bitrate: int,
    duration: int,
) -> str:
    parts = [value for value in (artist, album) if value]
    if parts:
        return " | ".join(parts)
    return f"{duration}s | {bitrate} kbps"


def build_track_message(
    *,
    render_mode: TrackRenderMode,
    rid: str,
    bitrate: int,
    duration: int,
    direct_url: str,
    ekey: str | None = None,
    local_file_path: str | None = None,
    cover_url: str | None = None,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
) -> str | UniMessage:
    if render_mode is TrackRenderMode.FILE:
        if not local_file_path:
            raise ValueError("local_file_path is required for file mode")
        file_path = Path(local_file_path)
        return UniMessage([File(path=file_path, name=file_path.name)])

    if render_mode is TrackRenderMode.RECORD:
        return UniMessage([Voice(url=direct_url)])

    if render_mode is TrackRenderMode.CARD:
        return UniMessage(
            [
                MusicShare(
                    kind=MusicShareKind.Custom,
                    url=direct_url,
                    audio=direct_url,
                    title=title or f"歌曲 ID {rid}",
                    content=format_track_card_content(
                        artist=artist,
                        album=album,
                        bitrate=bitrate,
                        duration=duration,
                    ),
                    thumbnail=cover_url,
                )
            ]
        )

    text = format_track_text(
        rid=rid,
        bitrate=bitrate,
        duration=duration,
        direct_url=direct_url,
        ekey=ekey,
        title=title,
        artist=artist,
        album=album,
    )
    if not cover_url:
        return text
    return UniMessage([Image(url=cover_url), Text(f"\n{text}")])
