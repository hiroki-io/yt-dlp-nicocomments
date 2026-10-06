import re

from .comments import Chat, VideoComments

NG_SCORE_THRESHOLDS = {"high": -1000, "medium": -4800, "low": -10000, "none": None}


def effective_ng_score_threshold(comments: VideoComments, ng_score_threshold: int | None) -> int | None:
    return None if comments.ng_score_disabled else ng_score_threshold


def is_hidden(chat: Chat, ng_score_threshold: int | None) -> bool:
    if chat.invisible:
        return True
    return not chat.is_owner and ng_score_threshold is not None and chat.score <= ng_score_threshold


def visible_chats(chats: list[Chat], ng_score_threshold: int | None) -> list[Chat]:
    return [chat for chat in chats if not is_hidden(chat, ng_score_threshold)]


def apply_owner_ngs(body: str, owner_ngs: list[dict]) -> str | None:
    result = body
    for ng in owner_ngs:
        source = ng.get("source")
        if not source:
            # The official player hides every viewer comment when an entry has no source.
            return None
        destination = ng.get("destination") or ""
        if source.startswith("*"):
            replaced = destination if result and source[1:] in result else result
        else:
            replaced = replace_ignoring_case(result, source, destination)
        # The official player compares with the original body, not with the result of the previous entry.
        if replaced != body:
            result = replaced
    return result


def replace_ignoring_case(text: str, old: str, new: str) -> str:
    return re.sub(re.escape(old), lambda _: new, text, flags=re.IGNORECASE)
