import json
import time

from yt_dlp.networking.exceptions import HTTPError, RequestError

from .comments import Chat, CommentLayer, FetchedComments
from .fetch import fetch_bytes

API_HEADERS = {"X-Frontend-Id": "6", "X-Frontend-Version": "0"}


class CommentAPIError(Exception):
    pass


def fetch_json(ydl, url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    return json.loads(fetch_bytes(ydl, url, body, headers))


def fetch_watch_data(ydl, video_id: str) -> dict:
    cause = detail = None
    for path in ("v3", "v3_guest"):
        track_id = f"AAAAAAAAAA_{round(time.time() * 1000)}"
        url = f"https://www.nicovideo.jp/api/watch/{path}/{video_id}?actionTrackId={track_id}"
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


def fetch_comments(ydl, video_id: str) -> FetchedComments:
    try:
        return _fetch_comments(ydl, video_id)
    except RequestError as e:
        raise CommentAPIError(f"failed to load comments: {e}") from e
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise CommentAPIError(f"unexpected response from the comment API: {e!r}") from e


def _fetch_comments(ydl, video_id: str) -> FetchedComments:
    comment = fetch_watch_data(ydl, video_id)["comment"]
    nv = comment["nvComment"]
    threads = fetch_json(
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

    layers = {layer["index"]: CommentLayer(layer["index"], layer["isTranslucent"], []) for layer in comment["layers"]}
    thread_layers = {
        (str(thread_id["id"]), thread_id["forkLabel"]): layer["index"]
        for layer in comment["layers"]
        for thread_id in layer["threadIds"]
    }
    for thread in threads:
        index = thread_layers.get((str(thread["id"]), thread["fork"]))
        if index is None:
            continue
        layers[index].chats += [Chat.parse(raw, thread["fork"]) for raw in thread["comments"]]
    ng_score_disabled = bool(((comment.get("ng") or {}).get("ngScore") or {}).get("isDisabled"))
    return FetchedComments(list(layers.values()), ng_score_disabled)
