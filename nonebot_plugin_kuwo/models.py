from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .utils import normalize_musicrid


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
