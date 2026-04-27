from __future__ import annotations

import importlib

import pytest


def import_config_module():
    return importlib.import_module("nonebot_plugin_kuwo.config")


def test_get_runtime_config_returns_plugin_config(monkeypatch: pytest.MonkeyPatch) -> None:
    config_module = import_config_module()
    expected = config_module.Config(
        kuwo_search_limit=7,
        kuwo_list_render_mode=config_module.ListRenderMode.IMAGE,
        kuwo_track_render_mode=config_module.TrackRenderMode.CARD,
        kuwo_default_quality=config_module.KuwoQuality.LOSSLESS,
        kuwo_track_cache_retention_days=2,
        kuwo_track_cache_max_size_mb=1536,
    )
    monkeypatch.setattr(config_module, "get_plugin_config", lambda _: expected)

    config = config_module.get_runtime_config()

    assert config is expected
    assert config.kuwo_search_limit == 7
    assert config.kuwo_list_render_mode is config_module.ListRenderMode.IMAGE
    assert config.kuwo_track_render_mode is config_module.TrackRenderMode.CARD
    assert config.kuwo_default_quality is config_module.KuwoQuality.LOSSLESS
    assert config.kuwo_track_cache_retention_days == 2
    assert config.kuwo_track_cache_max_size_mb == 1536
    assert config_module.get_quality_bitrate(config.kuwo_default_quality) == "2000kflac"


def test_config_uses_image_list_mode_when_track_mode_is_card_by_default() -> None:
    config_module = import_config_module()
    config = config_module.Config(kuwo_track_render_mode="card")

    assert config.kuwo_list_render_mode is config_module.ListRenderMode.IMAGE
    assert config.kuwo_track_render_mode is config_module.TrackRenderMode.CARD


def test_config_keeps_explicit_text_list_mode_when_track_mode_is_card() -> None:
    config_module = import_config_module()
    config = config_module.Config(
        kuwo_track_render_mode="card",
        kuwo_list_render_mode="text",
    )

    assert config.kuwo_list_render_mode is config_module.ListRenderMode.TEXT
    assert config.kuwo_track_render_mode is config_module.TrackRenderMode.CARD


def test_config_keeps_text_list_mode_when_track_mode_is_record() -> None:
    config_module = import_config_module()
    config = config_module.Config(kuwo_track_render_mode="record")

    assert config.kuwo_list_render_mode is config_module.ListRenderMode.TEXT
    assert config.kuwo_track_render_mode is config_module.TrackRenderMode.RECORD


def test_config_keeps_text_list_mode_when_track_mode_is_file() -> None:
    config_module = import_config_module()
    config = config_module.Config(kuwo_track_render_mode="file")

    assert config.kuwo_list_render_mode is config_module.ListRenderMode.TEXT
    assert config.kuwo_track_render_mode is config_module.TrackRenderMode.FILE


def test_resolve_track_quality_prefers_requested_quality() -> None:
    config_module = import_config_module()
    quality = config_module.resolve_track_quality(
        config_module.KuwoQuality.STANDARD,
        "lossless",
    )

    assert quality is config_module.KuwoQuality.LOSSLESS


def test_resolve_track_quality_raises_on_invalid_quality() -> None:
    config_module = import_config_module()
    with pytest.raises(ValueError):
        config_module.resolve_track_quality(
            config_module.KuwoQuality.STANDARD,
            "not-a-quality",
        )


def test_get_runtime_config_warns_when_track_cache_max_size_below_recommended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_module = import_config_module()
    warnings: list[tuple[str, tuple[object, ...]]] = []
    config_module._warned_cache_size_limits.clear()

    def fake_warning(message: str, *args: object, **kwargs: object) -> None:
        warnings.append((message, args))

    monkeypatch.setattr(
        config_module,
        "get_plugin_config",
        lambda _: config_module.Config(kuwo_track_cache_max_size_mb=512),
    )
    monkeypatch.setattr(config_module.logger, "warning", fake_warning)

    config = config_module.get_runtime_config()

    assert config.kuwo_track_cache_max_size_mb == 512
    assert warnings == [
        (
            "KUWO_TRACK_CACHE_MAX_SIZE_MB={} is smaller than the recommended minimum "
            "600MB; a single master-quality mflac may temporarily need about 500MB "
            "during decrypt.",
            (512,),
        )
    ]
