import pytest

from yt_dlp_plugins.postprocessor._nicocomments.comments import Chat, FetchedComments
from yt_dlp_plugins.postprocessor._nicocomments.filters import (
    NG_SCORE_THRESHOLDS,
    effective_ng_score_threshold,
    is_hidden,
    visible_chats,
)


def chat(body="comment", fork="main", score=0, commands=()):
    return Chat.parse({"vposMs": 0, "body": body, "score": score, "commands": list(commands)}, fork)


@pytest.mark.parametrize(
    ("level", "score", "hidden"),
    [
        ("middle", -4799, False),
        ("middle", -4800, True),
        ("high", -1000, True),
        ("low", -9999, False),
        ("none", -100000, False),
    ],
)
def test_ng_score_hides_viewer_comments(level, score, hidden):
    assert is_hidden(chat(score=score), NG_SCORE_THRESHOLDS[level]) == hidden


def test_ng_score_does_not_hide_owner_comments():
    assert not is_hidden(chat(fork="owner", score=-100000), NG_SCORE_THRESHOLDS["high"])


@pytest.mark.parametrize("body", ["@デフォルト", "\uff20置換 a b", " @逆", "/script"])
def test_owner_script_comments_are_hidden(body):
    assert is_hidden(chat(body=body, fork="owner"), None)


@pytest.mark.parametrize("body", ["text @5", " /script"])
def test_other_owner_comments_are_shown(body):
    assert not is_hidden(chat(body=body, fork="owner"), None)


def test_viewer_comments_that_start_with_at_are_shown():
    assert not is_hidden(chat(body="@デフォルト"), None)


def test_visible_chats_removes_hidden_comments():
    chats = [chat(body="shown"), chat(body="low score", score=-5000)]
    assert [chat.lines for chat in visible_chats(chats, NG_SCORE_THRESHOLDS["middle"])] == [["shown"]]


def test_invisible_command_hides_the_comment():
    assert is_hidden(chat(commands=["invisible"]), None)


@pytest.mark.parametrize(("ng_score_disabled", "expected"), [(False, -4800), (True, None)])
def test_ng_score_disabled_by_the_api_removes_the_threshold(ng_score_disabled, expected):
    fetched = FetchedComments([], ng_score_disabled)
    assert effective_ng_score_threshold(fetched, NG_SCORE_THRESHOLDS["middle"]) == expected
