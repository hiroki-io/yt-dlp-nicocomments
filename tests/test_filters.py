import pytest

from yt_dlp_plugins.postprocessor._nicocomments.comments import Chat, VideoComments
from yt_dlp_plugins.postprocessor._nicocomments.filters import (
    NG_SCORE_THRESHOLDS,
    apply_owner_ngs,
    effective_ng_score_threshold,
    is_hidden,
    visible_chats,
)


def chat(body="comment", fork="main", score=0, commands=()):
    return Chat.parse(no=1, vpos_ms=0, score=score, body=body, commands=list(commands), fork=fork)


@pytest.mark.parametrize(
    ("level", "score", "hidden"),
    [
        ("medium", -4799, False),
        ("medium", -4800, True),
        ("high", -1000, True),
        ("low", -9999, False),
        ("none", -100000, False),
    ],
)
def test_ng_score_hides_viewer_comments(level, score, hidden):
    assert is_hidden(chat(score=score), NG_SCORE_THRESHOLDS[level]) == hidden


def test_ng_score_does_not_hide_owner_comments():
    assert not is_hidden(chat(fork="owner", score=-100000), NG_SCORE_THRESHOLDS["high"])


def test_visible_chats_removes_hidden_comments():
    chats = [chat(body="shown"), chat(body="low score", score=-5000)]
    assert [chat.lines for chat in visible_chats(chats, NG_SCORE_THRESHOLDS["medium"])] == [["shown"]]


def test_invisible_command_hides_the_comment():
    assert is_hidden(chat(commands=["invisible"]), None)


@pytest.mark.parametrize(("ng_score_disabled", "expected"), [(False, -4800), (True, None)])
def test_ng_score_disabled_by_the_api_removes_the_threshold(ng_score_disabled, expected):
    comments = VideoComments([], ng_score_disabled)
    assert effective_ng_score_threshold(comments, NG_SCORE_THRESHOLDS["medium"]) == expected


@pytest.mark.parametrize(
    ("body", "ngs", "expected"),
    [
        ("Up up UP", [{"source": "up", "destination": "x"}], "x x x"),
        ("keep", [{"source": "up", "destination": "x"}], "keep"),
        ("İab", [{"source": "a", "destination": "x"}], "İxb"),
        ("a", [{"source": "a", "destination": r"\1"}], r"\1"),
        ("an ng word", [{"source": "*ng", "destination": "hidden"}], "hidden"),
        ("an NG word", [{"source": "*ng", "destination": "hidden"}], "an NG word"),
        ("", [{"source": "*", "destination": "x"}], ""),
        ("aa", [{"source": "aa", "destination": "a"}], "a"),
        ("ab", [{"source": "a", "destination": "b"}, {"source": "bb", "destination": "c"}], "c"),
        ("ab", [{"source": "a", "destination": "b"}, {"source": "bb", "destination": "ab"}], "bb"),
        ("comment", [{"source": "", "destination": "x"}], None),
    ],
)
def test_apply_owner_ngs(body, ngs, expected):
    assert apply_owner_ngs(body, ngs) == expected
