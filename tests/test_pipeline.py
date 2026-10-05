import pytest

from yt_dlp_plugins.postprocessor._nicocomments.comments import Chat, CommentLayer, FetchedComments
from yt_dlp_plugins.postprocessor._nicocomments.filters import NG_SCORE_THRESHOLDS
from yt_dlp_plugins.postprocessor._nicocomments.pipeline import layout_comments


def chat(no, score=0, fork="main"):
    return Chat.parse({"no": no, "vposMs": 1000 * no, "body": "comment", "score": score}, fork)


def layout(fetched, chains):
    return layout_comments(fetched, chains, None, NG_SCORE_THRESHOLDS["medium"], "sm9")


def numbers(slot_layers):
    return [(slot_layer.index, [slot.chat.no for slot in slot_layer.slots]) for slot_layer in slot_layers]


def test_layers_keep_their_index_and_translucency(fixed_width_chains):
    fetched = FetchedComments(
        [CommentLayer(0, False, [chat(1, fork="owner")]), CommentLayer(1, True, [chat(2), chat(3)])], False
    )
    slot_layers = layout(fetched, fixed_width_chains)
    assert numbers(slot_layers) == [(0, [1]), (1, [2, 3])]
    assert [slot_layer.translucent for slot_layer in slot_layers] == [False, True]


@pytest.mark.parametrize(("ng_score_disabled", "expected"), [(False, [(1, [3])]), (True, [(1, [2, 3])])])
def test_ng_score_threshold_applies_unless_disabled(fixed_width_chains, ng_score_disabled, expected):
    fetched = FetchedComments([CommentLayer(1, False, [chat(2, -5000), chat(3)])], ng_score_disabled)
    assert numbers(layout(fetched, fixed_width_chains)) == expected


def test_reverse_toggle_of_one_layer_stages_the_comments_of_every_layer_again(fixed_width_chains):
    fetched = FetchedComments(
        [CommentLayer(0, False, [chat(1, fork="owner")]), CommentLayer(1, False, [chat(2)], [(2500, 60000)])], False
    )
    owner_layer, main_layer = layout(fetched, fixed_width_chains)
    assert [(slot.chat.no, slot.reversed) for slot in owner_layer.slots] == [(1, False), (1, False)]
    assert [(slot.chat.no, slot.reversed) for slot in main_layer.slots] == [(2, False), (2, True)]
    assert owner_layer.slots[1].shown_ms == main_layer.slots[1].shown_ms
