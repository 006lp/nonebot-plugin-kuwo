# Changelog

## 0.2.3 - 2026-04-28

- 调整 GitHub Actions 触发条件，`CI` 响应分支 push / PR，但忽略 `v*` tag push，避免发布时同一提交触发重复 CI
- 修复跨平台 CI 中 `nonebot-plugin-htmlrender` 通过 `playwright` 导入时缺少 `greenlet` 的问题，改为正式跨平台运行时依赖

## 0.2.2 - 2026-04-28

- 命令测试改为适配器无关，不再要求测试环境安装 `nonebot-adapter-onebot`
- 按 NoneBot 官方插件规范重构插件入口，顶层固定 `require("nonebot_plugin_alconna")`，并继承其适配器支持列表
- 运行时彻底移除对 `nonebot-adapter-onebot` 的直接依赖，消息发送统一改用 `uniseg`
- 配置统一改为 `get_plugin_config(Config)`，去掉手动读 `.env` 的历史思路
- 配置与数据模型清理为兼容 Pydantic v1 的写法，移除无意义的兼容分支和 `ConfigDict` 风格写法
- `nonebot-plugin-localstore` 改为惰性解析并缓存一次插件缓存目录，避免导入期误调用
- `kwsearch` / `kw` / `kwid` 的用户提示文本统一修正为 UTF-8 正常内容
- 测试基建重写，修复插件在测试收集阶段被提前导入的问题
- 测试环境显式隔离 `localstore` 路径，并在 nonebug 中移除 htmlrender 的 Playwright 生命周期钩子

## 0.2.1 - 2026-04-22

- 新增 `KUWO_TRACK_CACHE_RETENTION_DAYS` 与 `KUWO_TRACK_CACHE_MAX_SIZE_MB`，为 `file` 模式缓存提供按时间和按大小的自动清理策略
- `file` 模式缓存命中时会刷新文件时间，容量清理按最旧文件优先淘汰
- `.mflac` 解密成功后会立即删除中间缓存，减少双份占用
- `0` 值可分别禁用按天数或按大小清理，两个值都为 `0` 时完全关闭自动清理

## 0.2.0 - 2026-04-20

- 为 Rust 原生扩展补充 `_qmc_rs.pyi` 与 `py.typed`，修复 Pylance 对 `_qmc_rs` 的未知导入符号提示
- 强化 CI / Release 工作流，补齐 Rust 格式检查与锁文件约束
- Release 工作流显式固定 Linux `manylinux2014`，并使用 `--compatibility pypi`
- 补充 Rust 原生 `derive_qmc_key` 与 `decrypt_qmc_bytes` 的直接样本测试
- 将 `nonebot_plugin_kuwo/qmc.py` 的核心算法整体迁移为 Rust 扩展
- 使用 `PyO3 + maturin` 暴露原生扩展模块 `nonebot_plugin_kuwo._qmc_rs`
- 保留 Python 包装层 `nonebot_plugin_kuwo/qmc.py`，维持原有 Python API 形状
- `decrypt_mflac_file` 现在由 Rust 原生代码执行，并在原生层释放 GIL
- `pyproject.toml` 切换为 `maturin` build backend，并增加开发依赖 `maturin`
- 更新 `.gitignore`，忽略 Rust 构建产物与本地扩展文件
- 新增 GitHub Actions 工作流，用于 CI 和跨平台 PyPI 发布

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
