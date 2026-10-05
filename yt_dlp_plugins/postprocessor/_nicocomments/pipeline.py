import random

from .comments import FetchedComments
from .filters import effective_ng_score_threshold, visible_chats
from .fonts import FontChain
from .layout import SlotLayer, Stage, reverse_toggle_frames


def layout_comments(
    fetched: FetchedComments,
    font_chains: dict[str, FontChain],
    content_length_ms: float | None,
    ng_score_threshold: int | None,
    seed: str,
) -> list[SlotLayer]:
    stage = Stage(content_length_ms, font_chains, random.Random(seed))
    ng_score_threshold = effective_ng_score_threshold(fetched, ng_score_threshold)
    refresh_frames = sorted(
        {frame for layer in fetched.layers for frame, _ in reverse_toggle_frames(layer.reverse_ranges)}
    )
    return [
        SlotLayer(
            layer.index,
            layer.translucent,
            stage.run_layer(visible_chats(layer.chats, ng_score_threshold), layer.reverse_ranges, refresh_frames),
        )
        for layer in fetched.layers
    ]
