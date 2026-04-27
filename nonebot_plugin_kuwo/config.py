from __future__ import annotations

from enum import Enum
from typing import Any

from nonebot import get_plugin_config, logger
from nonebot.compat import field_validator, model_validator
from pydantic import BaseModel, Field


class ListRenderMode(str, Enum):
    TEXT = "text"
    IMAGE = "image"


class TrackRenderMode(str, Enum):
    TEXT = "text"
    CARD = "card"
    RECORD = "record"
    FILE = "file"


class KuwoQuality(str, Enum):
    STANDARD = "standard"
    EXHIGH = "exhigh"
    LOSSLESS = "lossless"
    HIRES = "hires"
    HIFI = "hifi"
    SUR = "sur"
    JYMASTER = "jymaster"


QUALITY_TO_BR = {
    KuwoQuality.STANDARD: "128kmp3",
    KuwoQuality.EXHIGH: "320kmp3",
    KuwoQuality.LOSSLESS: "2000kflac",
    KuwoQuality.HIRES: "4000kflac",
    KuwoQuality.HIFI: "20201kmflac",
    KuwoQuality.SUR: "20501kmflac",
    KuwoQuality.JYMASTER: "20900kmflac",
}

_warned_cache_size_limits: set[int] = set()


def _normalize_enum_input(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


class Config(BaseModel):
    kuwo_search_limit: int = Field(default=5, ge=1, le=10)
    kuwo_list_render_mode: ListRenderMode = ListRenderMode.TEXT
    kuwo_track_render_mode: TrackRenderMode = TrackRenderMode.TEXT
    kuwo_default_quality: KuwoQuality = KuwoQuality.STANDARD
    kuwo_track_cache_retention_days: int = Field(default=1, ge=0)
    kuwo_track_cache_max_size_mb: int = Field(default=1024, ge=0)

    @model_validator(mode="before")
    @classmethod
    def apply_card_list_default(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        track_mode = _normalize_enum_input(data.get("kuwo_track_render_mode"))

        if track_mode in {TrackRenderMode.CARD, TrackRenderMode.CARD.value} and (
            "kuwo_list_render_mode" not in data
        ):
            data["kuwo_list_render_mode"] = ListRenderMode.IMAGE.value
        return data

    @field_validator("kuwo_list_render_mode", mode="before")
    @classmethod
    def normalize_list_render_mode(
        cls, value: ListRenderMode | str
    ) -> ListRenderMode | str:
        return _normalize_enum_input(value)

    @field_validator("kuwo_track_render_mode", mode="before")
    @classmethod
    def normalize_track_render_mode(
        cls, value: TrackRenderMode | str
    ) -> TrackRenderMode | str:
        return _normalize_enum_input(value)

    @field_validator("kuwo_default_quality", mode="before")
    @classmethod
    def normalize_default_quality(cls, value: KuwoQuality | str) -> KuwoQuality | str:
        return _normalize_enum_input(value)


def get_runtime_config() -> Config:
    config = get_plugin_config(Config)
    max_size_mb = config.kuwo_track_cache_max_size_mb
    if 0 < max_size_mb < 600 and max_size_mb not in _warned_cache_size_limits:
        logger.warning(
            "KUWO_TRACK_CACHE_MAX_SIZE_MB={} is smaller than the recommended minimum "
            "600MB; a single master-quality mflac may temporarily need about 500MB "
            "during decrypt.",
            max_size_mb,
        )
        _warned_cache_size_limits.add(max_size_mb)
    return config


def parse_quality(value: str | KuwoQuality | None) -> KuwoQuality | None:
    if value is None:
        return None
    if isinstance(value, KuwoQuality):
        return value
    normalized = value.strip().lower()
    if not normalized:
        return None
    return KuwoQuality(normalized)


def resolve_track_quality(
    default_quality: KuwoQuality,
    requested_quality: str | KuwoQuality | None = None,
) -> KuwoQuality:
    return parse_quality(requested_quality) or default_quality


def get_quality_bitrate(quality: KuwoQuality) -> str:
    return QUALITY_TO_BR[quality]
