<div align="center">
    <a href="https://nonebot.dev/">
    <img src="https://github.com/Misty02600/nonebot-plugin-template/releases/download/assets/NoneBotPlugin.png" width="310" alt="logo"></a>

## ✨ *基于 NoneBot2 的酷我音乐插件* ✨

[![LICENSE](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.html)
[![python](https://img.shields.io/badge/python-3.10+-blue.svg?logo=python&logoColor=white)](https://www.python.org)
[![Adapters](https://img.shields.io/badge/Adapters-OneBot%20v11%20%2F%20NapCat-blue)](#-支持适配器)
<br/>

[![uv](https://img.shields.io/badge/package%20manager-uv-black?logo=uv)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/badge/code%20style-ruff-black?logo=ruff)](https://github.com/astral-sh/ruff)
[![rust](https://img.shields.io/badge/native-Rust-orange?logo=rust)](https://www.rust-lang.org)

</div>

## 📖 介绍

`nonebot-plugin-kuwo` 是一个面向 NoneBot2 的酷我音乐插件，当前已经实现：

- 搜索歌曲列表：`kwsearch` / `kw搜索`
- 获取关键词搜索结果中的第一首歌：`kw`
- 通过 `rid` 直接获取单曲：`kwid`
- 面向 NapCat / OneBot V11 输出 `text`、`image`、`card`、`record`、`file`
- 对 `.mflac` 文件执行本地解密，转换为可播放的 `.flac`

插件当前明确坚持“一条命令只做一件事”，不引入等待用户继续输入序号的多轮选歌会话。

## ✨ 功能概览

- 命令解析：`nonebot-plugin-alconna`
- 搜索列表渲染：`text` / `image`
- 单曲输出：`text` / `card` / `record` / `file`
- 网络请求：`httpx.AsyncClient`
- 文件缓存：`nonebot-plugin-localstore`
- 图片渲染：`nonebot-plugin-htmlrender`
- 原生解密：Rust + PyO3 + maturin

## 🔌 支持适配器

当前项目按 OneBot V11 协议实现，并优先面向 NapCat 场景优化：

- [OneBot V11](https://github.com/botuniverse/onebot-11)
- [NapCat](https://github.com/NapNeko/NapCatQQ)

当前已覆盖的消息形态：

- 图片消息段
- 语音消息段 `record`
- 文件消息段 `file`
- 自定义音乐卡片 `music/custom`

## 📦 安装

> [!IMPORTANT]
> 普通用户安装已发布 wheel 时不需要额外构建 Rust。
> 只有源码开发、测试或从源码安装时，才需要本地 Rust 工具链。

<details open>
<summary>使用 nb-cli 安装</summary>

在 NoneBot2 项目根目录执行：

```bash
nb plugin install nonebot-plugin-kuwo --upgrade
```

使用 PyPI 源：

```bash
nb plugin install nonebot-plugin-kuwo --upgrade -i https://pypi.org/simple
```

</details>

<details>
<summary>使用包管理器安装</summary>

推荐使用 `uv`：

```bash
uv add nonebot-plugin-kuwo
```

安装 GitHub 仓库主分支：

```bash
uv add git+https://github.com/006lp/nonebot-plugin-kuwo@main
```

如果你使用其他包管理器，也可以选择：

```bash
pdm add nonebot-plugin-kuwo
```

```bash
poetry add nonebot-plugin-kuwo
```

安装后，在 NoneBot2 项目的 `pyproject.toml` 中加入：

```toml
plugins = ["nonebot_plugin_kuwo"]
```

</details>

## ⚙️ 配置

插件运行时会按需读取配置：

- 每次命令执行时重新读取 `.env`
- 如果设置了 `ENVIRONMENT`，会额外叠加 `.env.{ENVIRONMENT}`
- 进程环境变量优先级高于 `.env`

> [!NOTE]
> 当 `KUWO_TRACK_RENDER_MODE=card` 且没有显式配置 `KUWO_LIST_RENDER_MODE` 时，
> `kwsearch` 会自动回落到 `image` 模式，以匹配卡片场景下更合适的搜索列表展示。

### 配置项

| 配置项 | 必填 | 默认值 | 说明 |
| :-- | :--: | :--: | :-- |
| `KUWO_SEARCH_LIMIT` | 否 | `5` | 搜索结果条数，当前限制范围为 `1-10` |
| `KUWO_LIST_RENDER_MODE` | 否 | `text` | 搜索列表渲染模式：`text` / `image` |
| `KUWO_TRACK_RENDER_MODE` | 否 | `text` | 单曲输出模式：`text` / `card` / `record` / `file` |
| `KUWO_DEFAULT_QUALITY` | 否 | `standard` | 默认音质：`standard` / `exhigh` / `lossless` / `hires` / `hifi` / `sur` / `jymaster` |
| `KUWO_TRACK_CACHE_RETENTION_DAYS` | 否 | `1` | `file` 模式缓存按天数清理；`0` 表示禁用按时长清理 |
| `KUWO_TRACK_CACHE_MAX_SIZE_MB` | 否 | `1024` | `file` 模式缓存总大小上限；`0` 表示禁用按大小清理，不建议低于 `600` |

### 配置示例

```dotenv
COMMAND_START=["/"]
LOG_LEVEL=INFO
KUWO_SEARCH_LIMIT=5
KUWO_LIST_RENDER_MODE=text
KUWO_TRACK_RENDER_MODE=text
KUWO_DEFAULT_QUALITY=standard
KUWO_TRACK_CACHE_RETENTION_DAYS=1
KUWO_TRACK_CACHE_MAX_SIZE_MB=1024
```

## 🎵 使用

### 命令列表

> [!IMPORTANT]
> 所有命令均显式启用 `use_cmd_start=True` 与 `block=True`，会跟随 NoneBot2 的 `COMMAND_START`。

| 命令 | 参数 | 说明 |
| :-- | :-- | :-- |
| `kwsearch <关键词>` | 关键词 | 返回搜索结果列表 |
| `kw搜索 <关键词>` | 关键词 | `kwsearch` 的中文别名 |
| `kw <关键词> [-q/--quality <quality>]` | 关键词，可选音质 | 只取搜索结果中的第一首歌 |
| `kwid <rid> [-q/--quality <quality>]` | 音乐 ID，可选音质 | 通过 `rid` 直接查询单曲 |

补充说明：

- `kwsearch` 只返回搜索结果，不进入多轮选歌会话
- 非法音质参数会直接报错，不继续请求远程接口

### 搜索列表输出

`kwsearch` / `kw搜索` 当前支持：

- `text`
  - 返回格式：`序号. 音乐id 歌曲名-歌手`
- `image`
  - 使用 `nonebot-plugin-htmlrender` 渲染搜索图片
  - 直接复用搜索接口返回的 `web_albumpic_short` 拼接封面
  - 渲染失败时自动回退到文本模式

### 单曲输出

`kw` / `kwid` 当前支持：

- `text`
  - 如果有封面，则发送 `image + text`
  - 文本包含：歌名、歌手、专辑、时长、码率、直链
  - 如果直链接口返回 `ekey`，会一并显示
- `card`
  - 发送 OneBot V11 自定义音乐卡片
  - `url` 与 `audio` 都使用音乐直链，方便桌面端直接下载
- `record`
  - 发送 OneBot V11 `record` 消息段
  - 直接使用远程音频地址，不走本地下载
- `file`
  - 下载可播放文件到本地缓存目录后，再发送 OneBot V11 `file` 消息段
  - 如果源格式是 `.mflac`，会先本地解密成 `.flac`

### 音质规则

- `/kw` 与 `/kwid` 都支持 `-q/--quality`
- 未传音质时，使用 `KUWO_DEFAULT_QUALITY`
- `text` / `file` 使用最终解析后的音质请求远程接口
- `card` 支持显式传入音质，但最终上限固定为 `lossless`
- `record` 无论默认值还是显式传参，都会强制回落到 `standard`
- `record` / `card` 的音质回落只写日志，不额外向用户发送提示消息

## 🗂️ 文件模式与 `.mflac`

普通可播放格式当前支持：

- `mp3`
- `flac`
- `aac`
- `ogg`
- `wav`

文件缓存说明：

- 缓存目录来自 `nonebot-plugin-localstore`
- 子目录为 `tracks/`
- 相同 `rid + bitrate` 优先复用已缓存文件
- 缓存命中时会刷新文件时间，用于近似 LRU 清理
- 默认按 `1` 天和 `1024MB` 双重策略自动清理
- `KUWO_TRACK_CACHE_RETENTION_DAYS=0` 表示禁用按天数清理
- `KUWO_TRACK_CACHE_MAX_SIZE_MB=0` 表示禁用按大小清理
- 两个值都设为 `0` 时，不做自动缓存清理
- 不建议将 `KUWO_TRACK_CACHE_MAX_SIZE_MB` 设低于 `600`，单个母带 `.mflac` 加解密过程可能临时占用约 `500MB`

`.mflac` 当前处理流程：

1. 下载原始 `.mflac`
2. 使用 Kuwo 返回的 `ekey`
3. 兼容 Kuwo `kuwodes` 解密流程，提取 QMC 原始密钥
4. 推导最终 QMC 密钥
5. 本地解密为可播放的 `.flac`
6. 发送解密后的 `file` 消息段
7. 解密成功后立即删除中间 `.mflac`，避免长期双份占用

## 🦀 Rust 解密扩展

当前 `qmc` 核心已经整体迁移到 Rust，并通过 `PyO3 + maturin` 暴露给 Python。

项目结构中的关键文件：

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

## 🧪 开发

> [!IMPORTANT]
> 源码开发、测试和本地调试需要 Rust 工具链。
> 已发布 wheel 安装场景不需要再手动构建 `_qmc_rs`。

### 本地准备

```bash
uv sync
uv run maturin develop --release
```

### 常用命令

```bash
uv run ruff check .

uv run pytest tests/ -q -p no:cacheprovider

cargo fmt --all
```

## ⚠️ 当前限制

- 暂未实现单用户调用频率限制

## 🗺️ 后续计划

- 补齐真实 NapCat 环境下的端到端验证
- 视需要继续优化 Rust 解密核心的吞吐表现
- 细化 PyPI 发布矩阵与版本发布规范

## 🙏 致谢

- [LiuLang](mailto:gsushzhsosgsu@gmail.com) 提供 Kuwo `ekey` 所需的 DES 解密算法
- [UnblockNeteaseMusic](https://github.com/UnblockNeteaseMusic/server) 提供音乐直链接口

## 📄 许可证

本项目采用 AGPL v3，详见仓库根目录下的 [LICENSE](./LICENSE)。
