# nonebot-plugin-kuwo

基于 NoneBot2 的酷我音乐插件，当前已实现搜索列表、首条歌曲直链、按 `rid` 查询详情，以及面向 NapCat / OneBot V11 的多种消息输出。

## 当前能力

- 命令：`kwsearch` / `kw搜索` / `kw` / `kwid`
- 命令解析：`nonebot-plugin-alconna`
- 搜索列表输出：`text` / `image`
- 单曲输出：`text` / `card` / `record` / `file`
- 直链请求：`https://nmobi.kuwo.cn/mobi.s`
- 详情请求：`http://musicpay.kuwo.cn/music.pay`
- 文件缓存：`nonebot-plugin-localstore`
- `.mflac` 文件解密：由 Rust + PyO3 扩展负责，兼容 Kuwo `ekey` + QMCv2 流程，落地为可播放的 `.flac`

## 命令

命令前缀跟随 NoneBot2 的 `COMMAND_START`。下面示例默认使用 `/`。

```text
/kwsearch <关键词>
/kw搜索 <关键词>
/kw <关键词> [-q|--quality <quality>]
/kwid <rid> [-q|--quality <quality>]
```

补充说明：

- `kwsearch` 只返回搜索列表，不进入多轮会话。
- `kw` 只取搜索结果的第一首歌。
- `kwid` 支持 `123456` 和 `MUSIC_123456` 两种输入。
- 所有命令均显式启用 `use_cmd_start=True` 和 `block=True`。

## 输出模式

### `kwsearch`

- `text`
  - 返回格式：`序号. 音乐id 歌曲名-歌手`
- `image`
  - 使用 `nonebot-plugin-htmlrender` 渲染图片列表
  - 直接复用搜索接口返回的 `web_albumpic_short` 拼接封面
  - 如果渲染失败，会回退到文本模式

### `kw` / `kwid`

- `text`
  - 如果有封面，发送 `image + text`
  - 文本包含：歌名、歌手、专辑、时长、码率、直链
  - 如果直链接口返回了 `ekey`，会一并显示
- `card`
  - 发送 OneBot V11 自定义音乐卡片
  - `url` 和 `audio` 都使用音乐直链，方便桌面端直接下载
- `record`
  - 发送 OneBot V11 `record` 消息段
  - 使用音乐直链，不走本地下载
- `file`
  - 将可播放文件下载到本地缓存目录后发送 OneBot V11 `file` 消息段
  - 如果源格式是 `.mflac`，会先本地解密成 `.flac`

## 配置

```dotenv
COMMAND_START=["/"]
LOG_LEVEL=INFO
KUWO_SEARCH_LIMIT=5
KUWO_LIST_RENDER_MODE=text
KUWO_TRACK_RENDER_MODE=text
KUWO_DEFAULT_QUALITY=standard
```

### 配置项

- `KUWO_SEARCH_LIMIT`
  - 搜索结果条数，默认 `5`
  - 当前限制范围是 `1-10`
- `KUWO_LIST_RENDER_MODE`
  - 搜索列表渲染模式：`text` / `image`
- `KUWO_TRACK_RENDER_MODE`
  - 单曲输出模式：`text` / `card` / `record` / `file`
- `KUWO_DEFAULT_QUALITY`
  - 默认音质：`standard` / `exhigh` / `lossless` / `hires` / `hifi` / `sur` / `jymaster`

### 配置读取规则

- 每次命令执行时重新读取 `.env`
- 如果设置了 `ENVIRONMENT`，也会叠加读取 `.env.{ENVIRONMENT}`
- 进程环境变量优先级高于 `.env`
- 如果未显式设置 `KUWO_LIST_RENDER_MODE`，且 `KUWO_TRACK_RENDER_MODE=card`，则 `kwsearch` 默认使用 `image`

## 音质规则

- `/kw` 和 `/kwid` 都支持 `-q/--quality`
- 未传 `-q/--quality` 时，使用 `KUWO_DEFAULT_QUALITY`
- `text` / `file` 模式按最终解析出的音质请求远程接口
- `card` 模式支持 `-q/--quality`，但最终上限固定为 `lossless`
- `record` 模式无论默认值还是显式传参，都会强制回落到 `standard`
- `record` / `card` 的音质回落只记录到日志，不额外给用户发送提示消息

## Rust 解密扩展

当前 `qmc` 核心已经整体迁移到 Rust，并通过 `PyO3 + maturin` 暴露给 Python：

- Rust crate：`Cargo.toml`
- PyO3 入口：`src/lib.rs`
- 解密实现：`src/qmc.rs`
- Python 包装层：`nonebot_plugin_kuwo/qmc.py`

### 当前暴露的 Python API

- `kuwo_base64_decrypt(value: str) -> str`
- `extract_qmc_raw_key_from_ekey(ekey: str) -> bytes`
- `derive_qmc_key(raw_key: bytes | str) -> bytes`
- `decrypt_qmc_bytes(data: bytes, raw_key: bytes | str, offset: int = 0) -> bytes`
- `decrypt_mflac_file(source_path: Path, target_path: Path, ekey: str, chunk_size: int = 65536) -> Path`

### 设计说明

- Python 侧只保留轻量包装层，不再承载核心算法
- CPU 密集型解密逻辑在 Rust 中执行，并脱离 GIL
- 构建产物作为包内私有扩展模块 `nonebot_plugin_kuwo._qmc_rs`
- 包内额外提供 `_qmc_rs.pyi` 与 `py.typed`，便于 Pylance / 类型检查器识别原生扩展签名
- 采用 `abi3-py310`，便于生成跨 Python 3.10+ 的平台 wheel

## `file` 模式与 `.mflac`

- 普通可播放格式目前支持：`mp3` / `flac` / `aac` / `ogg` / `wav`
- 文件缓存目录来自 `nonebot-plugin-localstore` 的插件缓存目录，子目录为 `tracks/`
- 相同 `rid + bitrate` 会优先复用已缓存文件

`.mflac` 处理流程：

1. 下载原始 `.mflac`
2. 使用 Kuwo 返回的 `ekey`
3. 兼容 Kuwo `kuwodes` 解密流程，提取 QMC 原始密钥
4. 推导最终 QMC 密钥
5. 本地解密为可播放的 `.flac`
6. 发送解密后的 `file` 消息段

## 开发要求

本项目现在需要 Rust 工具链才能完整开发和测试。

本地准备：

```bash
uv sync
uv run maturin develop --release
```

日常命令：

```bash
uv run ruff check .
uv run pytest tests/ -q -p no:cacheprovider
cargo fmt --all
```

## 发布

仓库已预留 GitHub Actions 流程：

- CI：`.github/workflows/ci.yml`
- PyPI 发布：`.github/workflows/release.yml`

发布策略：

- 通过 `maturin-action` 构建 abi3 wheel
- 覆盖 Linux / Windows / macOS
- 使用 `pypa/gh-action-pypi-publish` 进行 PyPI 发布
- 建议使用 PyPI Trusted Publishing

## 当前限制

- 暂未实现单用户调用频率限制
- 暂未实现文件缓存清理策略

## 后续计划

- 评估 `file` 模式缓存生命周期与清理策略
- 补齐真实 NapCat 环境下的端到端验证
- 视需要继续优化 Rust 解密核心的吞吐表现
- 细化 PyPI 发布矩阵与版本发布规范

## 许可证

本项目采用 AGPL v3，详见仓库根目录下的 `LICENSE`。
