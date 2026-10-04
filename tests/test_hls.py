import pytest
from conftest import FakeDownloader
from yt_dlp.networking.exceptions import IncompleteRead, TransportError

from yt_dlp_plugins.postprocessor._nicocomments.hls import PlaylistError, fetch_playlist_duration, media_duration

PLAYLIST = b"""#EXTM3U
#EXT-X-TARGETDURATION:6
#EXTINF:6.006,
segment1.ts
#EXTINF:5.5,
segment2.ts
#EXTINF:1,
segment3.ts
#EXT-X-ENDLIST
"""


def test_playlist_duration_is_the_sum_of_the_segments():
    ydl = FakeDownloader([PLAYLIST])
    assert fetch_playlist_duration(ydl, "https://example.com/a.m3u8", {"Cookie": "a=b"}) == pytest.approx(12.506)
    assert ydl.requests[0].url == "https://example.com/a.m3u8"
    assert ydl.requests[0].headers["Cookie"] == "a=b"


def test_playlist_without_segments_is_an_error():
    with pytest.raises(PlaylistError, match="no segments"):
        fetch_playlist_duration(FakeDownloader([b"#EXTM3U\n#EXT-X-ENDLIST\n"]), "https://example.com/a.m3u8")


def test_request_error_becomes_a_playlist_error():
    with pytest.raises(PlaylistError, match="timed out"):
        fetch_playlist_duration(FakeDownloader([TransportError("timed out")]), "https://example.com/a.m3u8")


def hls_format(url):
    return {"url": url, "protocol": "m3u8_native", "http_headers": {"Cookie": "a=b"}}


def test_media_duration_is_the_longest_hls_playlist():
    ydl = FakeDownloader([b"#EXTINF:10.0,\na.ts\n", b"#EXTINF:10.0,\na.ts\n#EXTINF:5.0,\nb.ts\n"])
    info = {
        "requested_formats": [
            hls_format("https://example.com/v.m3u8"),
            {"url": "https://example.com/v.mp4", "protocol": "https"},
            hls_format("https://example.com/a.m3u8"),
        ]
    }
    assert media_duration(ydl, info) == 15.0
    assert [request.url for request in ydl.requests] == ["https://example.com/v.m3u8", "https://example.com/a.m3u8"]
    assert ydl.requests[0].headers["Cookie"] == "a=b"


def test_media_duration_without_hls_formats_is_none():
    assert media_duration(FakeDownloader(), {"url": "https://example.com/v.mp4", "protocol": "https"}) is None


def test_incomplete_playlist_read_is_retried():
    ydl = FakeDownloader([IncompleteRead(1), PLAYLIST])
    assert fetch_playlist_duration(ydl, "https://example.com/a.m3u8") == pytest.approx(12.506)
