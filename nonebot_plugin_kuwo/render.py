from __future__ import annotations

from collections.abc import Sequence

from nonebot import logger

from .config import SearchRenderMode
from .models import KuwoSearchSong
from .utils import format_search_result_line


async def render_search_results(
    songs: Sequence[KuwoSearchSong],
    mode: SearchRenderMode,
) -> str:
    if mode is SearchRenderMode.IMAGE:
        logger.warning("图片搜索结果渲染尚未实现，已回退到文本模式")

    return "\n".join(
        format_search_result_line(index, song.song_id, song.name, song.artist)
        for index, song in enumerate(songs, start=1)
    )
