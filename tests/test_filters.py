import pytest
from conftest import make_chat

from yt_dlp_plugins.postprocessor._nicocomments.filters import (
    NG_SCORE_THRESHOLDS,
    apply_owner_ngs,
    is_hidden,
    visible_chats,
)


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
    assert is_hidden(make_chat(score=score), NG_SCORE_THRESHOLDS[level]) == hidden


def test_ng_score_does_not_hide_owner_comments():
    assert not is_hidden(make_chat(fork="owner", score=-100000), NG_SCORE_THRESHOLDS["high"])


def test_visible_chats_removes_hidden_comments():
    chats = [make_chat(body="shown"), make_chat(body="low score", score=-5000)]
    assert [chat.lines for chat in visible_chats(chats, NG_SCORE_THRESHOLDS["medium"])] == [["shown"]]


def test_invisible_command_hides_the_comment():
    assert is_hidden(make_chat(commands=["invisible"]), None)


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
