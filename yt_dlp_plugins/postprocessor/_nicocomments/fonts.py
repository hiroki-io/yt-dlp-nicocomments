import math
import os
import struct
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import BinaryIO

METRICS_STRING = "|ÉqÅM"
JAPANESE_SAMPLE = "あア漢"
FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".otc")


@dataclass(frozen=True)
class ChainSpec:
    weight: int
    adjust_baseline: float
    face_names: tuple[str, ...]


# The font families that the official player uses on each platform, as the
# PostScript names of the faces that a browser selects for the CSS weight.
CHAIN_SPECS = {
    "darwin": {
        "defont": ChainSpec(600, -0.05, ("HiraginoSans-W6",)),
        "gothic": ChainSpec(400, -0.04, ("YuGo-Medium", "HiraginoSans-W4")),
        "mincho": ChainSpec(400, -0.01, ("YuMin-Medium", "HiraMinProN-W3", "HiraginoSans-W4")),
    },
    "win32": {
        "defont": ChainSpec(600, 0.01, ("Arial-BoldMT", "MS-PGothic")),
        "gothic": ChainSpec(400, -0.04, ("YuGothic-Regular", "SimSun", "ArialMT", "MS-PGothic")),
        "mincho": ChainSpec(400, -0.01, ("YuMincho-Regular", "SimSun", "ArialMT", "MS-PGothic")),
    },
    "linux": {
        "defont": ChainSpec(600, 0.0, ("NotoSansCJKjp-Bold",)),
        "gothic": ChainSpec(400, 0.0, ("NotoSansCJKjp-Regular",)),
        "mincho": ChainSpec(400, 0.0, ("NotoSerifCJKjp-Regular",)),
    },
}
# Ink bounds of METRICS_STRING above and below the baseline, in font units.
# CFF fonts have no table of glyph bounds, so these values are measured once.
CFF_METRICS_STRING_BOUNDS = {
    "HiraginoSans-W6": (1044, 207),
    "HiraginoSans-W4": (1007, 205),
    "HiraMinProN-W3": (985, 182),
    "YuGo-Medium": (1005, 163),
    "YuMin-Medium": (990, 209),
    "NotoSansCJKjp-Bold": (1010, 284),
    "NotoSansCJKjp-Regular": (983, 279),
    "NotoSerifCJKjp-Regular": (973, 272),
}


class FontError(Exception):
    pass


def _unpack(f: BinaryIO, offset: int, fmt: str) -> tuple:
    f.seek(offset)
    return struct.unpack(fmt, f.read(struct.calcsize(fmt)))


def _face_offsets(f: BinaryIO) -> list[int]:
    if _unpack(f, 0, ">4s")[0] != b"ttcf":
        return [0]
    count = _unpack(f, 8, ">I")[0]
    return list(_unpack(f, 12, f">{count}I"))


def _read_table_directory(f: BinaryIO, offset: int) -> dict[bytes, tuple[int, int]]:
    tables = {}
    for i in range(_unpack(f, offset + 4, ">H")[0]):
        tag, _, table_offset, length = _unpack(f, offset + 12 + 16 * i, ">4sIII")
        tables[tag] = (table_offset, length)
    return tables


def _read_table(f: BinaryIO, tables: dict[bytes, tuple[int, int]], tag: bytes) -> bytes:
    offset, length = tables[tag]
    f.seek(offset)
    return f.read(length)


def parse_names(data: bytes) -> dict[int, str]:
    count, string_offset = struct.unpack_from(">HH", data, 2)
    ranked = {}
    for i in range(count):
        platform, encoding, language, name_id, length, offset = struct.unpack_from(">6H", data, 6 + 12 * i)
        if platform == 3 and language == 0x409:
            rank = 0
        elif platform in (0, 3):
            rank = 1
        elif platform == 1 and encoding == 0 and language == 0:
            rank = 2
        else:
            continue
        if name_id in ranked and ranked[name_id][0] <= rank:
            continue
        raw = data[string_offset + offset : string_offset + offset + length]
        text = raw.decode("utf-16-be", "replace") if platform in (0, 3) else raw.decode("mac_roman", "replace")
        ranked[name_id] = (rank, text)
    return {name_id: text for name_id, (_, text) in ranked.items()}


