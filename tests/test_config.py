from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from nonebot_plugin_kuwo.config import (
    Config,
    KuwoQuality,
    ListRenderMode,
    TrackRenderMode,
    get_quality_bitrate,
    get_runtime_config,
    resolve_track_quality,
)


def test_get_runtime_config_reads_latest_env(monkeypatch) -> None:
    test_root = Path(f"tests/.tmp-config-{uuid4().hex}")
    test_root.mkdir(parents=True)

    env_file = test_root / ".env"
    env_file.write_text(
        (
            "KUWO_SEARCH_LIMIT=7\n"
            "KUWO_LIST_RENDER_MODE=image\n"
            "KUWO_TRACK_RENDER_MODE=card\n"
            "KUWO_DEFAULT_QUALITY=lossless\n"
            "KUWO_TRACK_CACHE_RETENTION_DAYS=2\n"
            "KUWO_TRACK_CACHE_MAX_SIZE_MB=1536\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("nonebot_plugin_kuwo.config.PROJECT_ROOT", test_root)
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.config.get_plugin_config",
        lambda _: Config(),
    )

    config = get_runtime_config()

    assert config.kuwo_search_limit == 7
    assert config.kuwo_list_render_mode is ListRenderMode.IMAGE
    assert config.kuwo_track_render_mode is TrackRenderMode.CARD
    assert config.kuwo_default_quality.value == "lossless"
    assert config.kuwo_track_cache_retention_days == 2
    assert config.kuwo_track_cache_max_size_mb == 1536
    assert get_quality_bitrate(config.kuwo_default_quality) == "2000kflac"


def test_get_runtime_config_uses_image_list_mode_when_track_mode_is_card(monkeypatch) -> None:
    test_root = Path(f"tests/.tmp-config-{uuid4().hex}")
    test_root.mkdir(parents=True)

    env_file = test_root / ".env"
    env_file.write_text(
        "KUWO_TRACK_RENDER_MODE=card\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("nonebot_plugin_kuwo.config.PROJECT_ROOT", test_root)
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.config.get_plugin_config",
        lambda _: Config(),
    )

    config = get_runtime_config()

    assert config.kuwo_list_render_mode is ListRenderMode.IMAGE
    assert config.kuwo_track_render_mode is TrackRenderMode.CARD


def test_get_runtime_config_keeps_text_list_mode_when_track_mode_is_record(
    monkeypatch,
) -> None:
    test_root = Path(f"tests/.tmp-config-{uuid4().hex}")
    test_root.mkdir(parents=True)

    env_file = test_root / ".env"
    env_file.write_text(
        "KUWO_TRACK_RENDER_MODE=record\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("nonebot_plugin_kuwo.config.PROJECT_ROOT", test_root)
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.config.get_plugin_config",
        lambda _: Config(),
    )

    config = get_runtime_config()

    assert config.kuwo_list_render_mode is ListRenderMode.TEXT
    assert config.kuwo_track_render_mode is TrackRenderMode.RECORD


def test_get_runtime_config_keeps_text_list_mode_when_track_mode_is_file(
    monkeypatch,
) -> None:
    test_root = Path(f"tests/.tmp-config-{uuid4().hex}")
    test_root.mkdir(parents=True)

    env_file = test_root / ".env"
    env_file.write_text(
        "KUWO_TRACK_RENDER_MODE=file\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("nonebot_plugin_kuwo.config.PROJECT_ROOT", test_root)
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.config.get_plugin_config",
        lambda _: Config(),
    )

    config = get_runtime_config()

    assert config.kuwo_list_render_mode is ListRenderMode.TEXT
    assert config.kuwo_track_render_mode is TrackRenderMode.FILE


def test_resolve_track_quality_prefers_requested_quality() -> None:
    quality = resolve_track_quality(KuwoQuality.STANDARD, "lossless")

    assert quality is KuwoQuality.LOSSLESS


def test_resolve_track_quality_raises_on_invalid_quality() -> None:
    with pytest.raises(ValueError):
        resolve_track_quality(KuwoQuality.STANDARD, "not-a-quality")


def test_get_runtime_config_warns_when_track_cache_max_size_below_recommended(
    monkeypatch,
) -> None:
    test_root = Path(f"tests/.tmp-config-{uuid4().hex}")
    test_root.mkdir(parents=True)

    env_file = test_root / ".env"
    env_file.write_text(
        "KUWO_TRACK_CACHE_MAX_SIZE_MB=512\n",
        encoding="utf-8",
    )

    warnings: list[tuple[str, tuple[object, ...]]] = []

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        warnings.append((message, args))

    monkeypatch.setattr("nonebot_plugin_kuwo.config.PROJECT_ROOT", test_root)
    monkeypatch.setattr(
        "nonebot_plugin_kuwo.config.get_plugin_config",
        lambda _: Config(),
    )
    monkeypatch.setattr("nonebot_plugin_kuwo.config.logger.warning", fake_warning)

    config = get_runtime_config()

    assert config.kuwo_track_cache_max_size_mb == 512
    assert warnings == [
        (
            "KUWO_TRACK_CACHE_MAX_SIZE_MB={} is smaller than the recommended minimum "
            "600MB; a single master-quality mflac may temporarily need about 500MB "
            "during decrypt.",
            (512,),
        )
    ]
