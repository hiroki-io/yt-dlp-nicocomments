import re
from dataclasses import dataclass, field
from typing import Literal, get_args

from .font_files import FontKey

VIEW_TIME_MS = 3000
MAX_BODY_LENGTH = 10000
MAX_AT_SECONDS = 1e9
Position = Literal["ue", "naka", "shita"]
Size = Literal["big", "medium", "small"]
CommandKind = Literal["position", "size", "color", "font"]
POSITIONS: tuple[Position, ...] = get_args(Position)
SIZES: tuple[Size, ...] = get_args(Size)
FONT_KEYS: tuple[FontKey, ...] = get_args(FontKey)
BASIC_COLORS = {
    "white": "FFFFFF",
    "red": "FF0000",
    "pink": "FF8080",
    "orange": "FFC000",
    "yellow": "FFFF00",
    "green": "00FF00",
    "cyan": "00FFFF",
    "blue": "0000FF",
    "purple": "C000FF",
    "black": "000000",
}
PREMIUM_COLORS = {
    "white2": "CCCC99",
    "niconicowhite": "CCCC99",
    "red2": "CC0033",
    "truered": "CC0033",
    "orange2": "FF6600",
    "passionorange": "FF6600",
    "yellow2": "999900",
    "madyellow": "999900",
    "green2": "00CC66",
    "elementalgreen": "00CC66",
    "blue2": "3399FF",
    "marineblue": "3399FF",
    "purple2": "6633CC",
    "nobleviolet": "6633CC",
    "pink2": "FF33CC",
    "cyan2": "00CCCC",
    "black2": "666666",
}
COLORS = BASIC_COLORS | PREMIUM_COLORS
AI_COMMENT_COLOR = "DCDCDC"
OWNER_FORK = "owner"
AI_FORK = "ai"
COLOR_CODE = re.compile(r"#[0-9a-f]{6}")
# The official player treats any 6 ASCII letters or digits as a color code when it checks command kinds.
COLOR_CODE_COMMAND = re.compile(r"#[a-zA-Z0-9]{6}")
DURATION_COMMAND = re.compile(r"@([0-9]+(?:\.[0-9]+)?)")
LINE_BREAK = re.compile(r"\r\n|\r|\n")
SCRIPT_PREFIXES = ("@", "\uff20")


def is_premium_color(command: str) -> bool:
    return command.lower() in PREMIUM_COLORS or bool(COLOR_CODE_COMMAND.fullmatch(command))


def command_kind(command: str, premium: bool) -> CommandKind | None:
    lower = command.lower()
    if lower in POSITIONS:
        return "position"
    if lower in SIZES:
        return "size"
    if lower in BASIC_COLORS or (premium and is_premium_color(command)):
        return "color"
    if lower in FONT_KEYS:
        return "font"
    return None


def allowed_commands(raw: dict) -> list[str]:
    commands = raw.get("commands") or []
    if raw.get("isPremium"):
        return list(commands)
    return [c for c in commands if not is_premium_color(c)]


def is_script_body(body: str) -> bool:
    return body.strip()[:1] in SCRIPT_PREFIXES or body.startswith("/")


def color_value(command: str) -> str | None:
    lower = command.lower()
    if lower in COLORS:
        return COLORS[lower]
    return lower[1:].upper() if COLOR_CODE.fullmatch(lower) else None


@dataclass
class Chat:
    no: int
    vpos_ms: int
    is_owner: bool
    score: int
    lines: list[str]
    full: bool
    ender: bool
    invisible: bool
    live: bool
    position: Position
    size: Size
    color: str
    font_key: FontKey
    at_seconds: float | None

    @classmethod
    def parse(cls, *, no: int, vpos_ms: int, score: int, body: str, commands: list[str], fork: str) -> "Chat":
        position = size = color = font_key = at = None
        is_owner = fork == OWNER_FORK
        for command in commands:
            lower = command.lower()
            if lower in POSITIONS:
                position = position or lower
            elif lower in SIZES:
                size = size or lower
            elif lower in BASIC_COLORS or is_premium_color(command):
                color = color or color_value(command)
            elif lower in FONT_KEYS:
                font_key = font_key or lower
            elif is_owner and at is None and (m := DURATION_COMMAND.fullmatch(command)):
                seconds = float(m[1])
                if seconds > 0:
                    at = min(seconds, MAX_AT_SECONDS)
        return cls(
            no=no,
            vpos_ms=vpos_ms,
            is_owner=is_owner,
            score=score,
            lines=LINE_BREAK.split(body.replace("\t", "  ")),
            full="full" in commands,
            ender="ender" in commands,
            invisible="invisible" in commands,
            live="_live" in commands,
            position=position or "naka",
            size=size or "medium",
            color=AI_COMMENT_COLOR if fork == AI_FORK else color or COLORS["white"],
            font_key=font_key or "defont",
            at_seconds=at,
        )

    @property
    def is_fixed(self) -> bool:
        return self.position != "naka"

    @property
    def view_time_ms(self) -> float:
        return self.at_seconds * 1000 if self.at_seconds is not None else VIEW_TIME_MS


@dataclass
class CommentLayer:
    index: int
    translucent: bool
    chats: list[Chat]
    reverse_ranges: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class VideoComments:
    layers: list[CommentLayer]
    ng_score_disabled: bool
