import json
import time

from yt_dlp.networking.exceptions import HTTPError, RequestError
from yt_dlp.utils import update_url_query

from .assemble import assemble_comments
from .comments import VideoComments
from .fetch import fetch_bytes

API_HEADERS = {"X-Frontend-Id": "6", "X-Frontend-Version": "0"}
WATCH_API_LANGUAGES = {"ja": "ja-jp", "en": "en-us", "zh": "zh-tw"}


class CommentAPIError(Exception):
    pass


def fetch_json(ydl, url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    return json.loads(fetch_bytes(ydl, url, body, headers))


def fetch_watch_data(ydl, video_id: str, language: str = "ja") -> dict:
    cause = detail = None
    for path in ("v3", "v3_guest"):
        track_id = f"AAAAAAAAAA_{round(time.time() * 1000)}"
        url = update_url_query(
            f"https://www.nicovideo.jp/api/watch/{path}/{video_id}",
            {"actionTrackId": track_id, "i18nLanguage": WATCH_API_LANGUAGES[language]},
        )
        try:
            api = fetch_json(ydl, url, headers=API_HEADERS)
        except HTTPError as e:
            cause, detail = e, str(e)
            continue
        status = (api.get("meta") or {}).get("status")
        if status == 200:
            return api["data"]
        cause, detail = None, f"status {status}"
    raise CommentAPIError(f"failed to load the watch API: {detail}") from cause


def fetch_comments(ydl, video_id: str, language: str = "ja") -> VideoComments:
    try:
        comment = fetch_watch_data(ydl, video_id, language)["comment"]
        return assemble_comments(comment, fetch_threads(ydl, comment))
    except RequestError as e:
        raise CommentAPIError(f"failed to load comments: {e}") from e
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise CommentAPIError(f"unexpected response from the comment API: {e!r}") from e


def fetch_threads(ydl, comment: dict) -> list[dict]:
    nv = comment["nvComment"]
    return fetch_json(
        ydl,
        f"{nv['server']}/v1/threads",
        data={"additionals": {}, "params": nv["params"], "threadKey": nv["threadKey"]},
        headers={
            **API_HEADERS,
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.nicovideo.jp",
            "Referer": "https://www.nicovideo.jp/",
            "X-Client-Os-Type": "others",
        },
    )["data"]["threads"]
