import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from yt_dlp.networking.exceptions import HTTPError, RequestError
from yt_dlp.utils import update_url_query

from .assemble import assemble_comments, thread_key
from .comments import VideoComments
from .fetch import fetch_bytes

API_HEADERS = {"X-Frontend-Id": "6", "X-Frontend-Version": "0"}
WATCH_API_LANGUAGES = {"ja": "ja-jp", "en": "en-us", "zh": "zh-tw"}
# The comment API accepts 60 requests a minute.
PAST_PAGE_DELAY = 1


class CommentAPIError(Exception):
    pass


class PastCommentsError(Exception):
    pass


@dataclass
class RawComments:
    comment: dict
    threads: list[dict]
    fetched_at: datetime

    def to_json(self, video_id: str, language: str) -> str:
        # Drop the values of the viewer: the keys expire soon, and the NG list and own posts are private.
        comment = without(self.comment, "keys")
        comment["nvComment"] = without(comment["nvComment"], "threadKey")
        if isinstance(comment.get("ng"), dict):
            comment["ng"] = without(comment["ng"], "viewer")
        if isinstance(comment.get("threads"), list):
            comment["threads"] = [without(thread, "threadkey") for thread in comment["threads"]]
        threads = [
            {**thread, "comments": [without(raw, "isMyPost", "nicoruId") for raw in thread["comments"]]}
            for thread in self.threads
        ]
        return json.dumps(
            {
                "videoId": video_id,
                "language": language,
                "fetchedAt": self.fetched_at.isoformat(),
                "comment": comment,
                "threads": threads,
            },
            ensure_ascii=False,
        )


def without(data: dict, *keys: str) -> dict:
    return {key: value for key, value in data.items() if key not in keys}


