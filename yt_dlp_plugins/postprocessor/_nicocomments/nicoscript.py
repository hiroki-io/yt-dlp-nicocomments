import math
import re
from dataclasses import dataclass, field
from datetime import datetime

from .comments import BASIC_COLORS, FONT_KEYS, POSITIONS, PREMIUM_COLORS, SCRIPT_PREFIXES, SIZES, command_kind

DEFAULT_DURATION_MS = 30000
SCRIPT_TYPES = {"デフォルト": "default", "置換": "replace", "逆": "reverse"}
TARGETS = {"全": frozenset({False, True}), "コメ": frozenset({False}), "投コメ": frozenset({True})}
ESCAPES = {"n": "\n", "r": "\r", "t": "\t"}
FIRST_TOKEN = re.compile(r"(\S*)\s+(.*)", re.DOTALL)
DURATION_TOKEN = re.compile(r"(?:^|\s)@([0-9]+(?:\.[0-9]+)?)(?:\s|$)")
ESCAPE = re.compile(r"\\([^\n\r\u2028\u2029])")
# The official player joins the names without a group, so "^" and "$" bind only to the first and last names.
COMMAND_KIND_PATTERNS = {
    "position": "|".join(POSITIONS),
    "size": "|".join(SIZES),
    "color": "|".join([*BASIC_COLORS, *PREMIUM_COLORS, "^#[0-9a-fA-F]{6}$"]),
    "font": "|".join(FONT_KEYS),
}


def style_commands(raw: dict) -> dict[str, str]:
    commands: dict[str, str] = {}
    for command in raw.get("commands") or []:
        kind = command_kind(command, bool(raw.get("isPremium")))
        if kind is not None and kind not in commands:
            commands[kind] = command
    return commands


def split_first(text: str, quoted: bool) -> tuple[str, str]:
    text = text.strip()
    if quoted:
        end = -1
        unescaped = ""
        if text[:1] in ("'", '"'):
            quote = text[0]
            end = text.find(quote, 1)
            if end >= 0:

                def unescape(m: re.Match) -> str:
                    nonlocal end
                    if m.start() > end:
                        return m[0]
                    if m[1] == quote:
                        end = text.find(quote, end + 1)
                    return ESCAPES.get(m[1], m[1])

                unescaped = ESCAPE.sub(unescape, text)
        elif text.startswith("「"):
            end = text.find("」", 1)
            unescaped = text
        if end >= 0:
            rest = FIRST_TOKEN.fullmatch(text[end + 1 :])
            return unescaped[1 : len(unescaped) - (len(text) - end)], rest[2] if rest else ""
    m = FIRST_TOKEN.fullmatch(text)
    return (m[1], m[2]) if m else (text, "")


def split_arguments(text: str) -> list[str]:
    arguments = []
    while text:
        argument, text = split_first(text, quoted=True)
        arguments.append(argument)
    return arguments


def time_range(raw: dict, default_ms: float) -> tuple[float, float]:
    duration = default_ms
    for command in raw.get("commands") or []:
        if m := DURATION_TOKEN.search(command):
            duration = float(m[1]) * 1000
            break
    return raw["vposMs"], raw["vposMs"] + duration


def posted_at_ms(raw: dict) -> float:
    try:
        return datetime.fromisoformat(raw["postedAt"]).timestamp() * 1000
    except (KeyError, TypeError, ValueError):
        return 0.0


@dataclass
class Default:
    start_ms: float
    end_ms: float
    commands: dict[str, str]
    posted_at_ms: float


@dataclass
class Replacement:
    source: str
    destination: str
    replace_all: bool
    targets: frozenset[bool]
    exact: bool
    start_ms: float
    end_ms: float
    commands: dict[str, str]
    posted_at_ms: float

    def replaced_commands_pattern(self) -> re.Pattern | None:
        if not self.commands:
            return None
        names = "|".join(COMMAND_KIND_PATTERNS[kind] for kind in COMMAND_KIND_PATTERNS if kind in self.commands)
        return re.compile(f"^{names}$", re.IGNORECASE)


@dataclass
class Reversal:
    targets: frozenset[bool]
    start_ms: float
    end_ms: float


@dataclass
class Nicoscripts:
    defaults: list[Default] = field(default_factory=list)
    replacements: list[Replacement] = field(default_factory=list)
    reversals: list[Reversal] = field(default_factory=list)

    @classmethod
    def parse(cls, raws: list[dict]) -> "Nicoscripts":
        scripts = cls()
        for raw in raws:
            name, arguments = split_first(raw.get("body") or "", quoted=False)
            if name[:1] not in SCRIPT_PREFIXES:
                continue
            script_type = SCRIPT_TYPES.get(name[1:])
            if script_type == "default":
                start, end = time_range(raw, math.inf)
                scripts.defaults.append(Default(start, end, style_commands(raw), posted_at_ms(raw)))
            elif script_type == "replace":
                args = split_arguments(arguments) + [""] * 5
                source, destination, mode, target, matching = args[:5]
                if not source:
                    continue
                if target in TARGETS:
                    targets = TARGETS[target]
                elif target == "含む":
                    targets = TARGETS["全"]
                else:
                    targets = TARGETS["コメ"]
                start, end = time_range(raw, DEFAULT_DURATION_MS)
                scripts.replacements.append(
                    Replacement(
                        source,
                        destination,
                        mode == "全",
                        targets,
                        matching == "完全一致",
                        start,
                        end,
                        style_commands(raw),
                        posted_at_ms(raw),
                    )
                )
            elif script_type == "reverse":
                target = (split_arguments(arguments) or [""])[0]
                start, end = time_range(raw, DEFAULT_DURATION_MS)
                scripts.reversals.append(Reversal(TARGETS.get(target, TARGETS["全"]), start, end))
        scripts.defaults.sort(key=lambda d: (d.start_ms, d.posted_at_ms), reverse=True)
        scripts.replacements.sort(key=lambda r: (r.start_ms, r.posted_at_ms))
        return scripts

    def apply(self, *, body: str, vpos_ms: int, commands: list[str], is_owner: bool) -> tuple[str, list[str]]:
        present = {kind for command in commands if (kind := command_kind(command, premium=True))}
        added = []
        for default in self.defaults:
            if default.start_ms <= vpos_ms < default.end_ms:
                added += [command for kind, command in default.commands.items() if kind not in present]
        commands = commands + added

        for replacement in self.replacements:
            if is_owner not in replacement.targets or not replacement.start_ms <= vpos_ms < replacement.end_ms:
                continue
            if replacement.exact:
                if body != replacement.source:
                    continue
            elif replacement.source not in body:
                continue
            if replacement.replace_all:
                body = replacement.destination
            else:
                body = body.replace(replacement.source, replacement.destination)
            if pattern := replacement.replaced_commands_pattern():
                commands = [c for c in commands if not pattern.search(c)] + list(replacement.commands.values())
        return body, commands

    def reverse_ranges(self, is_owner: bool) -> list[tuple[float, float]]:
        return [(r.start_ms, r.end_ms) for r in self.reversals if is_owner in r.targets]
