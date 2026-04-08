from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from nonebot_plugin_kuwo.config import Config, SearchRenderMode, get_runtime_config


def test_get_runtime_config_reads_latest_env(monkeypatch) -> None:
    test_root = Path(f"tests/.tmp-config-{uuid4().hex}")
    test_root.mkdir(parents=True)

    env_file = test_root / ".env"
    env_file.write_text(
        "KUWO_SEARCH_LIMIT=7\nKUWO_SEARCH_RENDER_MODE=image\nKUWO_DEFAULT_QUALITY=320kmp3\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("nonebot_plugin_kuwo.config.PROJECT_ROOT", test_root)
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.config.get_plugin_config",
        lambda _: Config(),
    )

    config = get_runtime_config()

    assert config.kuwo_search_limit == 7
    assert config.kuwo_search_render_mode is SearchRenderMode.IMAGE
    assert config.kuwo_default_quality == "320kmp3"
