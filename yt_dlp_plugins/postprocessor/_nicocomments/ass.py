from dataclasses import dataclass

from .comments import Chat
from .fonts import Face, FontChain
from .layout import STAGE_HEIGHT, STAGE_WIDTH, STROKE_WIDTH, Slot, SlotLayer

STROKE_OPACITY = 0.4
LIVE_OPACITY = 0.5
TRANSLUCENT_LAYER_OPACITY = 0.5

STYLE_FORMAT = (
    "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)


@dataclass
class Viewport:
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def for_video(cls, video_width: int, video_height: int) -> "Viewport":
        aspect = video_width / video_height
        if aspect < STAGE_WIDTH / STAGE_HEIGHT:
            width = STAGE_HEIGHT * aspect
            return cls((STAGE_WIDTH - width) / 2, 0.0, width, STAGE_HEIGHT)
        height = STAGE_WIDTH / aspect
        return cls(0.0, (STAGE_HEIGHT - height) / 2, STAGE_WIDTH, height)


def ass_font_name(face: Face) -> str:
    # Like GDI, libass finds CFF fonts by the PostScript name and TrueType fonts by the full name.
    return face.postscript_name if face.is_cff else face.full_name


def ass_font_size(face: Face, em: float) -> float:
    # libass scales a font so that usWinAscent + usWinDescent equals \fs,
    # and places the baseline usWinAscent below the top of the line.
    return em * face.win_height / face.units_per_em


def ass_ascent(face: Face, ass_size: float) -> float:
    return ass_size * face.win_ascent / face.win_height


def line_top(runs: list[tuple[Face, str]], em: float, baseline: float) -> float:
    return baseline - max(ass_ascent(face, ass_font_size(face, em)) for face, _ in runs)


def ass_time(cs: int) -> str:
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def ass_color(rgb: str) -> str:
    return f"&H{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&"


def ass_alpha(opacity: float) -> str:
    return f"&H{round((1 - opacity) * 255):02X}&"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\u200b").replace("{", "\\{").replace("}", "\\}")


def comment_opacity(chat: Chat, translucent: bool) -> float:
    live = LIVE_OPACITY if chat.live else 1.0
    return live * (TRANSLUCENT_LAYER_OPACITY if translucent else 1.0)


def slot_events(slot: Slot, viewport: Viewport, video_scale: float, ass_layer: int, opacity: float) -> list[str]:
    start_cs = round(slot.shown_ms / 10)
    end_cs = round(slot.hidden_ms / 10)
    if end_cs <= start_cs:
        return []
    chat = slot.chat
    em = slot.em
    border = "FFFFFF" if chat.color == "000000" else "000000"
    style = (
        f"\\bord{STROKE_WIDTH / 2 * video_scale:.2f}\\shad0"
        f"\\c{ass_color(chat.color)}\\3c{ass_color(border)}"
        f"\\1a{ass_alpha(opacity)}\\3a{ass_alpha(STROKE_OPACITY * opacity)}"
    )
    x0 = (slot.x_at(start_cs * 10) + slot.text_offset_x - viewport.x) * video_scale
    x1 = (slot.x_at(end_cs * 10) + slot.text_offset_x - viewport.x) * video_scale

    events = []
    for line, baseline in zip(chat.lines, slot.line_baselines(), strict=True):
        if not line.strip():
            continue
        runs = slot.font_chain.runs(line)
        y = (line_top(runs, em, baseline) - viewport.y) * video_scale
        if chat.is_fixed:
            placement = f"\\an7\\pos({x0:.2f},{y:.2f})"
        else:
            placement = f"\\an7\\move({x0:.2f},{y:.2f},{x1:.2f},{y:.2f})"
        events.append(
            f"Dialogue: {ass_layer},{ass_time(start_cs)},{ass_time(end_cs)},Default,,0,0,0,,"
            f"{{{placement}{style}}}{ass_runs(slot.font_chain, runs, em, video_scale)}"
        )
    return events


def ass_runs(chain: FontChain, runs: list[tuple[Face, str]], em: float, video_scale: float) -> str:
    parts = []
    for face, text in runs:
        bold = 1 if chain.synthetic_bold(face) else 0
        size = ass_font_size(face, em) * video_scale
        parts.append(f"{{\\fn{ass_font_name(face)}\\fs{size:.2f}\\b{bold}}}{ass_escape(text)}")
    return "".join(parts)


def ass_header(width: int, height: int) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: {STYLE_FORMAT}
Style: Default,sans-serif,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def paint_order(slots: list[Slot]) -> list[Slot]:
    # The official player stacks comments of a layer by vpos in centiseconds and then by number.
    return sorted(slots, key=lambda slot: (slot.chat.vpos_ms // 10, slot.chat.no))


def build_ass(layers: list[SlotLayer], width: int, height: int, opacity: float) -> str:
    viewport = Viewport.for_video(width, height)
    video_scale = height / viewport.height
    top_index = max((layer.index for layer in layers), default=0)
    events = []
    for layer in sorted(layers, key=lambda layer: -layer.index):
        for slot in paint_order(layer.slots):
            slot_opacity = comment_opacity(slot.chat, layer.translucent) * opacity
            events += slot_events(slot, viewport, video_scale, top_index - layer.index, slot_opacity)
    return ass_header(width, height) + "\n".join(events) + "\n"
