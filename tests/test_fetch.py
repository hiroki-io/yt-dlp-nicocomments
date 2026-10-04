import pytest
from conftest import FakeDownloader
from yt_dlp.networking.exceptions import IncompleteRead

from yt_dlp_plugins.postprocessor._nicocomments.fetch import fetch_bytes


def test_incomplete_read_is_retried():
    ydl = FakeDownloader([IncompleteRead(1), IncompleteRead(1), b"data"])
    assert fetch_bytes(ydl, "https://example.com/") == b"data"
    assert len(ydl.requests) == 3


def test_incomplete_read_is_raised_after_the_last_attempt():
    ydl = FakeDownloader([IncompleteRead(1), IncompleteRead(1), IncompleteRead(1)])
    with pytest.raises(IncompleteRead):
        fetch_bytes(ydl, "https://example.com/")
    assert len(ydl.requests) == 3
