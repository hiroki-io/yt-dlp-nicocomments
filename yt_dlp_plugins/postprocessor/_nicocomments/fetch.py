from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import IncompleteRead

MAX_ATTEMPTS = 3


def fetch_bytes(ydl, url: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    for attempt in range(MAX_ATTEMPTS):
        try:
            with ydl.urlopen(Request(url, data=data, headers=headers or {})) as response:
                return response.read()
        except IncompleteRead:
            if attempt == MAX_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable")
