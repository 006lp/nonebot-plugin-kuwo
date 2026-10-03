from __future__ import annotations

from pathlib import Path

from arclet.alconna import Alconna, Args, Arparma, MultiVar, Option
from nonebot import get_driver, logger, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage

from .config import (
    Config,
    KuwoQuality,
    TrackRenderMode,
    get_quality_bitrate,
    get_runtime_config,
    resolve_track_quality,
)
from .data_source import (
    KuwoSearchNetworkError,
    KuwoSearchResponseError,
    KuwoTrackError,
    KuwoUnsupportedFormatError,
    close_http_client,
    get_song_detailed_media,
    get_song_media,
    initialize_http_client,
    search_songs,
)
from .files import download_track_file
from .models import KuwoTrackResource
from .render import render_search_results
from .utils import build_track_message, join_keyword_parts, normalize_musicrid

__plugin_meta__ = PluginMetadata(
    name="酷我音乐",
    description="酷我音乐搜索与直链发送插件",
    usage="/kwsearch <关键词>、/kw <关键词>、/kwid <rid>",
    type="application",
    homepage="https://github.com/006lp/nonebot-plugin-kuwo",
    config=Config,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

driver = get_driver()
driver.on_startup(initialize_http_client)
driver.on_shutdown(close_http_client)


kwsearch = on_alconna(
    Alconna("kwsearch", Args["keyword", MultiVar(str, "*")]),
    aliases={"kw搜索"},
    use_cmd_start=True,
    block=True,
)
kw = on_alconna(
    Alconna(
        "kw",
        Option("-q|--quality", Args["quality", str]),
        Args["keyword", MultiVar(str, "*")],
    ),
    use_cmd_start=True,
    block=True,
)
kwid = on_alconna(
    Alconna(
        "kwid",
        Option("-q|--quality", Args["quality", str]),
        Args["rid", str],
    ),
    use_cmd_start=True,
    block=True,
)


def _resolve_command_quality(
    *,
    command_name: str,
    render_mode: TrackRenderMode,
    requested_quality: str | KuwoQuality | None,
    default_quality: KuwoQuality,
) -> KuwoQuality:
    quality = resolve_track_quality(default_quality, requested_quality)

    if render_mode is TrackRenderMode.RECORD and quality is not KuwoQuality.STANDARD:
        logger.info(
            (
                "Record mode forces standard quality: command={}, "
                "requested_quality={}, default_quality={}, effective_quality={}"
            ),
            command_name,
            requested_quality if requested_quality else "<default>",
            default_quality.value,
            KuwoQuality.STANDARD.value,
        )
        return KuwoQuality.STANDARD

    if render_mode is TrackRenderMode.CARD and quality not in {
        KuwoQuality.STANDARD,
        KuwoQuality.EXHIGH,
        KuwoQuality.LOSSLESS,
    }:
        logger.info(
            (
                "Card mode caps quality to lossless: command={}, "
                "requested_quality={}, default_quality={}, effective_quality={}"
            ),
            command_name,
            requested_quality if requested_quality else "<default>",
            default_quality.value,
            KuwoQuality.LOSSLESS.value,
        )
        return KuwoQuality.LOSSLESS

    logger.info(
        "Resolved track quality: command={}, requested_quality={}, effective_quality={}",
        command_name,
        requested_quality if requested_quality else "<default>",
        quality.value,
    )
    return quality


async def _build_track_message(
    *,
    render_mode: TrackRenderMode,
    media: KuwoTrackResource,
    quality: KuwoQuality,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
) -> str | UniMessage:
    local_file_path: Path | None = None
    if render_mode is TrackRenderMode.FILE:
        local_file_path = await download_track_file(
            rid=media.rid,
            direct_url=media.direct_url,
            format_name=media.format,
            bitrate=media.bitrate,
            ekey=media.ekey,
        )

    return build_track_message(
        render_mode=render_mode,
        rid=media.rid,
        quality=quality,
        bitrate=media.bitrate,
        duration=media.duration,
        direct_url=media.direct_url,
        ekey=media.ekey,
        local_file_path=local_file_path,
        cover_url=media.cover_url,
        title=title,
        artist=artist,
        album=album,
    )


@kwsearch.handle()
async def handle_kwsearch(arp: Arparma) -> None:
    config = get_runtime_config()
    keyword = join_keyword_parts(arp.all_matched_args.get("keyword") or ())
    if not keyword:
        await kwsearch.finish("请输入搜索关键词")

    logger.info(
        "Received kwsearch command: keyword={}, limit={}, render_mode={}",
        keyword,
        config.kuwo_search_limit,
        config.kuwo_list_render_mode.value,
    )

    try:
        songs = await search_songs(keyword, config.kuwo_search_limit)
    except KuwoSearchNetworkError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo search request failed: keyword={}", keyword
        )
        await kwsearch.finish("搜索服务暂时不可用，请稍后再试")
    except KuwoSearchResponseError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo search response parsing failed: keyword={}",
            keyword,
        )
        await kwsearch.finish("搜索结果解析失败")

    logger.info(
        "kwsearch search completed: keyword={}, song_count={}", keyword, len(songs)
    )
    if not songs:
        await kwsearch.finish("未找到相关歌曲")

    message = await render_search_results(
        songs,
        config.kuwo_list_render_mode,
        font_files=config.kuwo_render_font_files,
        font_dirs=config.kuwo_render_font_dirs,
    )
    logger.debug(
        "kwsearch render completed: keyword={}, message_type={}, segment_count={}",
        keyword,
        type(message).__name__,
        len(message) if isinstance(message, UniMessage) else 1,
    )
    await kwsearch.finish(message)


