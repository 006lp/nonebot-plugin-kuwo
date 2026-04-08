from __future__ import annotations

from arclet.alconna import Alconna, Args, Arparma, MultiVar
from nonebot import get_driver, logger, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot_plugin_alconna import on_alconna

from .config import Config, get_runtime_config
from .data_source import (
    KuwoSearchNetworkError,
    KuwoSearchResponseError,
    close_http_client,
    initialize_http_client,
    search_songs,
)
from .render import render_search_results
from .utils import join_keyword_parts

require("nonebot_plugin_alconna")

__plugin_meta__ = PluginMetadata(
    name="酷我音乐搜索",
    description="酷我音乐搜索插件",
    usage="/kwsearch <关键词> 或 /kw搜索 <关键词>",
    type="application",
    homepage="https://github.com/006lp/nonebot-plugin-kuwo",
    config=Config,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

kwsearch = None
_plugin_initialized = False


async def handle_kwsearch(arp: Arparma) -> None:
    if kwsearch is None:
        raise RuntimeError("kwsearch matcher has not been initialized")

    keyword = join_keyword_parts(arp.all_matched_args.get("keyword", ()))
    if not keyword:
        await kwsearch.finish("请输入搜索关键词")

    config = get_runtime_config()
    try:
        songs = await search_songs(keyword, config.kuwo_search_limit)
    except KuwoSearchNetworkError as exc:
        logger.opt(exception=exc).warning("酷我搜索请求失败: keyword={}", keyword)
        await kwsearch.finish("搜索服务暂时不可用，请稍后再试")
    except KuwoSearchResponseError as exc:
        logger.opt(exception=exc).warning("酷我搜索结果解析失败: keyword={}", keyword)
        await kwsearch.finish("搜索结果解析失败")

    if not songs:
        await kwsearch.finish("未找到相关歌曲")

    message = await render_search_results(songs, config.kuwo_search_render_mode)
    await kwsearch.finish(message)


def init_plugin() -> None:
    global _plugin_initialized, kwsearch
    if _plugin_initialized:
        return

    driver = get_driver()

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
    kwsearch.handle()(handle_kwsearch)
    _plugin_initialized = True


try:
    init_plugin()
except ValueError:
    pass
