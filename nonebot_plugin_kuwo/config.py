from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from nonebot import get_plugin_config, logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SearchRenderMode(str, Enum):
    TEXT = "text"
    IMAGE = "image"


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


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    kuwo_search_limit: int = Field(default=5, alias="KUWO_SEARCH_LIMIT", ge=1, le=10)
    kuwo_search_render_mode: SearchRenderMode = Field(
        default=SearchRenderMode.TEXT,
        alias="KUWO_SEARCH_RENDER_MODE",
    )
    kuwo_default_quality: KuwoQuality = Field(
        default=KuwoQuality.STANDARD,
        alias="KUWO_DEFAULT_QUALITY",
    )

    @field_validator("kuwo_search_render_mode", mode="before")
    @classmethod
    def normalize_render_mode(
        cls, value: SearchRenderMode | str
    ) -> SearchRenderMode | str:
        if isinstance(value, str):
            return value.lower()
        return value

    @field_validator("kuwo_default_quality", mode="before")
    @classmethod
    def normalize_default_quality(cls, value: KuwoQuality | str) -> KuwoQuality | str:
        if isinstance(value, str):
            return value.lower()
        return value


def _load_dotenv_values() -> dict[str, str]:
    env_files = [PROJECT_ROOT / ".env"]
    environment = os.getenv("ENVIRONMENT")
    if environment:
        env_files.append(PROJECT_ROOT / f".env.{environment}")

    values: dict[str, str] = {}
    for env_file in env_files:
        if not env_file.is_file():
            continue
        for key, value in dotenv_values(env_file).items():
            if value is not None:
                values[key] = value
    return values


def _load_system_env_values() -> dict[str, str]:
    keys = {
        "KUWO_SEARCH_LIMIT",
        "KUWO_SEARCH_RENDER_MODE",
        "KUWO_DEFAULT_QUALITY",
    }
    return {key: os.environ[key] for key in keys if key in os.environ}


def _base_config_data() -> dict[str, Any]:
    return get_plugin_config(Config).model_dump(by_alias=True)


def get_runtime_config() -> Config:
    data = {
        **_base_config_data(),
        **_load_dotenv_values(),
        **_load_system_env_values(),
    }
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        logger.opt(exception=exc).warning("酷我插件配置解析失败，已回退到当前运行配置")
        return get_plugin_config(Config)


def get_quality_bitrate(quality: KuwoQuality) -> str:
    return QUALITY_TO_BR[quality]
