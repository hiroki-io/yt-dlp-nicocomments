import sys
from datetime import datetime

from yt_dlp import YoutubeDL

from yt_dlp_plugins.postprocessor._nicocomments.api import (
    WATCH_API_LANGUAGES,
    CommentAPIError,
    fetch_threads,
    fetch_watch_data,
)

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


def check_language(ydl, language: str) -> tuple[list[str], int, int]:
    try:
        watch = fetch_watch_data(ydl, VIDEO_ID, language)
    except CommentAPIError as e:
        return [f"{language}: {e}"], 0, 0
    path = f"watch({language})"
    problems = check(watch, WATCH_SCHEMA, path)
    if problems:
        return problems, 0, 0
    actual = watch["comment"]["nvComment"]["params"].get("language")
    if actual != WATCH_API_LANGUAGES[language]:
        return [f"{path}.comment.nvComment.params.language is {actual!r}"], 0, 0
    threads = fetch_threads(ydl, watch["comment"])
    problems = check(threads, THREADS_SCHEMA, f"threads({language})")
    if problems:
        return problems, 0, 0
    comments = [comment for thread in threads for comment in thread["comments"]]
    if not any(thread["hasNicoscript"] for thread in watch["comment"]["threads"]):
        problems.append(f"{language}: no thread of {VIDEO_ID} has hasNicoscript")
    if not comments:
        problems.append(f"{language}: {VIDEO_ID} has no comments")
    for comment in comments:
        try:
            datetime.fromisoformat(comment["postedAt"])
        except ValueError:
            problems.append(f"{language}: postedAt {comment['postedAt']!r} is not an ISO 8601 date")
            break
    return problems, len(threads), len(comments)


def main() -> int:
    problems = []
    with YoutubeDL({"quiet": True}) as ydl:
        for language in WATCH_API_LANGUAGES:
            language_problems, threads, comments = check_language(ydl, language)
            problems += language_problems
            if not language_problems:
                print(f"{language}: {threads} threads and {comments} comments match the schema")
    for problem in problems[:50]:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
