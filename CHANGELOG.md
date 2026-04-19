# Changelog

## 0.2.0 - 2026-04-19

- 明确记录当前支持的四种单曲输出模式：`text` / `card` / `record` / `file`
- 明确记录 `card` 模式音质上限为 `lossless`
- 明确记录 `record` 模式强制回落到 `standard`
- 明确记录 `.mflac` 通过 Kuwo `ekey` + QMCv2 链路解密为 `.flac` 后发送
- 明确记录 `file` 模式使用 `nonebot-plugin-localstore` 缓存
- 补充真实 `.mflac + ekey` 样本的完整解密验证说明

## 0.1.3 - 2026-04-19

- 为 `/kw` 和 `/kwid` 增加 `-q/--quality` 选项
- `text` / `card` 输出模式接入音质参数
- 新增 `record` 输出模式
- `record` 模式强制使用 `standard` 音质
- 补充 `record` 模式相关命令测试和配置测试

## 0.1.2 - 2026-04-19

- 为 `/kw` 和 `/kwid` 增加 OneBot V11 自定义音乐卡片输出
- 自定义音乐卡片使用音乐直链作为 `url` 与 `audio`
- 新增 `KUWO_TRACK_RENDER_MODE=text|card`
- 搜索列表渲染配置重命名为 `KUWO_LIST_RENDER_MODE=text|image`
- 增加 `KUWO_TRACK_RENDER_MODE=card` 时的 `kwsearch -> image` 默认联动

## 0.1.1 - 2026-04-09

- 为 `kwsearch` 增加基于 `nonebot-plugin-htmlrender` 的图片列表渲染
- 搜索结果模型新增 `web_albumpic_short` 并支持直接拼接封面 URL
- 图片列表改为直接复用搜索接口封面信息
- 图片渲染失败时自动回退为文本模式
- 为 `kwsearch` 图片链路补充 `debug` / `info` 日志

## 0.1.0 - 2026-04-08

- 使用 `uv` 初始化项目并补齐基础依赖
- 新增 `nonebot_plugin_kuwo` 插件骨架
- 实现 `kwsearch` / `kw搜索` 搜索命令
- 实现 `kw <关键词>` 首条歌曲直链命令
- 实现 `kwid <rid>` 详情与直链命令
- 新增搜索响应模型、异步数据源和文本渲染逻辑
- 新增音质到 `br` 的映射与运行时配置读取
- 增加并发获取封面与单曲信息的链路
- 按 NoneBot 官方发布规范补齐 `require("nonebot_plugin_alconna")` 与适配器继承元数据
- 增加基础单元测试和 nonebug 命令测试
