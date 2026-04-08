from __future__ import annotations

import pytest

from nonebot_plugin_kuwo.utils import join_keyword_parts, normalize_musicrid


def test_normalize_musicrid() -> None:
    assert normalize_musicrid("MUSIC_553152678") == "553152678"
    assert normalize_musicrid("553152678") == "553152678"


def test_normalize_musicrid_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        normalize_musicrid("KW_553152678")


def test_join_keyword_parts() -> None:
    assert join_keyword_parts(("  hello", "world  ", "")) == "hello world"
