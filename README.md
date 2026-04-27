# nonebot-plugin-kuwo

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

基于 NoneBot2 的酷我音乐插件，面向 NapCat / OneBot V11 使用场景，提供搜索、直链、音乐卡片、语音和文件发送能力。

## 功能

- `kwsearch <关键词>`
  - 返回搜索结果列表
  - 支持 `text` / `image`
- `kw搜索 <关键词>`
  - `kwsearch` 中文别名
- `kw <关键词> [-q/--quality <quality>]`
  - 搜索后直接取第一首歌
  - 支持 `text` / `card` / `record` / `file`
- `kwid <rid> [-q/--quality <quality>]`
  - 直接通过 `rid` 获取歌曲
  - 支持 `text` / `card` / `record` / `file`


## 安装

### nb-cli

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

## 配置

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

配置项说明：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `KUWO_SEARCH_LIMIT` | `5` | 搜索结果条数，范围 `1-10` |
| `KUWO_LIST_RENDER_MODE` | `text` | 搜索列表模式，支持 `text` / `image` |
| `KUWO_TRACK_RENDER_MODE` | `text` | 单曲输出模式，支持 `text` / `card` / `record` / `file` |
| `KUWO_DEFAULT_QUALITY` | `standard` | 默认音质 |
| `KUWO_TRACK_CACHE_RETENTION_DAYS` | `1` | 文件缓存保留天数，`0` 表示关闭按天清理 |
| `KUWO_TRACK_CACHE_MAX_SIZE_MB` | `1024` | 文件缓存总大小上限，`0` 表示关闭按大小清理 |

音质枚举：

- `standard`
- `exhigh`
- `lossless`
- `hires`
- `hifi`
- `sur`
- `jymaster`

特殊规则：

- `KUWO_TRACK_RENDER_MODE=card` 且未显式设置 `KUWO_LIST_RENDER_MODE` 时，搜索列表默认切到 `image`
- `record` 模式强制回落到 `standard`
- `card` 模式音质上限固定为 `lossless`
- `KUWO_TRACK_CACHE_MAX_SIZE_MB` 小于 `600` 时仅记录警告，不阻止启动

## 使用

### 搜索列表

`kwsearch` / `kw搜索` 当前支持两种输出：

- `text`
  - 每行格式：`序号. 音乐id 歌曲名-歌手`
- `image`
  - 使用 `nonebot-plugin-htmlrender` 生成图片列表
  - 直接复用搜索接口返回的 `web_albumpic_short`
  - 渲染失败时自动回退到文本

### 单曲输出

`kw` / `kwid` 当前支持四种输出：

- `text`
  - 有封面时发送 `图片 + 文本`
  - 文本包含：歌曲名、歌手、专辑、时长、码率、直链
  - 若接口返回 `ekey`，文本中会额外带上 `ekey`
- `card`
  - 发送自定义音乐卡片
  - `url` 和 `audio` 都使用真实直链
- `record`
  - 发送语音段
  - 始终使用 `standard`
- `file`
  - 下载到本地缓存后发送文件段
  - `.mflac` 会先解密成可播放的 `.flac`

### 音质参数

`kw` 和 `kwid` 都支持：

```text
-q
--quality
```

示例：

```text
/kw Summer Pockets -q lossless
/kwid 553152678 --quality exhigh
```

## 文件缓存与 `.mflac`

`file` 模式使用 `nonebot-plugin-localstore` 的插件缓存目录，并在其下维护 `tracks/` 子目录。

普通可直接发送的格式：

- `mp3`
- `flac`
- `aac`
- `ogg`
- `wav`

缓存策略：

- 相同 `rid + bitrate` 优先复用缓存
- 缓存命中会刷新文件时间
- 默认按 `1` 天和 `1024MB` 双重策略清理
- 两个值都设为 `0` 时，不做自动清理

`.mflac` 流程：

1. 下载原始 `.mflac`
2. 使用 Kuwo 返回的 `ekey`
3. 提取 QMC 原始密钥
4. 推导最终 QMCv2 密钥
5. 本地解密为 `.flac`
6. 发送解密后的文件
7. 删除中间 `.mflac`

## 开发

项目强制使用 `uv`。

```bash
uv sync
uv run maturin develop --release
```

常用命令：

```bash
uv run ruff check .
uv run pytest tests -q -p no:cacheprovider
cargo fmt --all
```

说明：

- 发布版 wheel 会自带原生扩展 `_qmc_rs`
- 源码开发或本地调试需要先执行 `maturin develop`

## 项目结构

```text
nonebot_plugin_kuwo/
├── __init__.py
├── config.py
├── data_source.py
├── models.py
├── qmc.py
├── render.py
└── utils.py
src/
└── qmc.rs
tests/
```

## 鸣谢

- [LiuLang](mailto:gsushzhsosgsu@gmail.com) 提供 DES 解密算法思路
- [UnblockNeteaseMusic/server](https://github.com/UnblockNeteaseMusic/server) 提供音乐直链接口

## 许可证

本项目使用 [AGPL-3.0](LICENSE) 许可证。