def parse_cmap(data: bytes) -> dict[int, int]:
    subtables = {}
    for i in range(struct.unpack_from(">H", data, 2)[0]):
        platform, encoding, offset = struct.unpack_from(">HHI", data, 4 + 8 * i)
        subtables[(platform, encoding)] = offset
    for key in ((3, 10), (0, 6), (0, 4)):
        if key in subtables and struct.unpack_from(">H", data, subtables[key])[0] == 12:
            return _parse_cmap_format12(data, subtables[key])
    for key in ((3, 1), (0, 3)):
        if key in subtables and struct.unpack_from(">H", data, subtables[key])[0] == 4:
            return _parse_cmap_format4(data, subtables[key])
    raise ValueError("no supported Unicode cmap subtable")


def _parse_cmap_format12(data: bytes, offset: int) -> dict[int, int]:
    mapping = {}
    for i in range(struct.unpack_from(">I", data, offset + 12)[0]):
        start, end, glyph = struct.unpack_from(">III", data, offset + 16 + 12 * i)
        for code in range(start, end + 1):
            mapping[code] = glyph + code - start
    return mapping


def _parse_cmap_format4(data: bytes, offset: int) -> dict[int, int]:
    seg_count = struct.unpack_from(">H", data, offset + 6)[0] // 2
    ends = offset + 14
    starts = ends + 2 * seg_count + 2
    deltas = starts + 2 * seg_count
    range_offsets = deltas + 2 * seg_count
    mapping = {}
    for i in range(seg_count):
        end = struct.unpack_from(">H", data, ends + 2 * i)[0]
        start = struct.unpack_from(">H", data, starts + 2 * i)[0]
        delta = struct.unpack_from(">h", data, deltas + 2 * i)[0]
        range_offset = struct.unpack_from(">H", data, range_offsets + 2 * i)[0]
        for code in range(start, end + 1):
            if range_offset == 0:
                glyph = (code + delta) & 0xFFFF
            else:
                address = range_offsets + 2 * i + range_offset + 2 * (code - start)
                glyph = struct.unpack_from(">H", data, address)[0]
                if glyph:
                    glyph = (glyph + delta) & 0xFFFF
            if glyph:
                mapping[code] = glyph
    return mapping


def _glyf_bounds(f: BinaryIO, tables: dict[bytes, tuple[int, int]], glyphs: list[int]) -> tuple[int, int] | None:
    if b"glyf" not in tables or b"loca" not in tables:
        return None
    long_offsets = _unpack(f, tables[b"head"][0] + 50, ">h")[0] == 1
    loca = _read_table(f, tables, b"loca")
    glyf_offset = tables[b"glyf"][0]
    top = bottom = 0
    for glyph in glyphs:
        if long_offsets:
            start, end = struct.unpack_from(">II", loca, 4 * glyph)
        else:
            start, end = (2 * value for value in struct.unpack_from(">HH", loca, 2 * glyph))
        if start == end:
            continue
        _, y_min, _, y_max = _unpack(f, glyf_offset + start + 2, ">4h")
        top, bottom = max(top, y_max), max(bottom, -y_min)
    return top, bottom


@dataclass
class Face:
    postscript_name: str
    full_name: str
    is_cff: bool
    weight_class: int
    units_per_em: int
    win_ascent: int
    win_height: int
    advances: list[int]
    cmap: dict[int, int]
    metrics_bounds: tuple[int, int] | None

    @classmethod
    def load(cls, path: Path, offset: int) -> "Face":
        with open(path, "rb") as f:
            tables = _read_table_directory(f, offset)
            names = parse_names(_read_table(f, tables, b"name"))
            units_per_em = _unpack(f, tables[b"head"][0] + 18, ">H")[0]
            weight_class = _unpack(f, tables[b"OS/2"][0] + 4, ">H")[0]
            win_ascent, win_descent = _unpack(f, tables[b"OS/2"][0] + 74, ">HH")
            metric_count = _unpack(f, tables[b"hhea"][0] + 34, ">H")[0]
            hmtx = _read_table(f, tables, b"hmtx")
            cmap = parse_cmap(_read_table(f, tables, b"cmap"))
            bounds = None
            if all(ord(char) in cmap for char in METRICS_STRING):
                bounds = _glyf_bounds(f, tables, [cmap[ord(char)] for char in METRICS_STRING])
        postscript_name = names.get(6, "")
        bounds = bounds or CFF_METRICS_STRING_BOUNDS.get(postscript_name)
        return cls(
            postscript_name,
            names.get(4, postscript_name),
            b"CFF " in tables or b"CFF2" in tables,
            weight_class,
            units_per_em,
            win_ascent,
            win_ascent + win_descent,
            [advance for advance, _ in struct.iter_unpack(">Hh", hmtx[: 4 * metric_count])],
            cmap,
            bounds,
        )

    def has_char(self, char: str) -> bool:
        return ord(char) in self.cmap

    def advance(self, char: str) -> int:
        glyph = self.cmap.get(ord(char), 0)
        return self.advances[min(glyph, len(self.advances) - 1)]


