from __future__ import annotations

from nonebot.compat import field_validator
from pydantic import BaseModel, Field

from .utils import normalize_musicrid, strip_url_query

SEARCH_COVER_BASE_URL = "http://img1.kwcdn.kuwo.cn/star/albumcover/"


class KuwoSearchSong(BaseModel):
    musicrid: str = Field(alias="MUSICRID")
    name: str = Field(alias="NAME")
    artist: str = Field(alias="ARTIST")
    album: str = Field(alias="ALBUM", default="")
    duration: int = Field(alias="DURATION")
    web_album_cover_short: str = Field(alias="web_albumpic_short", default="")

    @field_validator("musicrid")
    @classmethod
    def validate_musicrid(cls, value: str) -> str:
        normalize_musicrid(value)
        return value

    @field_validator("web_album_cover_short", mode="before")
    @classmethod
    def normalize_cover_path(cls, value: str | None) -> str:
        if value is None:
            return ""
        return value.strip()

    @property
    def song_id(self) -> str:
        return normalize_musicrid(self.musicrid)

    @property
    def album_cover_url(self) -> str | None:
        if not self.web_album_cover_short:
            return None
        return f"{SEARCH_COVER_BASE_URL}{self.web_album_cover_short.lstrip('/')}"


class KuwoSearchResponse(BaseModel):
    total: int = Field(alias="TOTAL", default=0)
    songs: list[KuwoSearchSong] = Field(alias="abslist")


class KuwoTrackLinkData(BaseModel):
    bitrate: int
    duration: int
    format: str
    ekey: str | None = None
    rid: int
    url: str

    @property
    def direct_url(self) -> str:
        return strip_url_query(self.url)


class KuwoTrackLinkResponse(BaseModel):
    code: int
    data: KuwoTrackLinkData
    msg: str = ""


class KuwoTrackDetail(BaseModel):
    song_id: int = Field(alias="id")
    name: str
    artist: str = ""
    album: str = ""
    cover_url: str | None = Field(alias="albumPic", default=None)

    @field_validator("cover_url", mode="before")
    @classmethod
    def normalize_cover_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cover_url = value.strip()
        return cover_url or None


class KuwoTrackDetailResponse(BaseModel):
    errorcode: int
    errormsg: str = ""
    result: str = ""
    songs: list[KuwoTrackDetail] = Field(default_factory=list)


class KuwoTrackResource(BaseModel):
    rid: str
    format: str
    ekey: str | None = None
    bitrate: int
    duration: int
    direct_url: str
    cover_url: str | None = None


class KuwoDetailedTrackResource(KuwoTrackResource):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
