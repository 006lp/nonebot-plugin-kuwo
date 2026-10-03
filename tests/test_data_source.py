from __future__ import annotations

import importlib
import re
from copy import deepcopy

import httpx
import pytest
import respx


def import_config_module():
    return importlib.import_module("nonebot_plugin_kuwo.config")


def import_data_source_module():
    return importlib.import_module("nonebot_plugin_kuwo.data_source")


SEARCH_RESPONSE = {
    "TOTAL": "1",
    "abslist": [
        {
            "MUSICRID": "MUSIC_553152678",
            "NAME": "Morning Dew Reflection.wav",
            "ARTIST": "rionos&Kangseoha&Kim Yoon",
            "ALBUM": "Morning Dew Reflection",
            "DURATION": "182",
        }
    ],
}

TRACK_RESPONSE = {
    "code": 200,
    "data": {
        "bitrate": 2000,
        "duration": 242,
        "format": "flac",
        "rid": 11713652,
        "url": "http://example.com/song.flac?bitrate$2000&format$flac",
    },
    "locationid": "1",
    "msg": "ok",
}

DETAIL_RESPONSE = {
    "Reason": "",
    "errorcode": 0,
    "errormsg": "MusicPay_OK",
    "result": "ok",
    "songs": [
        {
            "album": "Summer Pockets REFLECTION BLUE Original SoundTrack",
            "albumPic": "http://example.com/album.jpg",
            "artist": "VISUAL ARTS&Key Sounds Label&rionos",
            "duration": 410,
            "id": 320490745,
            "name": "ポケットをふくらませて ～Sea, you again～",
        }
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_search_songs_success() -> None:
    data_source = import_data_source_module()
    route = respx.get(data_source.SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json=SEARCH_RESPONSE)
    )

    songs = await data_source.search_songs("Morning Dew Reflection", 5)

    assert route.called
    assert "x-forwarded-for" not in route.calls.last.request.headers
    assert len(songs) == 1
    assert songs[0].song_id == "553152678"
    assert songs[0].artist == "rionos&Kangseoha&Kim Yoon"

    await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_search_songs_enforces_limit_on_remote_results() -> None:
    data_source = import_data_source_module()
    payload = {**SEARCH_RESPONSE, "abslist": SEARCH_RESPONSE["abslist"] * 12}
    respx.get(data_source.SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )

    try:
        songs = await data_source.search_songs("Morning Dew Reflection", 5)
        assert len(songs) == 5
    finally:
        await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_search_songs_raises_on_invalid_payload() -> None:
    data_source = import_data_source_module()
    respx.get(data_source.SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json={"foo": "bar"})
    )

    with pytest.raises(data_source.KuwoSearchResponseError):
        await data_source.search_songs("Morning Dew Reflection", 5)

    await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("numeric_strings", [False, True])
async def test_get_song_media_returns_direct_url_and_cover(
    numeric_strings: bool,
) -> None:
    data_source = import_data_source_module()
    payload = deepcopy(TRACK_RESPONSE)
    if numeric_strings:
        payload["code"] = str(payload["code"])
        for field in ("bitrate", "duration", "rid"):
            payload["data"][field] = str(payload["data"][field])
    track_route = respx.get(data_source.TRACK_API_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )
    detail_payload = deepcopy(DETAIL_RESPONSE)
    detail_payload["songs"][0]["id"] = 11713652
    respx.get(data_source.DETAIL_API_URL).mock(
        return_value=httpx.Response(200, json=detail_payload)
    )

    media = await data_source.get_song_media("11713652", "2000kflac")

    assert data_source.TRACK_API_URL == "https://changenotice.kuwo.cn/mobi.s"
    assert track_route.called
    request = track_route.calls.last.request
    assert "x-forwarded-for" not in request.headers
    assert request.url.params["user"]
    assert re.fullmatch(r"[a-z0-9]{16}", request.url.params["user"])
    assert media.rid == "11713652"
    assert media.format == "flac"
    assert media.bitrate == 2000
    assert media.duration == 242
    assert media.direct_url == "http://example.com/song.flac"
    assert media.cover_url == "http://example.com/album.jpg"

    await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_search_and_id_resources_share_detail_cover() -> None:
    data_source = import_data_source_module()
    track = deepcopy(TRACK_RESPONSE)
    track["data"]["rid"] = 652507745
    detail = deepcopy(DETAIL_RESPONSE)
    detail["songs"][0].update(
        id=652507745,
        name="Otherside",
        albumPic="http://img1.kuwo.cn/star/albumcover/120/s4s13/34/357706223.jpg",
    )
    respx.get(data_source.TRACK_API_URL).mock(
        return_value=httpx.Response(200, json=track)
    )
    respx.get(data_source.DETAIL_API_URL).mock(
        return_value=httpx.Response(200, json=detail)
    )
    try:
        search_media = await data_source.get_song_media("652507745", "128kmp3")
        id_media = await data_source.get_song_detailed_media("652507745", "128kmp3")
        assert (
            search_media.cover_url
            == id_media.cover_url
            == detail["songs"][0]["albumPic"]
        )
    finally:
        await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("kind", ["network", "json", "schema", "empty"])
