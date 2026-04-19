# Changelog

## 0.1.3 - 2026-04-19

- 为 `/kw` 与 `/kwid` 增加 `-q/--quality` 选项，当前已接入 `text` / `card` 输出模式
- 在 `text` / `card` 模式下，命令行传入的 `-q/--quality` 会覆盖 `KUWO_DEFAULT_QUALITY`
- 补充 `/kw` 带空格关键词并跟随 `-q/--quality` 的命令解析测试，确保参数不会吞掉关键词

## 0.1.2 - 2026-04-19

- 为 `/kw` 与 `/kwid` 增加 OneBot V11 自定义音乐卡片输出
- 自定义音乐卡片的 `url` 与 `audio` 均使用音乐直链，方便桌面端直接下载
- 新增 `KUWO_TRACK_RENDER_MODE=text|card` 配置项
- 将 `kwsearch` 列表渲染配置重命名为 `KUWO_LIST_RENDER_MODE=text|image`
- 新增联动规则：当 `KUWO_TRACK_RENDER_MODE=card` 且未显式配置列表模式时，`kwsearch` 默认使用图片列表
- 重构单曲消息构建逻辑，统一文本输出与卡片输出入口
- 补充 `/kw`、`/kwid` 卡片模式测试，以及配置兼容与默认联动测试

## 0.1.1 - 2026-04-09

- 为 `kwsearch` / `kw搜索` 增加基于 `nonebot-plugin-htmlrender` 的图片列表渲染
- 搜索结果模型新增 `web_albumpic_short` 字段，并支持直接拼接搜索列表封面 URL
- 搜索结果图片模式改为直接复用搜索接口封面信息，不再为每一首歌单独请求封面接口
- 新增 `kwsearch` 图片模式命令测试，补充现有命令测试的 UTF-8 清理与断言稳定性
- 图片渲染失败时回退到文本模式，避免直接影响正常会话
- 为 `kwsearch` 图片链路补充 `debug` / `info` 级别排障日志，并补充 `LOG_LEVEL=DEBUG` 的使用说明

## 0.1.0 - 2026-04-08

- 使用 `uv` 初始化并补齐 NoneBot2、OneBot、Alconna、httpx、pytest、nonebug 等依赖
- 新增 `nonebot_plugin_kuwo` 插件包骨架
- 实现 `kwsearch` / `kw搜索` 搜索命令的最小闭环
- 实现 `kw <关键词>` 首条歌曲直链命令
- 实现 `kwid <rid>` 直链与封面查询命令
- 新增酷我搜索响应模型、异步数据源和文本结果渲染回退
- 新增音质等级到 `br` 的映射与 `.env` 热更新读取
- 新增并发获取封面与播放直链的逻辑
- `/kwid` 改为并发请求直链与 `music.pay` 详情接口，补齐歌名、歌手、专辑和封面
- 新增 `.env` 配置热读取能力
- 按 NoneBot 官方发布文档补齐 `require("nonebot_plugin_alconna")` 与适配器继承元数据
- 补充基础单元测试与 nonebug 命令测试
