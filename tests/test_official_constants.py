import json
from pathlib import Path

from yt_dlp_plugins.postprocessor._nicocomments.comments import (
    BASIC_COLORS,
    COLORS,
    FONT_KEYS,
    POSITIONS,
    PREMIUM_COLORS,
    SIZES,
)
from yt_dlp_plugins.postprocessor._nicocomments.filters import NG_SCORE_THRESHOLDS
from yt_dlp_plugins.postprocessor._nicocomments.layout import (
    LINE_COUNT_FOR_CHARACTER_SIZE,
    LINE_COUNT_FOR_LINE_HEIGHT,
    LINE_COUNT_FOR_LINE_HEIGHT_AT_RESIZE,
    RESIZE_LINE_COUNT,
)
from yt_dlp_plugins.postprocessor._nicocomments.nicoscript import SCRIPT_TYPES, TARGETS

OFFICIAL = json.loads((Path(__file__).parents[1] / "tools" / "drift" / "official.json").read_text("utf-8"))["constants"]


def test_colors_match_the_official_player():
    assert {name: code[1:].upper() for name, code in OFFICIAL["colors"].items()} == COLORS
    assert list(OFFICIAL["basicColors"]) == list(BASIC_COLORS)
    assert list(OFFICIAL["premiumColors"]) == list(PREMIUM_COLORS)


def test_command_names_match_the_official_player():
    assert tuple(OFFICIAL["positions"]) == POSITIONS
    assert tuple(OFFICIAL["resizeLineCounts"]) == SIZES
    assert tuple(OFFICIAL["fonts"]) == FONT_KEYS


def test_line_counts_match_the_official_player():
    assert OFFICIAL["lineCounts"] == {
        "LINE_COUNT_FOR_CHARACTER_SIZE": LINE_COUNT_FOR_CHARACTER_SIZE,
        "LINE_COUNT_FOR_LINE_HEIGHT": LINE_COUNT_FOR_LINE_HEIGHT,
        "LINE_COUNT_FOR_LINE_HEIGHT_AT_RESIZE": LINE_COUNT_FOR_LINE_HEIGHT_AT_RESIZE,
    }
    assert OFFICIAL["resizeLineCounts"] == RESIZE_LINE_COUNT


def test_nicoscripts_match_the_official_player():
    assert {name: OFFICIAL["scriptNames"][name] for name in SCRIPT_TYPES} == SCRIPT_TYPES
    targets = {name: frozenset(kind == "owner" for kind in kinds) for name, kinds in OFFICIAL["scriptTargets"].items()}
    assert targets == TARGETS


def test_ng_score_thresholds_match_the_official_player():
    # The official player names the medium level "middle" and disables the filter with 0.
    official = {
        "medium" if name == "middle" else name: score or None for name, score in OFFICIAL["ngScoreThresholds"].items()
    }
    assert official == NG_SCORE_THRESHOLDS
