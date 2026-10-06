from .comments import Chat, CommentLayer, VideoComments, allowed_commands, is_script_body
from .filters import apply_owner_ngs
from .nicoscript import Nicoscripts


def assemble_comments(comment: dict, threads: list[dict]) -> VideoComments:
    script_threads = {
        (str(thread["id"]), thread["forkLabel"])
        for thread in comment.get("threads") or []
        if thread.get("hasNicoscript")
    }
    scripts = Nicoscripts.parse(
        [
            raw
            for thread in threads
            if (str(thread["id"]), thread["fork"]) in script_threads
            for raw in thread["comments"]
        ]
    )
    layers = {}
    for layer in comment["layers"]:
        is_owner = any(thread_id["forkLabel"] == "owner" for thread_id in layer["threadIds"])
        layers[layer["index"]] = CommentLayer(
            layer["index"], layer["isTranslucent"], [], scripts.reverse_ranges(is_owner)
        )
    thread_layers = {
        (str(thread_id["id"]), thread_id["forkLabel"]): layer["index"]
        for layer in comment["layers"]
        for thread_id in layer["threadIds"]
    }
    owner_ngs = (comment.get("ng") or {}).get("owner") or []
    for thread in threads:
        index = thread_layers.get((str(thread["id"]), thread["fork"]))
        if index is None:
            continue
        is_owner = thread["fork"] == "owner"
        for raw in thread["comments"]:
            body = raw.get("body") or ""
            # The official player hides owner scripts before it applies @置換.
            if is_owner and is_script_body(body):
                continue
            if not is_owner and (body := apply_owner_ngs(body, owner_ngs)) is None:
                continue
            vpos_ms = raw["vposMs"]
            body, commands = scripts.apply(
                body=body, vpos_ms=vpos_ms, commands=allowed_commands(raw), is_owner=is_owner
            )
            chat = Chat.parse(
                no=raw.get("no", 0),
                vpos_ms=vpos_ms,
                score=raw.get("score", 0),
                body=body,
                commands=commands,
                fork=thread["fork"],
            )
            layers[index].chats.append(chat)
    ng_score_disabled = bool(((comment.get("ng") or {}).get("ngScore") or {}).get("isDisabled"))
    return VideoComments(list(layers.values()), ng_score_disabled)
