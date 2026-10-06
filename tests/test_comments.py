import pytest

from yt_dlp_plugins.postprocessor._nicocomments.comments import Chat, allowed_commands, is_script_body


def chat(body="comment", commands=(), fork="owner"):
    return Chat.parse(no=1, vpos_ms=10000, score=0, body=body, commands=list(commands), fork=fork)


def test_parse_takes_the_first_command_of_each_kind():
    parsed = chat(commands=["184", "big", "small", "ue", "shita", "red", "#00ff00", "mincho", "gothic", "@5"])
    assert parsed.size == "big"
    assert parsed.position == "ue"
    assert parsed.color == "FF0000"
    assert parsed.font_key == "mincho"
    assert parsed.at_seconds == 5.0


def test_parse_uses_default_styles():
    parsed = chat()
    assert (parsed.position, parsed.size, parsed.color, parsed.font_key) == ("naka", "medium", "FFFFFF", "defont")


def test_parse_ignores_the_case_of_style_commands():
    parsed = chat(commands=["UE", "Big", "RED", "Mincho"])
    assert (parsed.position, parsed.size, parsed.color, parsed.font_key) == ("ue", "big", "FF0000", "mincho")


def test_parse_sets_flag_commands():
    parsed = chat(commands=["full", "ender", "invisible", "_live"])
    assert (parsed.full, parsed.ender, parsed.invisible, parsed.live) == (True, True, True, True)


def test_parse_matches_flag_commands_case_sensitively():
    parsed = chat(commands=["FULL", "Ender", "Invisible", "_LIVE"])
    assert (parsed.full, parsed.ender, parsed.invisible, parsed.live) == (False, False, False, False)


def test_parse_ignores_at_commands_of_viewer_comments():
    assert chat(commands=["@5"], fork="main").at_seconds is None
    assert chat(commands=["@5"], fork="owner").at_seconds == 5.0


def test_parse_uses_the_ai_comment_color_for_ai_comments():
    assert chat(commands=["red"], fork="ai").color == "DCDCDC"
    assert chat(fork="ai").color == "DCDCDC"


def test_allowed_commands_drop_premium_colors_of_non_premium_users():
    assert allowed_commands({"commands": ["red2", "Blue", "#00ff00", "big"]}) == ["Blue", "big"]
    assert allowed_commands({"commands": ["Red2", "#00FF00"], "isPremium": True}) == ["Red2", "#00FF00"]
    assert allowed_commands({"commands": ["#GGGGGG", "#gggggg1"]}) == ["#gggggg1"]


def test_allowed_commands_keep_color_codes_with_non_ascii_letters():
    commands = ["#\u212a12345", "#\u0130abcde", "#\u017f12345"]
    assert allowed_commands({"commands": commands}) == commands


def test_parse_splits_lines_and_replaces_tabs():
    assert chat(body="a\tb\r\nc\rd\ne").lines == ["a  b", "c", "d", "e"]


def test_parse_ignores_at_commands_that_are_not_positive():
    assert chat(commands=["@0"]).at_seconds is None
    assert chat(commands=["@0", "@5"]).at_seconds == 5.0


def test_parse_ignores_at_commands_with_full_width_digits():
    assert chat(commands=["@\uff11\uff10", "@5"]).at_seconds == 5.0


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("@デフォルト", True),
        ("\uff20置換 a b", True),
        (" @逆", True),
        ("/script", True),
        ("text @5", False),
        (" /script", False),
    ],
)
def test_is_script_body(body, expected):
    assert is_script_body(body) == expected
