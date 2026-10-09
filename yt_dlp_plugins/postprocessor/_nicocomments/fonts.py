import functools
import hashlib
import importlib.resources
import importlib.util
import io
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from yt_dlp.utils import Popen

from .font_files import (
    CHAIN_FONTS,
    EMOJI,
    FALLBACK_FONTS,
    FONT_DATA_DIRECTORY,
    FONT_FILES,
    METRICS_STRING_BOUNDS,
    FontFile,
    FontKey,
)

if TYPE_CHECKING:
    if sys.version_info >= (3, 11):
        from importlib.resources.abc import Traversable
    else:
        from importlib.abc import Traversable

# Chromium on Linux synthesizes bold for the fallback faces of the CSS weight 600 that defont uses.
SYNTHETIC_BOLD_KEYS: set[FontKey] = {"defont"}

ZERO_WIDTH_CATEGORIES = ("Mn", "Me", "Cf")
ZERO_WIDTH_JOINER = "\u200d"
EMOJI_RANGES = (range(0x2600, 0x27C0), range(0x1F000, 0x1FB00))
EMOJI_MODIFIERS = range(0x1F3FB, 0x1F400)
REGIONAL_INDICATORS = range(0x1F1E6, 0x1F200)


class FontError(Exception):
    pass


def extends_cluster(text: str) -> list[bool]:
    # Browsers shape these characters together with the previous character,
    # so they add no width and use the font of the previous character.
    result = []
    previous = ""
    regional_indicator_count = 0
    for char in text:
        code = ord(char)
        if code in REGIONAL_INDICATORS:
            regional_indicator_count += 1
            result.append(regional_indicator_count % 2 == 0)
        else:
            regional_indicator_count = 0
            result.append(
                unicodedata.category(char) in ZERO_WIDTH_CATEGORIES
                or code in EMOJI_MODIFIERS
                or (previous == ZERO_WIDTH_JOINER and any(code in r for r in EMOJI_RANGES))
            )
        previous = char
    return result


def parse_cmap(data: bytes) -> dict[int, int]:
    subtables: dict[tuple[int, int, int], int] = {}
    for i in range(struct.unpack_from(">H", data, 2)[0]):
        platform, encoding, offset = struct.unpack_from(">HHI", data, 4 + 8 * i)
        subtables.setdefault((platform, encoding, struct.unpack_from(">H", data, offset)[0]), offset)
    if (offset := subtables.get((3, 10, 12))) is not None:
        return parse_cmap_format12(data, offset)
    # Noto Sans Thai has no characters outside the BMP, and this is its only Windows subtable.
    if (offset := subtables.get((3, 1, 4))) is not None:
        return parse_cmap_format4(data, offset)
    raise ValueError("no (3, 10) format 12 or (3, 1) format 4 cmap subtable")


def parse_cmap_format12(data: bytes, offset: int) -> dict[int, int]:
    mapping = {}
    for i in range(struct.unpack_from(">I", data, offset + 12)[0]):
        start, end, glyph = struct.unpack_from(">III", data, offset + 16 + 12 * i)
        for code in range(start, end + 1):
            mapping[code] = glyph + code - start
    return mapping


def parse_cmap_format4(data: bytes, offset: int) -> dict[int, int]:
    count = struct.unpack_from(">H", data, offset + 6)[0] // 2
    ends = struct.unpack_from(f">{count}H", data, offset + 14)
    starts = struct.unpack_from(f">{count}H", data, offset + 16 + 2 * count)
    deltas = struct.unpack_from(f">{count}h", data, offset + 16 + 4 * count)
    range_offsets_start = offset + 16 + 6 * count
    mapping = {}
    for i, (start, end, delta) in enumerate(zip(starts, ends, deltas, strict=True)):
        range_offset_position = range_offsets_start + 2 * i
        range_offset = struct.unpack_from(">H", data, range_offset_position)[0]
        for code in range(start, end + 1):
            if code == 0xFFFF:
                continue
            if range_offset:
                glyph = struct.unpack_from(">H", data, range_offset_position + range_offset + 2 * (code - start))[0]
                if glyph:
                    glyph = (glyph + delta) & 0xFFFF
            else:
                glyph = (code + delta) & 0xFFFF
            if glyph:
                mapping[code] = glyph
    return mapping


def _read_tables(data: bytes) -> dict[bytes, bytes]:
    tables = {}
    for i in range(struct.unpack_from(">H", data, 4)[0]):
        tag, _, offset, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        tables[tag] = data[offset : offset + length]
    return tables


@dataclass
class Face:
    font: FontFile
    units_per_em: int
    win_ascent: int
    win_height: int
    advances: list[int] = field(repr=False)
    cmap: dict[int, int] = field(repr=False)

    @classmethod
    def parse(cls, font: FontFile, data: bytes) -> "Face":
        tables = _read_tables(data)
        win_ascent, win_descent = struct.unpack_from(">HH", tables[b"OS/2"], 74)
        metric_count = struct.unpack_from(">H", tables[b"hhea"], 34)[0]
        return cls(
            font,
            struct.unpack_from(">H", tables[b"head"], 18)[0],
            win_ascent,
            win_ascent + win_descent,
            [advance for advance, _ in struct.iter_unpack(">Hh", tables[b"hmtx"][: 4 * metric_count])],
            parse_cmap(tables[b"cmap"]),
        )

    def has_char(self, char: str) -> bool:
        return ord(char) in self.cmap

    def advance(self, char: str) -> int:
        glyph = self.cmap.get(ord(char), 0)
        return self.advances[min(glyph, len(self.advances) - 1)]


