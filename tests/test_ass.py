import re

import pytest

from yt_dlp_plugins.postprocessor._nicocomments.ass import (
    Viewport,
    ass_color,
    ass_escape,
    ass_time,
    build_ass,
    comment_opacity,
    paint_order,
    slot_events,
)
from yt_dlp_plugins.postprocessor._nicocomments.comments import Chat
from yt_dlp_plugins.postprocessor._nicocomments.fonts import Face, FontChain
from yt_dlp_plugins.postprocessor._nicocomments.layout import (
    BEHIND_ADJUST_MS,
    FRONT_ADJUST_MS,
    STAGE_HEIGHT,
    STAGE_WIDTH,
    Slot,
    SlotLayer,
)

STAGE = Viewport(0, 0, STAGE_WIDTH, STAGE_HEIGHT)


def make_chain() -> FontChain:
    face = Face("Test-Regular", "Test Regular", False, 400, 1000, 800, 1000, [500], {}, (800, 200))
    return FontChain([face], 400, 0.0)


def make_slot(body="comment", commands=(), vpos_ms=0, no=1, shown_ms=1000, hidden_ms=6000) -> Slot:
    chat = Chat.parse(
        {"no": no, "vposMs": vpos_ms, "body": body, "commands": list(commands), "isPremium": True}, "main"
    )
    slot = Slot(chat, make_chain(), 30.0, 32.0)
    slot.start_ms, slot.end_ms = shown_ms + FRONT_ADJUST_MS, hidden_ms - BEHIND_ADJUST_MS
    slot.initial_x, slot.target_x = 600.0, 0.0
    slot.shown_ms, slot.hidden_ms = shown_ms, hidden_ms
    return slot


def dialogue_layers(ass: str) -> list[tuple[int, str]]:
    return [(int(m[1]), m[2]) for m in re.finditer(r"^Dialogue: (\d+),.*\}([^{}\n]*)$", ass, re.MULTILINE)]


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((640, 480), Viewport(STAGE_WIDTH / 2 - 256, 0, 512, STAGE_HEIGHT)),
        ((1920, 1080), Viewport(0, 0, STAGE_WIDTH, STAGE_HEIGHT)),
        ((2100, 900), Viewport(0, (STAGE_HEIGHT - STAGE_WIDTH * 9 / 21) / 2, STAGE_WIDTH, STAGE_WIDTH * 9 / 21)),
    ],
)
def test_viewport_fits_the_video_in_the_16_9_stage(size, expected):
    viewport = Viewport.for_video(*size)
    for field in ("x", "y", "width", "height"):
        assert getattr(viewport, field) == pytest.approx(getattr(expected, field))


def test_live_command_and_translucent_layer_reduce_opacity():
    chat = Chat.parse({"vposMs": 0, "commands": ["_live"]}, "main")
    assert comment_opacity(chat, translucent=True) == 0.25


def test_fixed_comment_uses_pos():
    (event,) = slot_events(make_slot(commands=["ue"]), STAGE, 1.0, 0, 1.0)
    assert "\\pos(" in event
    assert "\\move(" not in event


def test_moving_comment_x_matches_x_at_shown_ms_and_hidden_ms():
    slot = make_slot()
    (event,) = slot_events(slot, STAGE, 1.0, 0, 1.0)
    x0, y0, x1, y1 = map(float, re.search(r"\\move\(([^,]+),([^,]+),([^,]+),([^)]+)\)", event).groups())
    assert x0 == pytest.approx(slot.x_at(slot.shown_ms) + slot.text_offset_x, abs=0.01)
    assert x1 == pytest.approx(slot.x_at(slot.hidden_ms) + slot.text_offset_x, abs=0.01)
    assert x0 > slot.initial_x + slot.text_offset_x
    assert y0 == y1


def test_slot_events_skip_blank_lines():
    events = slot_events(make_slot(body="a\n \nb"), STAGE, 1.0, 0, 1.0)
    assert [event[-1] for event in events] == ["a", "b"]


@pytest.mark.parametrize(("shown_ms", "hidden_ms"), [(1000, 1004), (1000, 1000), (2000, 1000)])
def test_slot_events_are_empty_when_the_end_is_not_after_the_start(shown_ms, hidden_ms):
    assert slot_events(make_slot(shown_ms=shown_ms, hidden_ms=hidden_ms), STAGE, 1.0, 0, 1.0) == []


@pytest.mark.parametrize(("commands", "border"), [([], "&H000000&"), (["black"], "&HFFFFFF&")])
def test_border_color_contrasts_with_the_text_color(commands, border):
    (event,) = slot_events(make_slot(commands=commands), STAGE, 1.0, 0, 1.0)
    assert f"\\3c{border}" in event


def test_build_ass_sorts_events_by_layer_and_paint_order():
    layers = [
        SlotLayer(0, False, [make_slot(body="d", vpos_ms=500), make_slot(body="c", vpos_ms=0)]),
        SlotLayer(2, False, [make_slot(body="b", no=2), make_slot(body="a", no=1)]),
    ]
    ass = build_ass(layers, 1920, 1080, 1.0)
    assert dialogue_layers(ass) == [(0, "a"), (0, "b"), (2, "c"), (2, "d")]


def test_ass_time_formats_centiseconds_as_h_mm_ss_cc():
    assert ass_time(360000 + 2 * 6000 + 3 * 100 + 4) == "1:02:03.04"


def test_ass_color_uses_bgr_order():
    assert ass_color("123456") == "&H563412&"


def test_ass_escape_escapes_backslashes_and_braces():
    assert ass_escape("a\\b{c}") == "a\\\u200bb\\{c\\}"


def test_later_moving_comment_is_painted_over_earlier_fixed_comment():
    fixed = make_slot(commands=["ue"], vpos_ms=10000, no=1)
    moving = make_slot(vpos_ms=11000, no=2)
    assert paint_order([moving, fixed]) == [fixed, moving]


def test_comments_in_the_same_centisecond_are_painted_by_number():
    first, second = make_slot(vpos_ms=10009, no=2), make_slot(vpos_ms=10001, no=1)
    assert paint_order([first, second]) == [second, first]
