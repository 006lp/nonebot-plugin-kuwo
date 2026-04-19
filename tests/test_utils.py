from __future__ import annotations

import pytest

from nonebot_plugin_kuwo.utils import (
    format_track_text,
    join_keyword_parts,
    normalize_musicrid,
    strip_url_query,
)


def test_normalize_musicrid() -> None:
    assert normalize_musicrid("MUSIC_553152678") == "553152678"
    assert normalize_musicrid("553152678") == "553152678"


def test_normalize_musicrid_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        normalize_musicrid("KW_553152678")


def test_join_keyword_parts() -> None:
    assert join_keyword_parts(("  hello", "world  ", "")) == "hello world"


def test_strip_url_query() -> None:
    assert strip_url_query("http://example.com/song.flac?bitrate$2000") == (
        "http://example.com/song.flac"
    )


def test_format_track_text() -> None:
    text = format_track_text(
        rid="553152678",
        title="Morning Dew Reflection.wav",
        artist="rionos",
        album="Morning Dew Reflection",
        duration=242,
        bitrate=2000,
        ekey="sample-ekey",
        direct_url="http://example.com/song.flac",
    )

    assert text == (
        "Morning Dew Reflection.wav - rionos\n"
        "专辑：Morning Dew Reflection\n"
        "时长：242s\n"
        "码率：2000 kbps\n"
        "ekey：sample-ekey\n"
        "直链：http://example.com/song.flac"
    )