@dataclass
class FontChain:
    faces: list[Face]
    metrics_string_bounds: tuple[int, int]
    bold_fallbacks: bool = False

    def face_for(self, char: str) -> Face:
        return next((face for face in self.faces if face.has_char(char)), self.faces[0])

    def runs(self, text: str) -> list[tuple[Face, str]]:
        runs: list[tuple[Face, list[str]]] = []
        for char, extends in zip(text, extends_cluster(text), strict=True):
            face = runs[-1][0] if extends and runs else self.face_for(char)
            if runs and runs[-1][0] is face:
                runs[-1][1].append(char)
            else:
                runs.append((face, [char]))
        return [(face, "".join(chars)) for face, chars in runs]

    def text_width(self, text: str, px: int) -> float:
        width = 0.0
        for char, extends in zip(text, extends_cluster(text), strict=True):
            if not extends:
                face = self.face_for(char)
                width += face.advance(char) / face.units_per_em
        return width * px

    def synthetic_bold(self, face: Face) -> bool:
        # The official player draws emoji with a color emoji font, which looks the same with synthetic bold.
        return self.bold_fallbacks and face is not self.faces[0] and face.font is not EMOJI

    def metrics_bounds(self, px: int) -> tuple[int, int]:
        top, bottom = self.metrics_string_bounds
        units_per_em = self.faces[0].units_per_em
        return math.ceil(top * px / units_per_em), math.ceil(bottom * px / units_per_em)


def font_data_directory() -> "Traversable":
    return importlib.resources.files(__name__.rpartition(".")[0]) / FONT_DATA_DIRECTORY


def read_bundled_fonts(fonts: Iterable[FontFile], package_directory: "Traversable") -> dict[FontFile, bytes]:
    result = {}
    for font in fonts:
        try:
            data = (package_directory / font.filename).read_bytes()
        except OSError as e:
            raise FontError(
                f"cannot read the bundled font {font.filename}: {e}. In a clone, run tools/font_data.py"
            ) from e
        if hashlib.sha256(data).hexdigest() != font.sha256:
            raise FontError(
                f"unexpected SHA-256 hash of the bundled font {font.filename}. In a clone, run tools/font_data.py"
            )
        result[font] = data
    return result


def bundled_font_path(font: FontFile, package_directory: "Traversable", directory: Path) -> Path:
    resource = package_directory / font.filename
    if isinstance(resource, Path):
        return resource
    # FFmpeg cannot read the fonts from the zip file that yt-dlp loads the plugin from.
    path = directory / font.filename
    path.write_bytes(resource.read_bytes())
    return path


# The options keep the OpenType features and the names, which libass uses to select the fonts.
SUBSET_OPTIONS = ("--layout-features=*", "--name-IDs=*", "--name-languages=*", "--notdef-outline")


def font_subsetter() -> Callable[[bytes, Iterable[str]], bytes] | None:
    if importlib.util.find_spec("fontTools") is not None:
        return subset_font
    # The fonttools packages of Homebrew and other package managers use their own Python, so only the command works.
    if command := shutil.which("pyftsubset"):
        return functools.partial(subset_font_with_command, command)
    return None


def subset_font(data: bytes, chars: Iterable[str]) -> bytes:
    try:
        # yt-dlp imports the plugin on every run, and fontTools takes tens of milliseconds to import.
        from fontTools import subset

        options = subset.Options()
        options.parse_opts(list(SUBSET_OPTIONS))
        font = subset.load_font(io.BytesIO(data), options)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes={ord(char) for char in chars})
        subsetter.subset(font)
        output = io.BytesIO()
        subset.save_font(font, output, options)
    except Exception as e:
        raise FontError(repr(e)) from e
    return output.getvalue()


def subset_font_with_command(command: str, data: bytes, chars: Iterable[str]) -> bytes:
    try:
        with tempfile.TemporaryDirectory(prefix="yt-dlp-nicocomments-", ignore_cleanup_errors=True) as directory:
            source, unicodes, output = (Path(directory, name) for name in ("source", "unicodes.txt", "output"))
            source.write_bytes(data)
            unicodes.write_text("\n".join(f"{ord(char):X}" for char in chars), encoding="ascii")
            _, stderr, returncode = Popen.run(  # pyright: ignore[reportAssignmentType]
                [command, source, f"--unicodes-file={unicodes}", f"--output-file={output}", *SUBSET_OPTIONS],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if returncode != 0:
                raise FontError(f"pyftsubset exited with code {returncode}: {stderr.strip()}")
            return output.read_bytes()
    except OSError as e:
        raise FontError(f"cannot run pyftsubset: {e}") from e


@cache
def load_font_chains() -> dict[FontKey, FontChain]:
    faces = {}
    for font, data in read_bundled_fonts(FONT_FILES, font_data_directory()).items():
        try:
            faces[font] = Face.parse(font, data)
        except (KeyError, ValueError, struct.error) as e:
            raise FontError(f"cannot read {font.filename}: {e!r}") from e
    fallbacks = [faces[font] for font in FALLBACK_FONTS]
    return {
        key: FontChain([faces[font], *fallbacks], METRICS_STRING_BOUNDS[font], key in SYNTHETIC_BOLD_KEYS)
        for key, font in CHAIN_FONTS.items()
    }