async def test_song_media_keeps_audio_when_detail_cover_is_unavailable(
    kind: str,
) -> None:
    data_source = import_data_source_module()
    respx.get(data_source.TRACK_API_URL).mock(
        return_value=httpx.Response(200, json=TRACK_RESPONSE)
    )
    route = respx.get(data_source.DETAIL_API_URL)
    if kind == "network":
        route.mock(side_effect=httpx.ConnectError("unavailable"))
    elif kind == "json":
        route.mock(return_value=httpx.Response(200, text="not json"))
    elif kind == "schema":
        route.mock(return_value=httpx.Response(200, json={}))
    else:
        payload = deepcopy(DETAIL_RESPONSE)
        payload["songs"][0]["albumPic"] = None
        route.mock(return_value=httpx.Response(200, json=payload))
    try:
        media = await data_source.get_song_media("11713652", "2000kflac")
        assert media.direct_url == "http://example.com/song.flac"
        assert media.cover_url is None
    finally:
        await data_source.close_http_client()


@pytest.mark.asyncio
async def test_get_song_link_uses_configured_proxy_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_source = import_data_source_module()
    config_module = import_config_module()
    proxy_url = "http://user:pass@127.0.0.1:7890"
    captured_proxy_urls: list[str] = []
    captured_requests: list[tuple[str, dict[str, str]]] = []

    class FakeClient:
        async def get(self, url: str, params: dict[str, str]) -> httpx.Response:
            captured_requests.append((url, params))
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(200, json=TRACK_RESPONSE, request=request)

    async def fake_get_track_proxy_http_client(
        configured_proxy_url: str,
    ) -> FakeClient:
        captured_proxy_urls.append(configured_proxy_url)
        return FakeClient()

    monkeypatch.setattr(
        data_source,
        "get_runtime_config",
        lambda: config_module.Config(kuwo_track_proxy_url=proxy_url),
    )
    monkeypatch.setattr(
        data_source,
        "get_track_proxy_http_client",
        fake_get_track_proxy_http_client,
    )

    track = await data_source.get_song_link("11713652", "2000kflac")

    assert captured_proxy_urls == [proxy_url]
    assert len(captured_requests) == 1
    assert captured_requests[0][0] == data_source.TRACK_API_URL
    assert captured_requests[0][1]["rid"] == "11713652"
    assert captured_requests[0][1]["br"] == "2000kflac"
    assert track.direct_url == "http://example.com/song.flac"


