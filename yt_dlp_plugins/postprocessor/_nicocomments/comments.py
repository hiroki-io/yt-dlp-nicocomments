import re
from dataclasses import dataclass

VIEW_TIME_MS = 3000
POSITIONS = ("ue", "naka", "shita")
SIZES = ("big", "medium", "small")
FONT_KEYS = ("defont", "gothic", "mincho")
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
COLOR_CODE = re.compile(r"#[0-9a-f]{6}")
AT_COMMAND = re.compile(r"@(\d+(?:\.\d+)?)")
LINE_BREAK = re.compile(r"\r\n|\r|\n")


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
    position: str
    size: str
    color: str
    font_key: str
    at_seconds: float | None

    @classmethod
    def parse(cls, raw: dict, fork: str) -> "Chat":
        position = size = color = font_key = at = None
        is_owner = fork == "owner"
        commands = raw.get("commands") or []
        for command in commands:
            lower = command.lower()
            if not raw.get("isPremium") and (lower in PREMIUM_COLORS or COLOR_CODE.fullmatch(lower)):
                continue
            if lower in POSITIONS:
                position = position or lower
            elif lower in FONT_KEYS:
                font_key = font_key or lower
            elif lower in SIZES:
                size = size or lower
            elif lower in COLORS:
                color = color or COLORS[lower]
            elif COLOR_CODE.fullmatch(lower):
                color = color or lower[1:].upper()
            elif is_owner and at is None and (m := AT_COMMAND.fullmatch(command)) and (seconds := float(m[1])) > 0:
                at = seconds
        body = (raw.get("body") or "").replace("\t", "  ")
        return cls(
            no=raw.get("no", 0),
            vpos_ms=raw["vposMs"],
            is_owner=is_owner,
            score=raw.get("score", 0),
            lines=LINE_BREAK.split(body),
            full="full" in commands,
            ender="ender" in commands,
            invisible="invisible" in commands,
            live="_live" in commands,
            position=position or "naka",
            size=size or "medium",
            color=color or COLORS["white"],
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


@dataclass
class FetchedComments:
    layers: list[CommentLayer]
    ng_score_disabled: bool
