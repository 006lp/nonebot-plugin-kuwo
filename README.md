# nonebot-plugin-kuwo

基于 NoneBot2 的酷我音乐插件，当前已实现搜索、首条直链和按 `rid` 获取歌曲详情，并支持 OneBot V11 自定义音乐卡片输出。

## 当前能力

- 使用 `nonebot-plugin-alconna` 注册 `kwsearch` / `kw搜索`、`kw`、`kwid`
- 插件入口在顶层先执行 `require("nonebot_plugin_alconna")`
- 命令显式跟随 NoneBot `COMMAND_START`
- 所有命令均 `block=True`，阻止事件继续传播
- `kwsearch` 支持文本列表和图片列表
- `/kw <关键词>` 支持返回首条歌曲的文本直链或自定义音乐卡片
- `/kwid <rid>` 支持返回歌曲详情的文本直链或自定义音乐卡片

## 命令

```text
/kwsearch <关键词>
/kw搜索 <关键词>
/kw <关键词>
/kwid <rid>
```

## 输出说明

### `kwsearch`

- `text` 模式：返回 `序号. 音乐id 歌曲名-歌手`
- `image` 模式：返回带封面的图片列表

### `/kw`

- `text` 模式：返回封面 + 歌曲信息 + 直链
- `card` 模式：返回 OneBot V11 自定义音乐卡片
  - `url` 使用音乐直链
  - `audio` 使用音乐直链
  - `title` 使用歌曲名
  - `content` 使用 `歌手 | 专辑`
  - `image` 使用封面

### `/kwid`

- `text` 模式：返回封面 + 歌曲信息 + 直链
- `card` 模式：返回 OneBot V11 自定义音乐卡片

## 配置

```dotenv
COMMAND_START=["/"]
LOG_LEVEL=INFO
KUWO_SEARCH_LIMIT=5
KUWO_LIST_RENDER_MODE=text
KUWO_TRACK_RENDER_MODE=text
KUWO_DEFAULT_QUALITY=standard
```

### 配置项说明

- `KUWO_SEARCH_LIMIT`
  - 搜索结果数量，默认 `5`
- `KUWO_LIST_RENDER_MODE`
  - `kwsearch` 列表渲染模式
  - 可选值：`text`、`image`
- `KUWO_TRACK_RENDER_MODE`
  - `/kw` 与 `/kwid` 单曲输出模式
  - 可选值：`text`、`card`
- `KUWO_DEFAULT_QUALITY`
  - 单曲直链默认音质
  - 可选值：`standard`、`exhigh`、`lossless`、`hires`、`hifi`、`sur`、`jymaster`

### 默认联动规则

- 如果没有显式配置 `KUWO_LIST_RENDER_MODE`
- 且 `KUWO_TRACK_RENDER_MODE=card`
- 那么 `kwsearch` 默认使用 `image`

## 图片列表封面策略

- `kwsearch` 图片模式不会为每一首歌额外请求封面接口
- 直接复用搜索接口返回的 `web_albumpic_short`
- 完整封面地址通过 `http://img1.kwcdn.kuwo.cn/star/albumcover/` 拼接得到

## 开发命令

```bash
uv sync
uv run ruff format .
uv run ruff check . --fix
uv run pytest tests/ -v
```

## 当前限制

- 暂未实现语音 `record` 发送
- 暂未实现官方音乐卡片 / 自定义 CQ 卡片以外的播放形态
- 暂未实现单用户调用次数限制

## 许可证

本项目采用 AGPL v3 许可证，详见 [LICENSE](./LICENSE)。
