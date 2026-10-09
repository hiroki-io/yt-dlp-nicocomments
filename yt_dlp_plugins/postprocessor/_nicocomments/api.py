import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from yt_dlp.networking.exceptions import HTTPError, RequestError
from yt_dlp.utils import update_url_query

from .assemble import assemble_comments, thread_key
from .comments import VideoComments
from .fetch import fetch_bytes
from .response import CommentAPIError, check_comment_data, check_threads, expect, unexpected_response

API_HEADERS = {"X-Frontend-Id": "6", "X-Frontend-Version": "0"}
WATCH_API_LANGUAGES = {"ja": "ja-jp", "en": "en-us", "zh": "zh-tw"}
# The comment API accepts 60 requests a minute.
PAST_PAGE_DELAY = 1


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


def fetch_json(ydl, url: str, data: dict | None = None, headers: dict | None = None) -> Any:
    body = json.dumps(data).encode() if data is not None else None
    response = fetch_bytes(ydl, url, body, headers)
    try:
        return json.loads(response)
    except ValueError as e:
        raise unexpected_response(str(e)) from e


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
    meta = api.get("meta") if isinstance(api, dict) else None
    status = meta.get("status") if isinstance(meta, dict) else None
    if status != 200:
        raise CommentAPIError(f"failed to load the watch API: status {status}")
    expect(isinstance(api.get("data"), dict), "data in the watch API is not an object")
    return api["data"]


def fetch_comment_data(ydl, video_id: str, language: str) -> dict:
    return check_comment_data(fetch_watch_data(ydl, video_id, language).get("comment"))


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
    fetched_at = datetime.now(timezone.utc)
    try:
        comment = fetch_comment_data(ydl, video_id, language)
        threads = fetch_threads(ydl, comment)
    except RequestError as e:
        raise CommentAPIError(f"failed to load comments: {e}") from e
    if min_comments != 0:
        threads = fetch_past_threads(
            past_page_fetcher(ydl, video_id, language, comment),
            threads,
            min_comments,
            math.floor(fetched_at.timestamp()),
            to_screen,
            report_warning,
        )
    return assemble_comments(comment, threads), RawComments(comment, threads, fetched_at)


def fetch_threads(ydl, comment: dict, additionals: dict | None = None) -> list[dict]:
    response = request_threads(ydl, comment, additionals)
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise unexpected_response("data in the threads is not an object")
    return check_threads(data.get("threads"))


def request_threads(ydl, comment: dict, additionals: dict | None = None) -> Any:
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
    )


def fetch_past_threads(
    fetch_page: Callable[[int], list[dict]],
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
            read_threads = [read_past_thread(thread, when) for thread in fetch_page(when)]
        except (PastCommentsError, CommentAPIError, RequestError) as e:
            report_warning(f"Stopped loading past comments: {e}")
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
        # A page goes further back for a thread with few comments, so the next page starts at the latest of the
        # oldest times of the threads. The API includes the second of "when", so pages can repeat comments.
        next_when = max(oldest_of_threads)
        reached = datetime.fromtimestamp(next_when, timezone.utc).isoformat()
        count = f"{loaded}/{min_comments}" if min_comments else loaded
        to_screen(f"Loaded past comments back to {reached} (page {page}, {count} comments)")
        when = next_when if next_when < when else when - 1
    for thread in merged.values():
        thread["comments"].sort(key=lambda raw: raw.get("no", 0))
    return list(merged.values())


def read_past_thread(thread: dict, when: int) -> tuple[tuple[str, str], dict, int | None]:
    posted = []
    for raw in thread["comments"]:
        expect(isinstance(raw.get("no"), int), f"no number in the past comment {raw['id']!r}")
        posted.append(math.floor(posted_at(raw).timestamp()))
    # The owner thread ignores "when" and returns all of its comments, so only the comments up to "when"
    # can move the next page.
    return thread_key(thread), thread, min((seconds for seconds in posted if seconds <= when), default=None)


def posted_at(raw: dict) -> datetime:
    value = raw.get("postedAt")
    if not isinstance(value, str):
        raise unexpected_response(f"no postedAt in the comment {raw['id']!r}")
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise unexpected_response(str(e)) from e


def all_comments_loaded(threads: dict[tuple[str, str], dict], seen: dict[tuple[str, str], set[str]]) -> bool:
    return bool(threads) and all(
        isinstance(count := thread.get("commentCount"), int) and len(seen[key]) >= count
        for key, thread in threads.items()
    )


def past_page_fetcher(ydl, video_id: str, language: str, comment: dict) -> Callable[[int], list[dict]]:
    def fetch_page(when: int) -> list[dict]:
        nonlocal comment
        past_threads, comment = fetch_past_page(ydl, video_id, language, comment, when)
        return past_threads

    return fetch_page


def fetch_past_page(ydl, video_id: str, language: str, comment: dict, when: int) -> tuple[list[dict], dict]:
    try:
        return fetch_threads(ydl, comment, {"when": when}), comment
    except HTTPError as e:
        check_past_page_error(e)
    # The thread key expires in about 10 minutes.
    comment = fetch_comment_data(ydl, video_id, language)
    try:
        return fetch_threads(ydl, comment, {"when": when}), comment
    except HTTPError as e:
        check_past_page_error(e)
        raise


def check_past_page_error(error: HTTPError) -> None:
    if error.status != 400:
        raise error
    # A renewed thread key cannot fix INVALID_TOKEN, which a guest thread key gets.
    if api_error_code(error) == "INVALID_TOKEN":
        raise PastCommentsError(
            "the comment API needs a login for past comments. Use --cookies-from-browser or --cookies"
        ) from error


def api_error_code(error: HTTPError) -> str | None:
    try:
        return json.loads(error.response.read())["meta"]["errorCode"]
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        return None
