import random

import pytest

from yt_dlp_plugins.postprocessor._nicocomments.comments import Chat
from yt_dlp_plugins.postprocessor._nicocomments.layout import (
    BASE_WIDTH,
    SLOT_COUNT,
    STAGE_HEIGHT,
    STAGE_WIDTH,
    Stage,
    chat_timing,
)


def chat(vpos_ms=10000, body="comment", commands=(), no=1):
    return Chat.parse({"no": no, "vposMs": vpos_ms, "body": body, "commands": list(commands)}, "owner")


def make_stage(font_chains):
    return Stage(None, font_chains, random.Random(0))


def make_slot(stage, chat):
    return stage.make_slot(chat, chat_timing(chat, stage.content_length_ms))


def test_moving_comment_timing():
    assert chat_timing(chat(vpos_ms=10000), None) == (8000, 9000, 13000, 14000)


def test_fixed_comment_timing():
    assert chat_timing(chat(vpos_ms=10000, commands=["ue"]), None) == (10000, 10000, 13000, 13000)


def test_at_command_sets_the_view_time():
    assert chat_timing(chat(vpos_ms=10000, commands=["@5"]), None) == (8000, 9000, 15000, 16000)


def test_comments_near_the_end_finish_at_the_end():
    assert chat_timing(chat(vpos_ms=10000), 11000) == (6000, 7000, 11000, 11000)
    assert chat_timing(chat(vpos_ms=10000, commands=["shita"]), 11000) == (8000, 8000, 11000, 11000)


def test_moving_comment_crosses_the_4_3_area(fixed_width_chains):
    slot = make_slot(make_stage(fixed_width_chains), chat())
    assert slot.x_at(slot.start_ms) == pytest.approx(STAGE_WIDTH / 2 + BASE_WIDTH / 2)
    assert slot.x_at(slot.end_ms) == pytest.approx(STAGE_WIDTH / 2 - BASE_WIDTH / 2 - slot.width)


def test_comments_at_the_same_time_are_placed_in_different_rows(fixed_width_chains):
    stage = make_stage(fixed_width_chains)
    first, second = stage.run_layer([chat(no=1), chat(no=2)])
    assert first.y == 0
    assert second.y == pytest.approx(first.height)


def test_bottom_comments_stack_upward(fixed_width_chains):
    stage = make_stage(fixed_width_chains)
    first, second = stage.run_layer([chat(no=1, commands=["shita"]), chat(no=2, commands=["shita"])])
    assert first.y == pytest.approx(STAGE_HEIGHT - first.height)
    assert second.y == pytest.approx(first.y - second.height)


def test_fixed_comments_can_overlap_for_200_ms(fixed_width_chains):
    stage = make_stage(fixed_width_chains)
    first, second = stage.run_layer([chat(0, commands=["ue"], no=1), chat(2800, commands=["ue"], no=2)])
    assert first.y == second.y == 0


def test_fixed_comments_that_overlap_for_more_than_200_ms_are_placed_in_different_rows(fixed_width_chains):
    stage = make_stage(fixed_width_chains)
    first, second = stage.run_layer([chat(0, commands=["ue"], no=1), chat(2700, commands=["ue"], no=2)])
    assert second.y == pytest.approx(first.height)


def test_new_comment_hides_the_oldest_when_the_layer_is_full(fixed_width_chains):
    stage = make_stage(fixed_width_chains)
    slots = stage.run_layer([chat(no=i) for i in range(SLOT_COUNT + 1)])
    assert slots[0].hidden_ms == slots[SLOT_COUNT].shown_ms
    assert all(slot.hidden_ms == chat_timing(chat(), None).hidden_ms for slot in slots[1:])


def test_wide_fixed_comment_shrinks_to_the_4_3_width(fixed_width_chains):
    slot = make_slot(make_stage(fixed_width_chains), chat(body="x" * 40, commands=["ue"]))
    assert BASE_WIDTH * 0.9 < slot.width < BASE_WIDTH


def test_full_command_uses_the_16_9_width(fixed_width_chains):
    slot = make_slot(make_stage(fixed_width_chains), chat(body="x" * 40, commands=["ue", "full"]))
    assert BASE_WIDTH < slot.width < STAGE_WIDTH


def test_many_lines_reduce_the_line_height(fixed_width_chains):
    stage = make_stage(fixed_width_chains)
    normal = make_slot(stage, chat(body="a\nb"))
    many = make_slot(stage, chat(body="\n".join("abcde")))
    ender = make_slot(stage, chat(body="\n".join("abcde"), commands=["ender"]))
    assert many.line_height < normal.line_height
    assert ender.line_height == pytest.approx(normal.line_height)


def test_line_baselines_are_one_line_height_apart(fixed_width_chains):
    slot = make_slot(make_stage(fixed_width_chains), chat(body="a\nb\nc"))
    first, second, third = slot.line_baselines()
    assert slot.y < first < slot.y + slot.height
    assert second - first == pytest.approx(slot.line_height)
    assert third - second == pytest.approx(slot.line_height)
