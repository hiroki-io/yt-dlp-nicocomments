import math

import pytest

from yt_dlp_plugins.postprocessor._nicocomments.nicoscript import Nicoscripts, split_arguments


def raw(body="comment", commands=(), vpos_ms=10000, premium=True, posted_at="2024-01-01T00:00:00+09:00"):
    return {"vposMs": vpos_ms, "body": body, "commands": list(commands), "isPremium": premium, "postedAt": posted_at}


def apply(scripts, comment, is_owner=False):
    return scripts.apply(comment, comment["commands"], is_owner)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a b  c", ["a", "b", "c"]),
        ('"a b" c', ["a b", "c"]),
        ("'it\\'s' x", ["it's", "x"]),
        ('"line\\nbreak"', ["line\nbreak"]),
        ('"a\\\nb" c', ["a\\\nb", "c"]),
        ("「a b」 c", ["a b", "c"]),
        ('"open c', ['"open', "c"]),
        ("a　b", ["a", "b"]),
    ],
)
def test_split_arguments(text, expected):
    assert split_arguments(text) == expected


def test_default_adds_only_the_missing_kinds_of_commands():
    scripts = Nicoscripts.parse([raw("@デフォルト", ["red", "big"], vpos_ms=0)])
    assert apply(scripts, raw(commands=["small"])) == ("comment", ["small", "red"])


def test_default_applies_until_the_end_unless_an_at_command_is_given():
    scripts = Nicoscripts.parse([raw("@デフォルト", ["red"], vpos_ms=0)])
    assert scripts.defaults[0].end_ms == math.inf
    scripts = Nicoscripts.parse([raw("@デフォルト", ["red", "@5"], vpos_ms=0)])
    assert apply(scripts, raw(vpos_ms=4999)) == ("comment", ["red"])
    assert apply(scripts, raw(vpos_ms=5000)) == ("comment", [])


def test_later_default_takes_priority():
    scripts = Nicoscripts.parse([raw("@デフォルト", ["red"], vpos_ms=0), raw("@デフォルト", ["blue"], vpos_ms=5000)])
    _, commands = apply(scripts, raw())
    assert commands[0] == "blue"


def test_default_ignores_premium_colors_of_non_premium_users():
    scripts = Nicoscripts.parse([raw("@デフォルト", ["red2", "ue"], vpos_ms=0, premium=False)])
    assert apply(scripts, raw()) == ("comment", ["ue"])


def test_non_hex_color_codes_count_as_colors_like_the_official_player():
    scripts = Nicoscripts.parse([raw("@デフォルト", ["red"], vpos_ms=0)])
    assert apply(scripts, raw(commands=["#GGGGGG"])) == ("comment", ["#GGGGGG"])
    scripts = Nicoscripts.parse([raw("@置換 a b", ["#gggggg"], vpos_ms=0)])
    assert apply(scripts, raw("a", ["blue"])) == ("b", ["#gggggg"])


def test_replacement_replaces_every_occurrence_for_viewer_comments_by_default():
    scripts = Nicoscripts.parse([raw("@置換 a b", vpos_ms=0)])
    assert apply(scripts, raw("banana")) == ("bbnbnb", [])
    assert apply(scripts, raw("banana"), is_owner=True) == ("banana", [])
    assert apply(scripts, raw("banana", vpos_ms=30000)) == ("banana", [])


def test_replacement_options():
    scripts = Nicoscripts.parse([raw("@置換 ab XY 全 投コメ 完全一致", vpos_ms=0)])
    assert apply(scripts, raw("ab"), is_owner=True) == ("XY", [])
    assert apply(scripts, raw("abc"), is_owner=True) == ("abc", [])
    assert apply(scripts, raw("ab")) == ("ab", [])
    scripts = Nicoscripts.parse([raw("@置換 b X 全 含む", vpos_ms=0)])
    assert apply(scripts, raw("abc"), is_owner=True) == ("X", [])


def test_replacement_replaces_the_kinds_of_commands_that_the_script_has():
    scripts = Nicoscripts.parse([raw("@置換 a b", ["red", "ue"], vpos_ms=0)])
    assert apply(scripts, raw("a", ["blue", "shita", "big"])) == ("b", ["big", "red", "ue"])


def test_replacement_matches_command_names_like_the_official_player():
    scripts = Nicoscripts.parse([raw("@置換 a b", ["ue"], vpos_ms=0)])
    assert apply(scripts, raw("a", ["ue", "184", "nakanaka"])) == ("b", ["184", "ue"])


def test_reverse_targets_both_kinds_of_comments_by_default():
    scripts = Nicoscripts.parse([raw("@逆", vpos_ms=1000), raw("\uff20逆 コメ", ["@5"], vpos_ms=50000)])
    assert scripts.reverse_ranges(is_owner=True) == [(1000, 31000)]
    assert scripts.reverse_ranges(is_owner=False) == [(1000, 31000), (50000, 55000)]


def test_time_range_ignores_at_commands_with_full_width_digits():
    scripts = Nicoscripts.parse([raw("@逆", ["@\uff15"], vpos_ms=1000)])
    assert scripts.reverse_ranges(is_owner=True) == [(1000, 31000)]


def test_unknown_scripts_and_ordinary_comments_are_ignored():
    scripts = Nicoscripts.parse([raw("@ジャンプ #1:00"), raw("@置換"), raw("comment @逆"), raw("@unknown")])
    assert scripts == Nicoscripts()
