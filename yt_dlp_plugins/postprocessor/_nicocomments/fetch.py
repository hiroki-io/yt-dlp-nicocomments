import time

from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import TransportError

MAX_ATTEMPTS = 3
RETRY_DELAY = 5


def fetch_bytes(ydl, url: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with ydl.urlopen(Request(url, data=data, headers=headers or {})) as response:
                return response.read()
        except TransportError:
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(RETRY_DELAY * attempt)
    raise AssertionError("unreachable")
