from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from nonebot_plugin_alconna.builtins.uniseg.music_share import (
    MusicShare,
    MusicShareKind,
)
from nonebot_plugin_alconna.uniseg import File, Image, Text, UniMessage, Voice

from .config import KuwoQuality, TrackRenderMode

_MUSICRID_RE = re.compile(r"(?:MUSIC_)?(?P<song_id>\d+)$")
_AUDIO_SUFFIX_RE = re.compile(r"\.(?:aac|flac|mflac|mgg|mp3|ogg|wav)$", re.IGNORECASE)
_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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


def _strip_audio_suffix(value: str) -> str:
    return _AUDIO_SUFFIX_RE.sub("", value.strip())


def _sanitize_filename_part(value: str, fallback: str) -> str:
    sanitized = _INVALID_FILENAME_CHARS_RE.sub(" ", value)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
    return sanitized or fallback


def format_track_file_name(
    *,
    quality: KuwoQuality,
    file_path: Path,
    rid: str,
    title: str | None = None,
    artist: str | None = None,
) -> str:
    title_part = _sanitize_filename_part(
        _strip_audio_suffix(title or ""),
        f"歌曲 ID {rid}",
    )
    artist_part = _sanitize_filename_part(artist or "", "")
    track_name = f"{title_part} - {artist_part}" if artist_part else title_part
    return f"[{quality.value}]{track_name}{file_path.suffix}"


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
    quality: KuwoQuality,
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
        file_name = format_track_file_name(
            quality=quality,
            file_path=file_path,
            rid=rid,
            title=title,
            artist=artist,
        )
        return UniMessage([File(path=file_path, name=file_name)])

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
