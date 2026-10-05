import math
import random
from dataclasses import dataclass, field
from typing import NamedTuple

from .comments import Chat
from .fonts import FontChain

# Values below are taken from the comment renderer of the official web player.
STAGE_HEIGHT = 384
STAGE_WIDTH = STAGE_HEIGHT * 16 / 9
BASE_WIDTH = math.ceil(STAGE_HEIGHT * 4 / 3)
FRAME_MS = 1000 / 60
FRONT_ADJUST_MS = 1000
BEHIND_ADJUST_MS = 1000
FIXED_OVERLAP_TOLERANCE_MS = 200
SLOT_COUNT = 40
LINE_COUNT_FOR_CHARACTER_SIZE = {"big": 7.8, "medium": 11.3, "small": 16.6}
LINE_COUNT_FOR_LINE_HEIGHT = {"big": 8.4, "medium": 13.1, "small": 21}
LINE_COUNT_FOR_LINE_HEIGHT_AT_RESIZE = {"big": 16, "medium": 25.4, "small": 38}
RESIZE_LINE_COUNT = {"big": 3, "medium": 5, "small": 7}
OVERLAP_EPSILON = 1e-4
STROKE_WIDTH = 2.8
FONT_SIZE_RATIO = 0.8
MIN_FONT_PX = 10


def next_frame_ms(ms: float) -> float:
    return math.ceil(ms / FRAME_MS) * FRAME_MS


def font_px(character_size: float) -> tuple[int, float]:
    px = character_size * FONT_SIZE_RATIO
    if px < MIN_FONT_PX:
        if px >= 1:
            px = math.floor(px)
        return MIN_FONT_PX, px / MIN_FONT_PX
    return math.floor(px), 1.0


class Timing(NamedTuple):
    staging_ms: float
    start_ms: float
    end_ms: float
    hidden_ms: float


def chat_timing(chat: Chat, content_length_ms: float | None) -> Timing:
    view = chat.view_time_ms
    if chat.is_fixed:
        start, end = chat.vpos_ms, chat.vpos_ms + view
        if content_length_ms is not None and content_length_ms - chat.vpos_ms < view:
            start, end = content_length_ms - view, content_length_ms
        staging, hidden = start, end
    else:
        start, end = chat.vpos_ms - FRONT_ADJUST_MS, chat.vpos_ms + view
        if content_length_ms is not None and end > content_length_ms:
            start, end = content_length_ms - (view + FRONT_ADJUST_MS), content_length_ms
        staging, hidden = start - FRONT_ADJUST_MS, end + BEHIND_ADJUST_MS
    if content_length_ms is not None:
        hidden = min(hidden, content_length_ms)
    return Timing(staging, start, end, hidden)


@dataclass
class Slot:
    chat: Chat
    font_chain: FontChain
    character_size: float
    line_height: float
    text_width: float = field(init=False)
    width: float = field(init=False)
    height: float = field(init=False)
    start_ms: float = 0.0
    end_ms: float = 0.0
    initial_x: float = 0.0
    target_x: float = 0.0
    y: float = 0.0
    shown_ms: float = 0.0
    hidden_ms: float = 0.0
    reversed: bool = False
    _line_widths: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.set_size(self.character_size, self.line_height)

    def measure(self, character_size: float, line_height: float) -> tuple[float, float, float]:
        px, shrink = font_px(character_size)
        if px not in self._line_widths:
            self._line_widths[px] = [self.font_chain.text_width(line, px) for line in self.chat.lines]
        widths = self._line_widths[px]
        width = max(math.ceil(w * shrink) for w in widths)
        count = len(self.chat.lines)
        height = line_height * (count - 1) + character_size if count > 1 else character_size
        return width, height, max(widths) * shrink

    def set_size(self, character_size: float, line_height: float) -> None:
        self.character_size, self.line_height = character_size, line_height
        self.width, self.height, self.text_width = self.measure(character_size, line_height)

    @property
    def em(self) -> float:
        px, shrink = font_px(self.character_size)
        return px * shrink

    @property
    def text_offset_x(self) -> float:
        return (self.width - self.text_width) / 2

    def line_baselines(self) -> list[float]:
        px, shrink = font_px(self.character_size)
        top, bottom = self.font_chain.metrics_bounds(px)
        line_count = len(self.chat.lines)
        unshrunk_line_height = self.line_height / shrink
        unshrunk_stroke = STROKE_WIDTH / shrink
        text_height = (
            max(unshrunk_line_height, top + bottom + unshrunk_stroke) + (line_count - 1) * unshrunk_line_height
        )
        # Copies the official player, which multiplies the text height by shrink
        # although the height already includes it.
        centered_top = (self.height - text_height * shrink * shrink) / 2
        text_top = centered_top + self.font_chain.adjust_baseline * self.line_height * shrink
        first = self.y + text_top + STROKE_WIDTH / 2 + top * shrink
        return [first + i * self.line_height for i in range(line_count)]

    def x_at(self, t: float) -> float:
        if self.end_ms == self.start_ms:
            return self.initial_x
        return self.initial_x + (self.target_x - self.initial_x) * (t - self.start_ms) / (self.end_ms - self.start_ms)

    def screen_x_at(self, t: float) -> float:
        # The official player uses the reversed position only for drawing, not for collision checks.
        if self.reversed:
            return self.initial_x + self.target_x - self.x_at(t)
        return self.x_at(t)