def fetch_json(ydl, url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    return json.loads(fetch_bytes(ydl, url, body, headers))


def is_logged_in(ydl) -> bool:
    cookies = ydl.cookiejar.get_cookies_for_url("https://www.nicovideo.jp/")
    return any(cookie.name == "user_session" and cookie.value for cookie in cookies)


def fetch_watch_data(ydl, video_id: str, language: str = "ja") -> dict:
    headers = dict(API_HEADERS)
    if proxy := ydl.params.get("geo_verification_proxy"):
        headers["Ytdl-request-proxy"] = proxy
    api = None
    if is_logged_in(ydl):
        try:
            api = request_watch_api(ydl, "v3", video_id, language, headers)
        except HTTPError as e:
            # A stale user_session cookie can make the v3 API fail even for videos open to guests.
            ydl.report_warning(f"Loading the watch API as a guest because the logged-in request failed: {e}")
    if api is None:
        try:
            api = request_watch_api(ydl, "v3_guest", video_id, language, headers)
        except HTTPError as e:
            raise CommentAPIError(f"failed to load the watch API: {e}") from e
    status = (api.get("meta") or {}).get("status")
    if status != 200:
        raise CommentAPIError(f"failed to load the watch API: status {status}")
    return api["data"]


def request_watch_api(ydl, path: str, video_id: str, language: str, headers: dict) -> dict:
    track_id = f"AAAAAAAAAA_{round(time.time() * 1000)}"
    url = update_url_query(
        f"https://www.nicovideo.jp/api/watch/{path}/{video_id}",
        {"actionTrackId": track_id, "i18nLanguage": WATCH_API_LANGUAGES[language]},
    )
    return fetch_json(ydl, url, headers=headers)


def fetch_comments(
    ydl,
    video_id: str,
    language: str = "ja",
    min_comments: int | None = 0,
    to_screen: Callable[[str], None] = lambda _: None,
    report_warning: Callable[[str], None] = lambda _: None,
) -> tuple[VideoComments, RawComments]:
    try:
        fetched_at = datetime.now(timezone.utc)
        comment = fetch_watch_data(ydl, video_id, language)["comment"]
        threads = fetch_threads(ydl, comment)
        if min_comments != 0:
            threads = fetch_past_threads(
                ydl,
                video_id,
                language,
                comment,
                threads,
                min_comments,
                math.floor(fetched_at.timestamp()),
                to_screen,
                report_warning,
            )
        return assemble_comments(comment, threads), RawComments(comment, threads, fetched_at)
    except RequestError as e:
        raise CommentAPIError(f"failed to load comments: {e}") from e
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise CommentAPIError(f"unexpected response from the comment API: {e!r}") from e


def fetch_threads(ydl, comment: dict, additionals: dict | None = None) -> list[dict]:
    nv = comment["nvComment"]
    return fetch_json(
        ydl,
        f"{nv['server']}/v1/threads",
        data={"additionals": additionals or {}, "params": nv["params"], "threadKey": nv["threadKey"]},
        headers={
            **API_HEADERS,
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.nicovideo.jp",
            "Referer": "https://www.nicovideo.jp/",
            "X-Client-Os-Type": "others",
        },
    )["data"]["threads"]


def fetch_past_threads(
    ydl,
    video_id: str,
    language: str,
    comment: dict,
    threads: list[dict],
    min_comments: int | None,
    when: int,
    to_screen: Callable[[str], None],
    report_warning: Callable[[str], None],
) -> list[dict]:
    merged = {thread_key(thread): {**thread, "comments": list(thread["comments"])} for thread in threads}
    seen = {key: {raw["id"] for raw in thread["comments"]} for key, thread in merged.items()}
    page = 0
    loaded = sum(len(ids) for ids in seen.values())
    while min_comments is None or loaded < min_comments:
        if all_comments_loaded(merged, seen):
            to_screen("Loaded all comments")
            break
        time.sleep(PAST_PAGE_DELAY)
        try:
            past_threads, comment = fetch_past_page(ydl, video_id, language, comment, when)
            read_threads = [read_past_thread(thread, when) for thread in past_threads]
        except (PastCommentsError, CommentAPIError, RequestError) as e:
            report_warning(f"Stopped loading past comments: {e}")
            break
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            report_warning(f"Stopped loading past comments: unexpected response from the comment API: {e!r}")
            break
        page += 1
        oldest_of_threads = [oldest for _, _, oldest in read_threads if oldest is not None]
        for key, thread, _ in read_threads:
            target = merged.setdefault(key, {**thread, "comments": []})
            ids = seen.setdefault(key, set())
            for raw in thread["comments"]:
                if raw["id"] not in ids:
                    ids.add(raw["id"])
                    target["comments"].append(raw)
                    loaded += 1
        if not oldest_of_threads:
            break
        before = datetime.fromtimestamp(when, timezone.utc).isoformat()
        count = f"{loaded}/{min_comments}" if min_comments else loaded
        to_screen(f"Loaded past comments before {before} (page {page}, {count} comments)")
        # A page goes further back for a thread with few comments, so the next page starts at the latest of the
        # oldest times of the threads. The API includes the second of "when", so pages can repeat comments.
        next_when = max(oldest_of_threads)
        when = next_when if next_when < when else when - 1
    for thread in merged.values():
        thread["comments"].sort(key=lambda raw: raw.get("no", 0))
    return list(merged.values())


def read_past_thread(thread: dict, when: int) -> tuple[tuple[str, str], dict, int | None]:
    for raw in thread["comments"]:
        if not isinstance(raw["id"], str) or not isinstance(raw["no"], int):
            raise TypeError(f"invalid id or no in a comment: {raw['id']!r}, {raw['no']!r}")
    # The owner thread ignores "when" and returns all of its comments, so only the comments up to "when"
    # can move the next page.
    posted = [math.floor(datetime.fromisoformat(raw["postedAt"]).timestamp()) for raw in thread["comments"]]
    return thread_key(thread), thread, min((seconds for seconds in posted if seconds <= when), default=None)


def all_comments_loaded(threads: dict[tuple[str, str], dict], seen: dict[tuple[str, str], set[str]]) -> bool:
    return bool(threads) and all(
        isinstance(count := thread.get("commentCount"), int) and len(seen[key]) >= count
        for key, thread in threads.items()
    )


def fetch_past_page(ydl, video_id: str, language: str, comment: dict, when: int) -> tuple[list[dict], dict]:
    try:
        return fetch_threads(ydl, comment, {"when": when}), comment
    except HTTPError as e:
        if e.status != 400:
            raise
    # The thread key expires in about 10 minutes.
    comment = fetch_watch_data(ydl, video_id, language)["comment"]
    try:
        return fetch_threads(ydl, comment, {"when": when}), comment
    except HTTPError as e:
        if e.status != 400:
            raise
        if api_error_code(e) == "INVALID_TOKEN":
            raise PastCommentsError(
                "the comment API needs a login for past comments. Use --cookies-from-browser or --cookies"
            ) from e
        raise


def api_error_code(error: HTTPError) -> str | None:
    try:
        return json.loads(error.response.read())["meta"]["errorCode"]
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        return None
