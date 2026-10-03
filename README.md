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

> [!WARNING]
> **Breaking Changes（自 0.3.0 起）**
>
> 由于上游 `nonebot-plugin-htmlrender` 0.8+ 引入了破坏性更新，本插件**自 `0.3.0` 起，搜索结果图片改用 SVG 模板 + 内置 Rust `resvg` 渲染**，移除对 `nonebot-plugin-htmlrender`、Playwright 和 Chromium 的依赖。
>
> `KUWO_LIST_RENDER_MODE=image` 的使用方式保持不变，无需再设置 `RENDER_BACKEND=playwright`。插件默认自带霞鹜文楷等宽字体，可通过 `KUWO_RENDER_FONT_FILES` / `KUWO_RENDER_FONT_DIRS` 自定义，详见[配置](#配置)。
>
> **如果仍希望使用 `nonebot-plugin-htmlrender` 渲染，请固定使用本插件 `0.2.7` 版本**，对应源码见 [legacy/0.2.7 分支](https://github.com/006lp/nonebot-plugin-kuwo/tree/legacy/0.2.7)。该分支从 `v0.2.7` 标签创建，htmlrender 依赖限定为 `>=0.7.1,<0.8`：
>
> ```bash
> uv add "nonebot-plugin-kuwo==0.2.7"
> ```

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

<details>
<summary>使用包管理器安装</summary>

推荐使用 `uv`：

```bash
uv add nonebot-plugin-kuwo
```

安装 GitHub 仓库主分支（当前为 `0.3.0a2` 预发布版本）：

```bash
uv add git+https://github.com/006lp/nonebot-plugin-kuwo@main
```

安装保留 htmlrender 渲染的 [legacy/0.2.7 分支](https://github.com/006lp/nonebot-plugin-kuwo/tree/legacy/0.2.7)：

```bash
uv add git+https://github.com/006lp/nonebot-plugin-kuwo@legacy/0.2.7
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
[tool.nonebot]
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
# KUWO_TRACK_PROXY_URL=http://127.0.0.1:7890
KUWO_TRACK_CACHE_RETENTION_DAYS=1
KUWO_TRACK_CACHE_MAX_SIZE_MB=1024
# KUWO_RENDER_FONT_FILES=[]
# KUWO_RENDER_FONT_DIRS=[]
```

配置项说明：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `KUWO_SEARCH_LIMIT` | `5` | 搜索结果条数，范围 `1-10` |
| `KUWO_LIST_RENDER_MODE` | `text` | 搜索列表模式，支持 `text` / `image` |
| `KUWO_TRACK_RENDER_MODE` | `text` | 单曲输出模式，支持 `text` / `card` / `record` / `file` |
| `KUWO_DEFAULT_QUALITY` | `standard` | 默认音质 |
| `KUWO_TRACK_PROXY_URL` | 未配置 | 由于版权相关问题，海外用户请求歌曲直链时需要使用境内 HTTP/HTTPS 代理，例如 `http://user:pass@127.0.0.1:7890` |
| `KUWO_TRACK_CACHE_RETENTION_DAYS` | `1` | 文件缓存保留天数，`0` 表示关闭按天清理 |
| `KUWO_TRACK_CACHE_MAX_SIZE_MB` | `1024` | 文件缓存总大小上限，`0` 表示关闭按大小清理 |
| `KUWO_RENDER_FONT_FILES` | 未配置 | 自定义图片字体文件列表，优先于字体目录和系统字体 |
| `KUWO_RENDER_FONT_DIRS` | 未配置 | 自定义图片字体目录列表，优先于系统字体 |

图片列表由 Rust 原生扩展内置的 `resvg` 渲染，不需要 Playwright / Chromium。插件随 wheel 和源码包分发霞鹜文楷等宽 `LXGWWenKaiMono-Regular.ttf`（字体族 `LXGW WenKai Mono`），默认使用该字体，精简 Docker 镜像无需额外安装中文字体。

字体配置使用 JSON 数组，例如 `KUWO_RENDER_FONT_FILES=["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]`。存在有效的自定义文件或目录时，使用自定义来源替代默认字体；第一个加载成功的字体族作为默认，文件按配置顺序优先于目录，系统字体用于缺字回退。未配置或所有配置路径不存在时使用内置字体。目录内请放置可用的 TTF / OTF / TTC 字体；更新字体后重启 NoneBot 以刷新字体缓存。没有可用字体或原生渲染失败时，搜索列表会自动回退到文本并记录原因。升级后可移除仅为本插件设置的 `RENDER_BACKEND=playwright`。

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
- `KUWO_TRACK_PROXY_URL` 只代理歌曲直链接口，不代理搜索、封面、详情和文件下载
- 歌曲直链接口使用 `https://changenotice.kuwo.cn/mobi.s`，沿用 `rid` / `br` 等请求参数

## 使用

### 搜索列表

`kwsearch` / `kw搜索` 当前支持两种输出：

- `text`
  - 每行格式：`序号. 音乐id 歌曲名-歌手`
- `image`
  - 使用 Rust 原生扩展（`resvg`）把搜索列表渲染成 PNG
  - 复用搜索接口的 `web_albumpic_short`，并发下载封面后以内嵌图片渲染
  - 封面下载超过 5 MiB、尺寸超过单边 4096px / 总计 4194304 像素、格式不支持或解码失败时使用矢量占位图
  - 并发搜索的图片任务排队执行，原生渲染在线程中运行；画布上限为 8388608 像素
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
  - `/kw` 与 `/kwid` 的封面均优先取自歌曲详情的 `albumPic`；`/kw` 获取详情封面失败或没有封面时复用搜索结果封面，不影响音频直链获取
- `record`
  - 发送语音段
  - 始终使用 `standard`
- `file`
  - 下载到本地缓存后发送文件段
  - `.mflac` 会先解密成可播放的 `.flac`
  - 上传文件名使用 `[quality]歌曲名 - 歌手.扩展名`，`quality` 为最终生效音质，例如 `[lossless]Summer - rionos.flac`

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
- 单个歌曲文件下载上限为 `512 MiB`，超限会停止下载并清理临时文件
- 下载和封面请求禁用 HTTP 内容压缩，压缩响应会被拒绝，避免解压后超出资源限额
- 缓存路径必须位于插件缓存目录中，清理时跳过符号链接；下载取消或失败时清理 `.part` 文件
- `.mflac` 解密在线程中执行；取消时先等待原生任务结束，再释放文件操作锁并清理临时文件

`.mflac` 流程：

1. 下载原始 `.mflac`
2. 使用 Kuwo 返回的 `ekey`
3. 提取 QMC 原始密钥
4. 推导最终 QMCv2 密钥
5. 本地解密为 `.flac`
6. 发送解密后的文件
7. 删除中间 `.mflac`

## 反馈问题

提交 Issue 前请先搜索已有反馈，并按模板提供插件版本、NoneBot / 适配器 / 协议端版本、相关配置、触发命令和脱敏后的 DEBUG 日志。

## 开发

项目强制使用 `uv`。

当前版本 `0.3.0a2` 的本地验证环境为 Python `3.13.16` / Rust `1.99.0`，插件支持 Python `>=3.10`，原生扩展使用 `abi3-py310`。Python 使用 PEP 440 版本 `0.3.0a2`，Cargo 使用等价的 SemVer 版本 `0.3.0-alpha2`。
构建工具使用 `maturin>=1.15.0,<2.0`，Rust 绑定使用 `pyo3 0.29.3`；Release 工作流固定使用 maturin `1.15.0`。

```bash
uv sync --dev --locked
uv run maturin develop --release --locked
```

更新依赖后需要重新构建原生扩展：

```bash
uv lock --upgrade
cargo update
uv sync --dev --locked
uv run maturin develop --release --locked
```

常用命令：

```bash
uv run ruff check .
uv run pytest tests -q -p no:cacheprovider
cargo fmt --all --check
```

说明：

- 发布版 wheel 会自带原生扩展 `_qmc_rs`
- 源码开发或本地调试需要先执行 `maturin develop`

## 项目结构

```text
nonebot_plugin_kuwo/
├── _native.py
├── __init__.py
├── config.py
├── data_source.py
├── files.py
├── fonts/
│   ├── LXGWWenKaiMono-Regular.ttf
│   └── LXGWWenKai-OFL-License.txt
├── models.py
├── qmc.py
├── render.py
└── utils.py
src/
├── qmc.rs
└── render.rs
tests/
```

接口请求和 HTTP 客户端集中在 `data_source.py`，缓存、下载与解密集中在 `files.py`；QMC 回归测试通过 `tests/test_qmc.py` 调用原生扩展，Rust 实现文件不内嵌测试模块。

命令注册、参数读取和流程编排保留在 `__init__.py`，通过 Alconna 的 `Arparma` 获取解析结果、通过 `UniMessage` 构建跨适配器消息。HTTP 客户端初始化和关闭函数直接注册到 NoneBot 的启动与关闭钩子，导入阶段不创建客户端。开发约定参考 [NoneBot 插件发布规范](https://nonebot.dev/docs/developer/plugin-publishing)和 [Alconna 响应器文档](https://nonebot.dev/docs/best-practice/alconna/matcher)。

模型的数字字段由 Pydantic 统一校验，兼容整数与数字字符串；空值或畸形数据会转换为插件的接口响应异常。原生扩展按需加载，接口签名统一维护在 `_qmc_rs.pyi`。缓存与图片渲染共享取消等待逻辑，确保后台原生任务结束后才释放各自的操作锁；模块仅按这些明确职责划分。

## 鸣谢

- [LiuLang](mailto:gsushzhsosgsu@gmail.com) 提供 DES 解密算法思路
- [UnblockNeteaseMusic/server](https://github.com/UnblockNeteaseMusic/server) 提供音乐直链接口

## 许可证

本项目使用 [AGPL-3.0](LICENSE) 许可证。

内置的 [霞鹜文楷](https://github.com/lxgw/LxgwWenKai) 等宽字体使用 [SIL Open Font License 1.1](nonebot_plugin_kuwo/fonts/LXGWWenKai-OFL-License.txt)，字体文件与许可证一起分发。
