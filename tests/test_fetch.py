import io

import pytest
from conftest import FakeDownloader
from yt_dlp.networking import Response
from yt_dlp.networking.exceptions import HTTPError, IncompleteRead, TransportError

from yt_dlp_plugins.postprocessor._nicocomments.fetch import fetch_bytes


def test_transport_error_is_retried(sleeps):
    ydl = FakeDownloader([IncompleteRead(1), TransportError("timed out"), b"data"])
    assert fetch_bytes(ydl, "https://example.com/") == b"data"
    assert len(ydl.requests) == 3
    assert sleeps == [5, 10]


def test_transport_error_is_raised_after_the_last_attempt(sleeps):
    ydl = FakeDownloader([IncompleteRead(1), IncompleteRead(1), IncompleteRead(1)])
    with pytest.raises(IncompleteRead):
        fetch_bytes(ydl, "https://example.com/")
    assert len(ydl.requests) == 3


def test_http_error_is_not_retried(sleeps):
    ydl = FakeDownloader([HTTPError(Response(io.BytesIO(), "https://example.com/", {}, status=404))])
    with pytest.raises(HTTPError):
        fetch_bytes(ydl, "https://example.com/")
    assert len(ydl.requests) == 1
    assert sleeps == []
