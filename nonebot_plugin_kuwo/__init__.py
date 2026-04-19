from __future__ import annotations

from collections.abc import Awaitable, Callable

from arclet.alconna import Alconna, Args, Arparma, MultiVar, Option
from nonebot import get_driver, logger, require
from nonebot.adapters.onebot.v11 import Message
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

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
    download_track_file,
    get_song_detailed_media,
    get_song_media,
    initialize_http_client,
    search_songs,
)
from .models import KuwoDetailedTrackResource, KuwoSearchSong, KuwoTrackResource
from .render import render_search_results
from .utils import build_track_message, join_keyword_parts, normalize_musicrid

require("nonebot_plugin_alconna")

__plugin_meta__ = PluginMetadata(
    name="酷我音乐",
    description="酷我音乐搜索与直链插件",
    usage="/kwsearch <关键词>、/kw <关键词>、/kwid <rid>",
    type="application",
    homepage="https://github.com/006lp/nonebot-plugin-kuwo",
    config=Config,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

kwsearch = None
kw = None
kwid = None
_plugin_initialized = False
_QUALITY_ORDER = {
    KuwoQuality.STANDARD: 0,
    KuwoQuality.EXHIGH: 1,
    KuwoQuality.LOSSLESS: 2,
    KuwoQuality.HIRES: 3,
    KuwoQuality.HIFI: 4,
    KuwoQuality.SUR: 5,
    KuwoQuality.JYMASTER: 6,
}


async def _search_song_candidates(keyword: str, limit: int) -> list[KuwoSearchSong]:
    if not keyword:
        raise RuntimeError("missing keyword")

    try:
        return await search_songs(keyword, limit)
    except KuwoSearchNetworkError as exc:
        logger.opt(exception=exc).warning("Kuwo search request failed: keyword={}", keyword)
        if kwsearch is not None:
            await kwsearch.finish("搜索服务暂时不可用，请稍后再试")
        raise
    except KuwoSearchResponseError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo search response parsing failed: keyword={}",
            keyword,
        )
        if kwsearch is not None:
            await kwsearch.finish("搜索结果解析失败")
        raise


async def _search_song_candidates_by_parts(
    parts: tuple[str, ...] | list[str] | tuple[()],
    limit: int,
) -> list[KuwoSearchSong]:
    keyword = join_keyword_parts(parts)
    if not keyword:
        if kwsearch is not None:
            await kwsearch.finish("请输入搜索关键词")
        raise RuntimeError("missing keyword")
    return await _search_song_candidates(keyword, limit)


async def handle_kwsearch(arp: Arparma) -> None:
    if kwsearch is None:
        raise RuntimeError("kwsearch matcher has not been initialized")

    config = get_runtime_config()
    keyword = join_keyword_parts(arp.all_matched_args.get("keyword", ()))
    logger.info(
        "Received kwsearch command: keyword={}, limit={}, render_mode={}",
        keyword,
        config.kuwo_search_limit,
        config.kuwo_list_render_mode.value,
    )
    songs = await _search_song_candidates_by_parts(
        arp.all_matched_args.get("keyword", ()),
        config.kuwo_search_limit,
    )
    logger.info("kwsearch search completed: keyword={}, song_count={}", keyword, len(songs))

    if not songs:
        await kwsearch.finish("未找到相关歌曲")

    message = await render_search_results(songs, config.kuwo_list_render_mode)
    logger.debug(
        "kwsearch render completed: keyword={}, message_type={}, segment_count={}",
        keyword,
        type(message).__name__,
        len(message) if isinstance(message, Message) else 1,
    )
    if isinstance(message, Message):
        logger.debug(
            "kwsearch message first segment: keyword={}, segment_type={}, file_type={}",
            keyword,
            message[0].type if message else "unknown",
            message[0].data.get("file", "")[:32] if message else "",
        )
    logger.info(
        "Sending kwsearch response: keyword={}, render_mode={}",
        keyword,
        config.kuwo_list_render_mode.value,
    )
    await kwsearch.finish(message)


async def _resolve_command_quality(
    *,
    command_name: str,
    render_mode: TrackRenderMode,
    requested_quality: str | KuwoQuality | None,
    default_quality: KuwoQuality,
    finish: Callable[[str | Message], Awaitable[None]],
) -> KuwoQuality:
    try:
        quality = resolve_track_quality(default_quality, requested_quality)
    except ValueError:
        await finish("请输入正确的音质参数")
        raise RuntimeError("invalid quality")

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

    if (
        render_mode is TrackRenderMode.CARD
        and _QUALITY_ORDER[quality] > _QUALITY_ORDER[KuwoQuality.LOSSLESS]
    ):
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


