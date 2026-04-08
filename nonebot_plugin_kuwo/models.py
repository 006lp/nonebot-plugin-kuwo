from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .utils import normalize_musicrid, strip_url_query


class KuwoSearchSong(BaseModel):
    model_config = ConfigDict(extra="ignore")

    musicrid: str = Field(alias="MUSICRID")
    name: str = Field(alias="NAME")
    artist: str = Field(alias="ARTIST")
    album: str = Field(alias="ALBUM", default="")
    duration: int = Field(alias="DURATION")

    @field_validator("duration", mode="before")
    @classmethod
    def parse_duration(cls, value: int | str) -> int:
        return int(value)

    @property
    def song_id(self) -> str:
        return normalize_musicrid(self.musicrid)


class KuwoSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: int = Field(alias="TOTAL", default=0)
    songs: list[KuwoSearchSong] = Field(alias="abslist")

    @field_validator("total", mode="before")
    @classmethod
    def parse_total(cls, value: int | str) -> int:
        return int(value)


class KuwoTrackLinkData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bitrate: int = Field(alias="bitrate")
    duration: int = Field(alias="duration")
    format: str = Field(alias="format")
    rid: int = Field(alias="rid")
    url: str = Field(alias="url")

    @field_validator("bitrate", "duration", "rid", mode="before")
    @classmethod
    def parse_numeric_fields(cls, value: int | str) -> int:
        return int(value)

    @property
    def direct_url(self) -> str:
        return strip_url_query(self.url)


class KuwoTrackLinkResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: int = Field(alias="code")
    data: KuwoTrackLinkData = Field(alias="data")
    msg: str = Field(alias="msg", default="")

    @field_validator("code", mode="before")
    @classmethod
    def parse_code(cls, value: int | str) -> int:
        return int(value)


class KuwoTrackResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rid: str
    bitrate: int
    duration: int
    direct_url: str
    cover_url: str | None = None
