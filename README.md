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
- `.mflac` 文件解密：兼容 Kuwo `ekey` + QMCv2 流程，落地为可播放的 `.flac`

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

补充说明：

- `.mflac` 解密当前是纯 Python 实现，处理大文件时会比较慢
- 现阶段没有做并行解密优化，因为这是典型 CPU 密集任务，普通多线程收益很有限

## 开发命令

```bash
uv sync
uv run ruff format .
uv run ruff check . --fix
uv run pytest tests/ -v
```

## 当前限制

- 暂未实现单用户调用频率限制
- 暂未实现文件缓存清理策略

## 后续计划

- 评估 `file` 模式缓存生命周期与清理策略
- 评估是否要为 `.mflac` 解密引入更高性能的原生实现
- 评估 `file` 模式未来是否扩展为“上传可播放文件”的能力
- 补齐真实 NapCat 环境下的端到端验证

## 许可证

本项目采用 AGPL v3，详见 [LICENSE](./LICENSE)。
