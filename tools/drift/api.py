import sys
from datetime import datetime

from yt_dlp import YoutubeDL

from yt_dlp_plugins.postprocessor._nicocomments.api import fetch_threads, fetch_watch_data

VIDEO_ID = "sm9"
WATCH_SCHEMA = {
    "comment": {
        "nvComment": {"server": str, "params": dict, "threadKey": str},
        "threads": [{"id": int, "forkLabel": str, "hasNicoscript": bool}],
        "layers": [{"index": int, "isTranslucent": bool, "threadIds": [{"id": int, "forkLabel": str}]}],
        "ng": {"ngScore": {"isDisabled": bool}},
    }
}
COMMENT_SCHEMA = {
    "no": int,
    "vposMs": int,
    "body": str,
    "commands": [str],
    "isPremium": bool,
    "postedAt": str,
    "score": int,
}
THREADS_SCHEMA = [{"id": str, "fork": str, "comments": [COMMENT_SCHEMA]}]


def check(value, schema, path: str) -> list[str]:
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            return [f"{path} is {type(value).__name__}, not an object"]
        problems = []
        for key, child in schema.items():
            if key not in value:
                problems.append(f"{path}.{key} is missing")
            else:
                problems += check(value[key], child, f"{path}.{key}")
        return problems
    if isinstance(schema, list):
        if not isinstance(value, list):
            return [f"{path} is {type(value).__name__}, not an array"]
        return [problem for i, item in enumerate(value) for problem in check(item, schema[0], f"{path}[{i}]")]
    if type(value) is not schema:
        return [f"{path} is {type(value).__name__}, not {schema.__name__}"]
    return []


def main() -> int:
    with YoutubeDL({"quiet": True}) as ydl:
        watch = fetch_watch_data(ydl, VIDEO_ID)
        problems = check(watch, WATCH_SCHEMA, "watch")
        threads = fetch_threads(ydl, watch["comment"]) if not problems else []
    problems += check(threads, THREADS_SCHEMA, "threads")
    comments = [comment for thread in threads if isinstance(thread, dict) for comment in thread.get("comments") or []]
    if not problems:
        if not any(thread["hasNicoscript"] for thread in watch["comment"]["threads"]):
            problems.append(f"no thread of {VIDEO_ID} has hasNicoscript")
        if not comments:
            problems.append(f"{VIDEO_ID} has no comments")
        for comment in comments:
            try:
                datetime.fromisoformat(comment["postedAt"])
            except ValueError:
                problems.append(f"postedAt {comment['postedAt']!r} is not an ISO 8601 date")
                break
    for problem in problems[:50]:
        print(problem)
    if problems:
        return 1
    print(f"{len(threads)} threads and {len(comments)} comments match the schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