@dataclass
class FontChain:
    faces: list[Face]
    weight: int
    adjust_baseline: float
    missing: tuple[str, ...] = ()

    def covers(self, text: str) -> bool:
        return all(any(face.has_char(char) for face in self.faces) for char in text)

    def face_for(self, char: str) -> Face:
        return next((face for face in self.faces if face.has_char(char)), self.faces[0])

    def runs(self, text: str) -> list[tuple[Face, str]]:
        runs: list[tuple[Face, str]] = []
        for char in text:
            face = self.face_for(char)
            if runs and runs[-1][0] is face:
                runs[-1] = (face, runs[-1][1] + char)
            else:
                runs.append((face, char))
        return runs

    def text_width(self, text: str, px: int) -> float:
        width = 0.0
        for char in text:
            face = self.face_for(char)
            width += face.advance(char) / face.units_per_em
        return width * px

    def metrics_bounds(self, px: int) -> tuple[int, int]:
        face = next(face for face in self.faces if face.metrics_bounds)
        top, bottom = face.metrics_bounds
        return math.ceil(top * px / face.units_per_em), math.ceil(bottom * px / face.units_per_em)

    def synthetic_bold(self, face: Face) -> bool:
        # Browsers synthesize bold when the CSS weight is bold and the face is not.
        return self.weight >= 600 and face.weight_class < 600


def platform_key() -> str:
    return sys.platform if sys.platform in ("darwin", "win32") else "linux"


def font_directories() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        assets = Path("/System/Library/AssetsV2")
        return [
            Path("/System/Library/Fonts"),
            *sorted(assets.glob("com_apple_MobileAsset_Font*")),
            Path("/Library/Fonts"),
            home / "Library/Fonts",
        ]
    if sys.platform == "win32":
        directories = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
        if local_app_data := os.environ.get("LOCALAPPDATA"):
            directories.append(Path(local_app_data) / "Microsoft/Windows/Fonts")
        return directories
    data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), data_home / "fonts", home / ".fonts"]


def find_faces(names: set[str]) -> dict[str, tuple[Path, int]]:
    found: dict[str, tuple[Path, int]] = {}
    for directory in font_directories():
        for root, _, files in os.walk(directory, followlinks=True):
            for file in sorted(files):
                if not file.lower().endswith(FONT_EXTENSIONS):
                    continue
                path = Path(root) / file
                try:
                    with open(path, "rb") as f:
                        for offset in _face_offsets(f):
                            tables = _read_table_directory(f, offset)
                            name = parse_names(_read_table(f, tables, b"name")).get(6)
                            if name in names and name not in found:
                                found[name] = (path, offset)
                except (OSError, KeyError, struct.error):
                    continue
                if len(found) == len(names):
                    return found
    return found


@cache
def load_font_chains() -> dict[str, FontChain]:
    specs = CHAIN_SPECS[platform_key()]
    names = {name for spec in specs.values() for name in spec.face_names}
    locations = find_faces(names)
    faces = {}
    for name, (path, offset) in locations.items():
        try:
            faces[name] = Face.load(path, offset)
        except (OSError, KeyError, ValueError, struct.error) as e:
            raise FontError(f"cannot read {name} from {path}: {e!r}") from e
    chains = {}
    for key, spec in specs.items():
        available = [faces[name] for name in spec.face_names if name in faces]
        if not available:
            raise FontError(f"none of the fonts for {key} are installed: {', '.join(spec.face_names)}")
        if not any(face.metrics_bounds for face in available):
            raise FontError(f"no glyph bounds for the fonts of {key}: {', '.join(spec.face_names)}")
        missing = tuple(name for name in spec.face_names if name not in faces)
        chains[key] = FontChain(available, spec.weight, spec.adjust_baseline, missing)
    return chains
