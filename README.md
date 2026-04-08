# nonebot-plugin-kuwo

基于 NoneBot2 的酷我音乐插件，当前已完成基础初始化，并实现了搜索、首条直链和按 `rid` 获取直链的第一版能力。

## 当前能力

- 使用 `nonebot-plugin-alconna` 注册 `kwsearch` / `kw搜索`、`kw`、`kwid`
- 在插件入口顶层 `require("nonebot_plugin_alconna")`，并继承其适配器支持列表
- 按照 `COMMAND_START` 解析命令前缀
- 调用酷我搜索接口并返回文本结果
- 将 `MUSICRID` 规范化为纯数字歌曲 ID
- `/kw <关键词>`：搜索第一首歌并返回封面 + 文本直链信息
- `/kwid <rid>`：直接按 `rid` 返回封面 + 文本直链信息
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
歌曲ID：11713652
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

- 图片搜索结果渲染尚未实现，`image` 模式当前会自动回退到文本
- `/kwid` 当前只有 `rid` 时无法补充歌名、歌手、专辑，后续需要额外详情接口
- `/kw` 直接播放、音乐卡片、自定义 CQ 卡片、语音播放尚未实现

## 许可证
本项目采用 AGPL v3 许可证 - 查看 [LICENSE](./LICENSE) 文件了解详情。
