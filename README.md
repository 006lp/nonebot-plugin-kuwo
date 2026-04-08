# nonebot-plugin-kuwo

基于 NoneBot2 的酷我音乐插件，当前已完成基础初始化，并实现了搜索、首条直链和按 `rid` 获取完整歌曲信息的第一版能力。

## 当前能力

- 使用 `nonebot-plugin-alconna` 注册 `kwsearch` / `kw搜索`、`kw`、`kwid`
- 在插件入口顶层 `require("nonebot_plugin_alconna")`，并继承其适配器支持列表
- 按照 `COMMAND_START` 解析命令前缀
- 调用酷我搜索接口并返回文本结果
- 支持 `KUWO_SEARCH_RENDER_MODE=image` 时将搜索结果渲染为图片列表
- 将 `MUSICRID` 规范化为纯数字歌曲 ID
- `/kw <关键词>`：搜索第一首歌并返回封面 + 文本直链信息
- `/kwid <rid>`：并发请求直链接口和详情接口，返回封面 + 歌名 + 歌手 + 专辑 + 文本直链信息
- 支持通过 `.env` 热更新以下配置
  - `KUWO_SEARCH_LIMIT`
  - `KUWO_SEARCH_RENDER_MODE`
  - `KUWO_DEFAULT_QUALITY`

## 当前命令

```text
/kwsearch <关键词>
/kw搜索 <关键词>
/kw <关键词>
/kwid <rid>
```

文本模式输出格式：

```text
1. 音乐id 歌曲名-歌手
2. 音乐id 歌曲名-歌手
```

图片模式输出格式：

```text
[搜索结果图片]
```

图片列表中的每首歌会展示：

- 序号
- 音乐 ID
- 歌名
- 歌手
- 专辑
- 时长
- 搜索接口返回的专辑封面

说明：

- 搜索结果图片列表不会为每首歌额外请求封面接口，而是直接使用搜索响应里的 `web_albumpic_short` 拼接完整封面 URL
- 若图片渲染失败，当前会自动回退到文本模式，避免命令直接报错

`/kw` 返回格式：

```text
[封面图片]
歌曲名 - 歌手
专辑：xxx
时长：242s
码率：2000 kbps
直链：http://...
```

`/kwid` 返回格式：

```text
[封面图片]
歌曲名 - 歌手
专辑：xxx
时长：242s
码率：2000 kbps
直链：http://...
```

## 配置示例

参考 [.env.example](./.env.example)：

```dotenv
COMMAND_START=["/"]
KUWO_SEARCH_LIMIT=5
KUWO_SEARCH_RENDER_MODE=text
KUWO_DEFAULT_QUALITY=standard
```

当前支持的 `KUWO_DEFAULT_QUALITY`：

- `standard`
- `exhigh`
- `lossless`
- `hires`
- `hifi`
- `sur`
- `jymaster`

## 开发命令

```bash
uv sync
uv run ruff format .
uv run ruff check . --fix
uv run pytest tests/ -v
```

## 当前限制

- 搜索结果图片渲染依赖 `nonebot-plugin-htmlrender` 与可用的 Playwright 浏览器环境
- `/kw` 直接播放、音乐卡片、自定义 CQ 卡片、语音播放尚未实现

## 许可证
本项目采用 AGPL v3 许可证 - 查看 [LICENSE](./LICENSE) 文件了解详情。