@dataclass
class SlotLayer:
    index: int
    translucent: bool
    slots: list[Slot]


def default_character_size(size: str) -> float:
    return STAGE_HEIGHT / LINE_COUNT_FOR_CHARACTER_SIZE[size]


def default_line_height(size: str) -> float:
    return (STAGE_HEIGHT - default_character_size(size)) / (LINE_COUNT_FOR_LINE_HEIGHT[size] - 1)


def resized_line_height(size: str) -> float:
    resized = LINE_COUNT_FOR_LINE_HEIGHT_AT_RESIZE[size]
    return (STAGE_HEIGHT - LINE_COUNT_FOR_LINE_HEIGHT[size] / resized * default_character_size(size)) / (resized - 1)


class Stage:
    def __init__(
        self,
        content_length_ms: float | None,
        font_chains: dict[str, FontChain],
        rng: random.Random,
    ):
        self.content_length_ms = content_length_ms
        self.font_chains = font_chains
        self.rng = rng

    def make_slot(self, chat: Chat, timing: Timing) -> Slot:
        slot = Slot(
            chat=chat,
            font_chain=self.font_chains[chat.font_key],
            character_size=default_character_size(chat.size),
            line_height=default_line_height(chat.size),
        )
        self.resize_if_needed(slot)
        slot.start_ms, slot.end_ms, slot.hidden_ms = timing.start_ms, timing.end_ms, timing.hidden_ms
        if chat.is_fixed:
            slot.initial_x = slot.target_x = STAGE_WIDTH / 2 - slot.width / 2
        else:
            slot.initial_x = STAGE_WIDTH / 2 + BASE_WIDTH / 2
            slot.target_x = STAGE_WIDTH / 2 - BASE_WIDTH / 2 - slot.width
        return slot

    def resize_if_needed(self, slot: Slot) -> None:
        chat = slot.chat
        original_character_size, original_line_height = slot.character_size, slot.line_height
        limit = STAGE_WIDTH if chat.full else BASE_WIDTH
        too_many_lines = len(chat.lines) >= RESIZE_LINE_COUNT[chat.size] and not chat.ender
        if not (slot.width > limit and chat.is_fixed) and not too_many_lines:
            return

        if too_many_lines:
            line_height = resized_line_height(chat.size)
            character_size = slot.character_size * (line_height / slot.line_height)
        else:
            character_size, line_height = slot.character_size, slot.line_height
        width, _, _ = slot.measure(character_size, line_height)
        fit_to_width = width > limit and chat.is_fixed

        if fit_to_width:
            before_fit = character_size
            ratio = limit / width
            character_size, line_height = character_size * ratio, line_height * ratio
            width, _, _ = slot.measure(character_size, line_height)
            if width > limit:
                while width >= limit and character_size > 1:
                    new_character_size = character_size - 1
                    line_height *= new_character_size / character_size
                    character_size = new_character_size
                    width, _, _ = slot.measure(character_size, line_height)
            else:
                while True:
                    previous = (character_size, line_height)
                    new_character_size = character_size + 1
                    line_height *= new_character_size / character_size
                    character_size = new_character_size
                    width, _, _ = slot.measure(character_size, line_height)
                    if width >= limit:
                        break
                character_size, line_height = previous
            if too_many_lines:
                ratio = character_size / before_fit
                character_size, line_height = original_character_size * ratio, original_line_height * ratio
        slot.set_size(character_size, line_height)

    def staging_y(self, slot: Slot, staged: list[Slot]) -> float:
        position = slot.chat.position
        if slot.height >= STAGE_HEIGHT:
            if position == "shita":
                return STAGE_HEIGHT - slot.height
            if position == "ue":
                return 0.0
            return -(slot.height - STAGE_HEIGHT) / 2

        if position == "shita":
            y, downward, limit = STAGE_HEIGHT - slot.height, False, 0.0
        else:
            y, downward, limit = 0.0, True, STAGE_HEIGHT

        while True:
            moved = overflow = False
            for other in staged:
                if other.chat.position != position:
                    continue
                if other.y + other.height <= y + OVERLAP_EPSILON or y + slot.height <= other.y + OVERLAP_EPSILON:
                    continue
                if not self.collides(slot, other):
                    continue
                if slot.chat.is_fixed and other.end_ms - slot.start_ms <= FIXED_OVERLAP_TOLERANCE_MS:
                    continue
                if downward:
                    y = other.y + other.height
                    overflow = y + slot.height > limit
                else:
                    y = other.y - slot.height
                    overflow = y < limit
                moved = not overflow
                break
            if overflow:
                return self.rng.random() * (STAGE_HEIGHT - slot.height)
            if not moved:
                return y

    @staticmethod
    def collides(new: Slot, other: Slot) -> bool:
        return (
            new.initial_x <= other.x_at(new.start_ms) + other.width
            or new.x_at(other.end_ms) <= other.target_x + other.width
        )

    def run_layer(
        self,
        chats: list[Chat],
        reverse_ranges: list[tuple[float, float]] = (),
        refresh_frames: list[float] = (),
    ) -> list[Slot]:
        timed_chats = sorted(
            ((chat_timing(chat, self.content_length_ms), chat) for chat in chats),
            key=lambda item: (item[0].staging_ms, item[1].no),
        )
        toggles = dict(reverse_toggle_frames(reverse_ranges))
        refreshes = sorted({*toggles, *refresh_frames})
        staged: list[Slot] = []
        result: list[Slot] = []
        reversed_moving = False

        def stage(timing: Timing, chat: Chat, frame: float) -> None:
            nonlocal staged
            slot = self.make_slot(chat, timing)
            slot.reversed = reversed_moving
            staged = [s for s in staged if next_frame_ms(s.hidden_ms) >= frame]
            if len(staged) >= SLOT_COUNT:
                evicted = staged.pop(0)
                evicted.hidden_ms = min(evicted.hidden_ms, frame)
            slot.y = self.staging_y(slot, staged)
            slot.shown_ms = frame
            staged.append(slot)
            result.append(slot)

        def refresh(frame: float, earlier: list[tuple[Timing, Chat]]) -> None:
            # The official player removes all comments of every layer and stages the visible ones again.
            nonlocal staged
            for slot in staged:
                slot.hidden_ms = min(slot.hidden_ms, frame)
            staged = []
            for timing, chat in earlier:
                if next_frame_ms(max(0.0, timing.staging_ms)) <= frame < timing.hidden_ms:
                    stage(timing, chat, frame)

        def refresh_until(frame: float, earlier: list[tuple[Timing, Chat]]) -> None:
            nonlocal reversed_moving
            while refreshes and refreshes[0] <= frame:
                refresh_frame = refreshes.pop(0)
                reversed_moving = toggles.get(refresh_frame, reversed_moving)
                refresh(refresh_frame, earlier)

        for i, (timing, chat) in enumerate(timed_chats):
            frame = next_frame_ms(max(0.0, timing.staging_ms))
            refresh_until(frame, timed_chats[:i])
            if frame >= timing.hidden_ms:
                continue
            stage(timing, chat, frame)
        refresh_until(math.inf, timed_chats)
        return result


def reverse_toggle_frames(ranges: list[tuple[float, float]]) -> list[tuple[float, bool]]:
    frames = sorted({next_frame_ms(max(0.0, t)) for start, end in ranges for t in (start, end) if math.isfinite(t)})
    toggles = []
    current = False
    for frame in frames:
        active = any(start <= frame < end for start, end in ranges)
        if active != current:
            toggles.append((frame, active))
            current = active
    return toggles
