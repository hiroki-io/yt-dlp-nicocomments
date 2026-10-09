from typing import Any


class CommentAPIError(Exception):
    pass


def unexpected_response(description: str) -> CommentAPIError:
    return CommentAPIError(f"unexpected response from the comment API: {description}")


def expect(condition: bool, description: str) -> None:
    if not condition:
        raise unexpected_response(description)


def is_objects(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def is_optional(value: Any, types: type | tuple[type, ...]) -> bool:
    return value is None or isinstance(value, types)


def is_watch_thread_id(value: dict) -> bool:
    return isinstance(value.get("id"), (int, str)) and isinstance(value.get("forkLabel"), str)


def check_comment_data(comment: Any) -> dict:
    expect(isinstance(comment, dict), "comment is not an object")
    nv = comment.get("nvComment")
    expect(
        isinstance(nv, dict)
        and isinstance(nv.get("server"), str)
        and "params" in nv
        and isinstance(nv.get("threadKey"), str),
        "invalid comment.nvComment",
    )
    expect(is_optional(comment.get("threads"), list), "comment.threads is not an array")
    for thread in comment.get("threads") or []:
        expect(isinstance(thread, dict) and is_watch_thread_id(thread), "invalid thread in comment.threads")
    layers = comment.get("layers")
    expect(is_objects(layers), "comment.layers is not an array of objects")
    for layer in layers:
        expect(
            isinstance(layer.get("index"), int)
            and isinstance(layer.get("isTranslucent"), bool)
            and is_objects(layer.get("threadIds"))
            and all(is_watch_thread_id(thread_id) for thread_id in layer["threadIds"]),
            "invalid layer in comment.layers",
        )
    ng = comment.get("ng")
    expect(is_optional(ng, dict), "comment.ng is not an object")
    if ng:
        expect(is_optional(ng.get("ngScore"), dict), "comment.ng.ngScore is not an object")
        expect(is_optional(ng.get("owner"), list), "comment.ng.owner is not an array")
        for entry in ng.get("owner") or []:
            expect(
                isinstance(entry, dict)
                and is_optional(entry.get("source"), str)
                and is_optional(entry.get("destination"), str),
                "invalid entry in comment.ng.owner",
            )
    return comment


def check_threads(threads: Any) -> list[dict]:
    expect(is_objects(threads), "threads is not an array of objects")
    for thread in threads:
        expect(
            isinstance(thread.get("id"), (int, str))
            and isinstance(thread.get("fork"), str)
            and is_objects(thread.get("comments")),
            "invalid thread",
        )
        for raw in thread["comments"]:
            # The plugin falls back to the defaults of "no" and "score" only when the keys are missing.
            expect(
                isinstance(raw.get("id"), str)
                and isinstance(raw.get("vposMs"), int)
                and isinstance(raw.get("no", 0), int)
                and isinstance(raw.get("score", 0), int)
                and is_optional(raw.get("body"), str)
                and is_optional(raw.get("commands"), list)
                and all(isinstance(command, str) for command in raw.get("commands") or []),
                f"invalid comment {raw.get('id')!r}",
            )
    return threads
