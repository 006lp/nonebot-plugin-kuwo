# Changelog

## 0.1.0 - 2026-04-08

- 使用 `uv` 初始化并补齐 NoneBot2、OneBot、Alconna、httpx、pytest、nonebug 等依赖
- 新增 `nonebot_plugin_kuwo` 包插件骨架
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
