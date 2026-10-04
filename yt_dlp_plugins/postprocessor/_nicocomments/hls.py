import re

from yt_dlp.networking.exceptions import RequestError

from .fetch import fetch_bytes

EXTINF = re.compile(r"^#EXTINF:([0-9.]+)", re.MULTILINE)


class PlaylistError(Exception):
    pass


def fetch_playlist_duration(ydl, url: str, headers: dict | None = None) -> float:
    try:
        playlist = fetch_bytes(ydl, url, headers=headers).decode()
        durations = EXTINF.findall(playlist)
        if not durations:
            raise PlaylistError("no segments in the playlist")
        return sum(float(duration) for duration in durations)
    except (RequestError, ValueError) as e:
        raise PlaylistError(str(e)) from e


def media_duration(ydl, info: dict) -> float | None:
    formats = [
        fmt
        for fmt in info.get("requested_formats") or [info]
        if fmt.get("url") and str(fmt.get("protocol")).startswith("m3u8")
    ]
    durations = [fetch_playlist_duration(ydl, fmt["url"], fmt.get("http_headers")) for fmt in formats]
    return max(durations, default=None)
