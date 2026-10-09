import random

from .comments import VideoComments
from .filters import visible_chats
from .font_files import FontKey
from .fonts import FontChain
from .layout import SlotLayer, Stage, reverse_toggle_frames


def layout_comments(
    comments: VideoComments,
    font_chains: dict[FontKey, FontChain],
    content_length_ms: float | None,
    ng_score_threshold: int | None,
    seed: str,
) -> list[SlotLayer]:
    stage = Stage(content_length_ms, font_chains, random.Random(seed))
    if comments.ng_score_disabled:
        ng_score_threshold = None
    refresh_frames = sorted(
        {frame for layer in comments.layers for frame, _ in reverse_toggle_frames(layer.reverse_ranges)}
    )
    return [
        SlotLayer(
            layer.index,
            layer.translucent,
            stage.run_layer(visible_chats(layer.chats, ng_score_threshold), layer.reverse_ranges, refresh_frames),
        )
        for layer in comments.layers
    ]