async def _fetch_track_message(
    *,
    rid: str,
    render_mode: TrackRenderMode,
    quality: KuwoQuality,
    song: KuwoSearchSong | None = None,
) -> str | Message:
    try:
        media = await get_song_media(rid, get_quality_bitrate(quality))
    except KuwoTrackError as exc:
        logger.opt(exception=exc).warning(
            "Kuwo track link request failed: rid={}, quality={}",
            rid,
            quality.value,
        )
        raise

    return await _build_track_message(
        render_mode=render_mode,
        media=media,
        rid=rid,
        title=song.name if song else None,
        artist=song.artist if song else None,
        album=song.album if song else None,
    )


async def _build_track_message(
    *,
    render_mode: TrackRenderMode,
    media: KuwoTrackResource | KuwoDetailedTrackResource,
    rid: str,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
) -> str | Message:
    local_file_path: str | None = None
    if render_mode is TrackRenderMode.FILE:
        local_file_path = str(
            await download_track_file(
                rid=rid,
                direct_url=media.direct_url,
                format_name=media.format,
                bitrate=media.bitrate,
                ekey=media.ekey,
            )
        )

    return build_track_message(
        render_mode=render_mode,
        rid=rid,
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


def _resolve_track_failure_message(
    render_mode: TrackRenderMode,
    *,
    default_message: str,
) -> str:
    if render_mode is TrackRenderMode.FILE:
        return "下载歌曲文件失败"
    return default_message


async def handle_kw(arp: Arparma) -> None:
    if kw is None:
        raise RuntimeError("kw matcher has not been initialized")

    config = get_runtime_config()
    keyword = join_keyword_parts(arp.all_matched_args.get("keyword", ()))
    if not keyword:
        await kw.finish("请输入搜索关键词")

    try:
        songs = await _search_song_candidates(keyword, 1)
    except (KuwoSearchNetworkError, KuwoSearchResponseError):
        await kw.finish("搜索服务暂时不可用，请稍后再试")
    if not songs:
        await kw.finish("未找到相关歌曲")

    first_song = songs[0]
    quality = await _resolve_command_quality(
        command_name="kw",
        render_mode=config.kuwo_track_render_mode,
        requested_quality=arp.all_matched_args.get("quality"),
        default_quality=config.kuwo_default_quality,
        finish=kw.finish,
    )
    try:
        message = await _fetch_track_message(
            rid=first_song.song_id,
            render_mode=config.kuwo_track_render_mode,
            quality=quality,
            song=first_song,
        )
    except KuwoUnsupportedFormatError:
        await kw.finish("当前暂不支持该歌曲的文件发送")
    except KuwoTrackError:
        await kw.finish(
            _resolve_track_failure_message(
                config.kuwo_track_render_mode,
                default_message="获取播放链接失败",
            )
        )
    await kw.finish(message)


async def handle_kwid(arp: Arparma) -> None:
    if kwid is None:
        raise RuntimeError("kwid matcher has not been initialized")

    raw_rid = str(arp.all_matched_args.get("rid", "")).strip()
    if not raw_rid:
        await kwid.finish("请输入正确的音乐ID")

    try:
        rid = normalize_musicrid(raw_rid)
    except ValueError:
        await kwid.finish("请输入正确的音乐ID")

    config = get_runtime_config()
    quality = await _resolve_command_quality(
        command_name="kwid",
        render_mode=config.kuwo_track_render_mode,
        requested_quality=arp.all_matched_args.get("quality"),
        default_quality=config.kuwo_default_quality,
        finish=kwid.finish,
    )
    try:
        media = await get_song_detailed_media(
            rid,
            get_quality_bitrate(quality),
        )
        message = await _build_track_message(
            render_mode=config.kuwo_track_render_mode,
            media=media,
            rid=rid,
            title=media.title,
            artist=media.artist,
            album=media.album,
        )
    except KuwoUnsupportedFormatError:
        await kwid.finish("当前暂不支持该歌曲的文件发送")
    except KuwoTrackError:
        await kwid.finish(
            _resolve_track_failure_message(
                config.kuwo_track_render_mode,
                default_message="获取歌曲信息失败",
            )
        )
    await kwid.finish(message)


def init_plugin() -> None:
    global _plugin_initialized, kwsearch, kw, kwid
    if _plugin_initialized:
        return

    from nonebot_plugin_alconna import on_alconna

    driver = get_driver()
    require("nonebot_plugin_localstore")

    @driver.on_startup
    async def _startup() -> None:
        await initialize_http_client()

    @driver.on_shutdown
    async def _shutdown() -> None:
        await close_http_client()

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
    kwsearch.handle()(handle_kwsearch)
    kw.handle()(handle_kw)
    kwid.handle()(handle_kwid)
    _plugin_initialized = True


try:
    init_plugin()
except ValueError:
    pass