@kw.handle()
async def handle_kw(arp: Arparma) -> None:
    config = get_runtime_config()
    keyword = join_keyword_parts(arp.all_matched_args.get("keyword") or ())
    if not keyword:
        await kw.finish("请输入搜索关键词")

    try:
        songs = await search_songs(keyword, 1)
    except KuwoSearchNetworkError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo search request failed: keyword={}", keyword
        )
        await kw.finish("搜索服务暂时不可用，请稍后再试")
    except KuwoSearchResponseError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo search response parsing failed: keyword={}",
            keyword,
        )
        await kw.finish("搜索结果解析失败")

    if not songs:
        await kw.finish("未找到相关歌曲")

    try:
        quality = _resolve_command_quality(
            command_name="kw",
            render_mode=config.kuwo_track_render_mode,
            requested_quality=arp.all_matched_args.get("quality"),
            default_quality=config.kuwo_default_quality,
        )
    except ValueError:
        await kw.finish("请输入正确的音质参数")

    try:
        song = songs[0]
        media = await get_song_media(song.song_id, get_quality_bitrate(quality))
        message = await _build_track_message(
            render_mode=config.kuwo_track_render_mode,
            media=media,
            quality=quality,
            title=song.name,
            artist=song.artist,
            album=song.album,
        )
    except KuwoUnsupportedFormatError:
        await kw.finish("当前暂不支持该歌曲的文件发送")
    except KuwoTrackError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo track request failed: rid={}, quality={}",
            songs[0].song_id,
            quality.value,
        )
        await kw.finish(
            "下载歌曲文件失败"
            if config.kuwo_track_render_mode is TrackRenderMode.FILE
            else "获取播放链接失败"
        )

    await kw.finish(message)


@kwid.handle()
async def handle_kwid(arp: Arparma) -> None:
    raw_rid = str(arp.all_matched_args.get("rid", "")).strip()
    if not raw_rid:
        await kwid.finish("请输入正确的音乐 ID")

    try:
        rid = normalize_musicrid(raw_rid)
    except ValueError:
        await kwid.finish("请输入正确的音乐 ID")

    config = get_runtime_config()
    try:
        quality = _resolve_command_quality(
            command_name="kwid",
            render_mode=config.kuwo_track_render_mode,
            requested_quality=arp.all_matched_args.get("quality"),
            default_quality=config.kuwo_default_quality,
        )
    except ValueError:
        await kwid.finish("请输入正确的音质参数")

    try:
        media = await get_song_detailed_media(rid, get_quality_bitrate(quality))
        message = await _build_track_message(
            render_mode=config.kuwo_track_render_mode,
            media=media,
            quality=quality,
            title=media.title,
            artist=media.artist,
            album=media.album,
        )
    except KuwoUnsupportedFormatError:
        await kwid.finish("当前暂不支持该歌曲的文件发送")
    except KuwoTrackError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo detailed track request failed: rid={}, quality={}",
            rid,
            quality.value,
        )
        await kwid.finish(
            "下载歌曲文件失败"
            if config.kuwo_track_render_mode is TrackRenderMode.FILE
            else "获取歌曲信息失败"
        )

    await kwid.finish(message)
