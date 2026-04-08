from __future__ import annotations

import re
from collections.abc import Sequence

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
