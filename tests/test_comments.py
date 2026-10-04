from yt_dlp_plugins.postprocessor._nicocomments.comments import Chat


def chat(body="comment", commands=(), fork="owner", premium=True):
    return Chat.parse({"no": 1, "vposMs": 10000, "body": body, "commands": list(commands), "isPremium": premium}, fork)


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


def test_parse_ignores_premium_colors_of_non_premium_users():
    assert chat(commands=["red2", "blue"], premium=False).color == "0000FF"
    assert chat(commands=["#00ff00", "blue"], premium=False).color == "0000FF"
    assert chat(commands=["Red2"], premium=False).color == "FFFFFF"
    assert chat(commands=["red2"], premium=True).color == "CC0033"
    assert chat(commands=["#00ff00"], premium=True).color == "00FF00"


def test_parse_splits_lines_and_replaces_tabs():
    assert chat(body="a\tb\r\nc\rd\ne").lines == ["a  b", "c", "d", "e"]


def test_parse_ignores_at_commands_that_are_not_positive():
    assert chat(commands=["@0"]).at_seconds is None
    assert chat(commands=["@0", "@5"]).at_seconds == 5.0