def test_redact_proxy_url_hides_credentials() -> None:
    data_source = import_data_source_module()

    assert (
        data_source.redact_proxy_url("http://user:pass@127.0.0.1:7890")
        == "http://***@127.0.0.1:7890"
    )
    assert (
        data_source.redact_proxy_url("https://127.0.0.1:7890")
        == "https://127.0.0.1:7890"
    )


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("numeric_strings", [False, True])
async def test_get_song_detailed_media_returns_track_detail(
    numeric_strings: bool,
) -> None:
    data_source = import_data_source_module()
    payload = deepcopy(DETAIL_RESPONSE)
    if numeric_strings:
        payload["errorcode"] = str(payload["errorcode"])
        payload["songs"][0]["id"] = str(payload["songs"][0]["id"])
    respx.get(data_source.TRACK_API_URL).mock(
        return_value=httpx.Response(200, json=TRACK_RESPONSE)
    )
    respx.get(data_source.DETAIL_API_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )

    media = await data_source.get_song_detailed_media("320490745", "2000kflac")

    assert media.rid == "320490745"
    assert media.format == "flac"
    assert media.bitrate == 2000
    assert media.duration == 242
    assert media.direct_url == "http://example.com/song.flac"
    assert media.title == "ポケットをふくらませて ～Sea, you again～"
    assert media.artist == "VISUAL ARTS&Key Sounds Label&rionos"
    assert media.album == "Summer Pockets REFLECTION BLUE Original SoundTrack"
    assert media.cover_url == "http://example.com/album.jpg"

    await data_source.close_http_client()


def test_generate_track_user_returns_lowercase_alphanumeric_string() -> None:
    data_source = import_data_source_module()
    value = data_source.generate_track_user()

    assert re.fullmatch(r"[a-z0-9]{16}", value)


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("kind", ["network", "json", "schema", "code"])
async def test_get_song_link_reports_remote_failures(kind: str) -> None:
    data_source = import_data_source_module()
    route = respx.get(data_source.TRACK_API_URL)
    expected = data_source.KuwoTrackResponseError
    if kind == "network":
        route.mock(side_effect=httpx.ConnectError("unavailable"))
        expected = data_source.KuwoTrackNetworkError
    elif kind == "json":
        route.mock(return_value=httpx.Response(200, text="not json"))
    elif kind == "schema":
        route.mock(return_value=httpx.Response(200, json={"code": 200}))
    else:
        route.mock(
            return_value=httpx.Response(200, json={**TRACK_RESPONSE, "code": 403})
        )
    try:
        with pytest.raises(expected):
            await data_source.get_song_link("11713652", "2000kflac")
    finally:
        await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
async def test_search_rejects_invalid_rid_at_response_boundary() -> None:
    data_source = import_data_source_module()
    payload = {
        **SEARCH_RESPONSE,
        "abslist": [{**SEARCH_RESPONSE["abslist"][0], "MUSICRID": "../../outside"}],
    }
    respx.get(data_source.SEARCH_API_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )
    try:
        with pytest.raises(data_source.KuwoSearchResponseError):
            await data_source.search_songs("test", 5)
    finally:
        await data_source.close_http_client()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("endpoint", "field_path"),
    [
        ("search", ("TOTAL",)),
        ("search", ("abslist", 0, "DURATION")),
        ("link", ("code",)),
        ("link", ("data", "bitrate")),
        ("link", ("data", "duration")),
        ("link", ("data", "rid")),
        ("detail", ("errorcode",)),
        ("detail", ("songs", 0, "id")),
    ],
)
async def test_null_numeric_fields_report_response_errors(
    endpoint: str, field_path: tuple[str | int, ...]
) -> None:
    data_source = import_data_source_module()
    if endpoint == "search":
        payload = deepcopy(SEARCH_RESPONSE)
        url = data_source.SEARCH_API_URL
        request = data_source.search_songs("test", 5)
        expected = data_source.KuwoSearchResponseError
    elif endpoint == "link":
        payload = deepcopy(TRACK_RESPONSE)
        url = data_source.TRACK_API_URL
        request = data_source.get_song_link("11713652", "2000kflac")
        expected = data_source.KuwoTrackResponseError
    else:
        payload = deepcopy(DETAIL_RESPONSE)
        url = data_source.DETAIL_API_URL
        request = data_source.get_song_detail("320490745")
        expected = data_source.KuwoTrackResponseError

    parent = payload
    for key in field_path[:-1]:
        parent = parent[key]
    parent[field_path[-1]] = None
    respx.get(url).mock(return_value=httpx.Response(200, json=payload))
    try:
        with pytest.raises(expected, match="schema mismatch"):
            await request
    finally:
        await data_source.close_http_client()
