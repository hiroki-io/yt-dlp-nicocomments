from .comments import Chat, FetchedComments

NG_SCORE_THRESHOLDS = {"high": -1000, "middle": -4800, "low": -10000, "none": None}


def effective_ng_score_threshold(fetched: FetchedComments, ng_score_threshold: int | None) -> int | None:
    return None if fetched.ng_score_disabled else ng_score_threshold


def is_hidden(chat: Chat, ng_score_threshold: int | None) -> bool:
    if chat.invisible:
        return True
    if chat.is_owner:
        body = "\n".join(chat.lines)
        return body.strip()[:1] in ("@", "\uff20") or body.startswith("/")
    return ng_score_threshold is not None and chat.score <= ng_score_threshold


def visible_chats(chats: list[Chat], ng_score_threshold: int | None) -> list[Chat]:
    return [chat for chat in chats if not is_hidden(chat, ng_score_threshold)]
