from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

FONT_DATA_DIRECTORY = "font_data"
# The Matroska muxer needs a MIME type for each attachment. FFmpeg uses these types for TrueType and CFF fonts.
MIMETYPES = {".ttf": "application/x-truetype-font", ".otf": "application/vnd.ms-opentype"}


@dataclass(frozen=True)
class FontFile:
    ass_name: str
    url: str
    sha256: str

    @property
    def filename(self) -> str:
        return f"{self.ass_name}{Path(self.url).suffix}"

    @property
    def mimetype(self) -> str:
        return MIMETYPES[Path(self.url).suffix]


def add_font_chars(chars: dict[FontFile, set[str]], new_chars: Mapping[FontFile, Iterable[str]]) -> None:
    for font, font_chars in new_chars.items():
        chars.setdefault(font, set()).update(font_chars)


@dataclass(frozen=True)
class LicenseFile:
    filename: str
    url: str
    fonts: tuple[FontFile, ...]


# The official player uses sans-serif at 600 and serif at 400 on Linux, where these fonts are the usual defaults.
SANS_BOLD = FontFile(
    "NotoSansJP-Bold",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/JP/NotoSansJP-Bold.otf",
    "a8361640c06ff301334f981d6c8dc1f22553570b4db20bd66ac89960921e3603",
)
SANS_REGULAR = FontFile(
    "NotoSansJP-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/JP/NotoSansJP-Regular.otf",
    "eb5d08776b52a361415f340d56103952cf80b05ed581d4d23c0ad48e40b810e8",
)
SERIF_REGULAR = FontFile(
    "NotoSerifJP-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Serif2.003/Serif/SubsetOTF/JP/NotoSerifJP-Regular.otf",
    "a40e351c4d112add6a6bbc78ae9d92d7b40c71d1f7b2c0b7da99c0f58bd7232c",
)
# libass cannot draw color fonts, so the chains use a monochrome emoji font.
# libass finds this variable font only by its family name.
EMOJI = FontFile(
    "Noto Emoji",
    "https://raw.githubusercontent.com/google/fonts/b979dba422e445492b0eb9951ac52ee0b4d648c3/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf",
    "0b443f5a215ee197c727e4ca125d2e5b1524b1752b25fcc1b5f9b74bbb1c2ced",
)
# These fonts have the characters that the Japanese subsets do not have, for example the spaces
# from U+2000 to U+2006 that comment art uses.
MATH = FontFile(
    "Noto Sans Math",
    "https://raw.githubusercontent.com/google/fonts/dbd1ab6e65dc59bcda3ca8de9fd372f58f98e0af/ofl/notosansmath/NotoSansMath-Regular.ttf",
    "f958624ee51974aecb65a214788c910af5808efa5840e0b3265b2ab010c07d72",
)
SYMBOLS = FontFile(
    "Noto Sans Symbols 2",
    "https://raw.githubusercontent.com/google/fonts/7b6724ac7ececc713e9ba93af309f7520c9a80a3/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
    "7d907ba95e568a0232dbd38e22c28e181ed6d4751ffb13246371cdefc8f1a7ff",
)
# These fonts come last so that they do not replace the glyphs of the other fallback fonts,
# for example the spaces of Noto Sans Math.
SANS_SC_REGULAR = FontFile(
    "NotoSansSC-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf",
    "fc9132016cf5d804253a040e289e078542ffd677f8663efdf637fbfce66e14a6",
)
SANS_KR_REGULAR = FontFile(
    "NotoSansKR-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/KR/NotoSansKR-Regular.otf",
    "d9c48583236330acb9a6e2ead16971045280349fea2f4b8b8cf30d715b4a6e5a",
)
# Kaomoji often use Thai letters such as "ง" and "ว".
THAI = FontFile(
    "Noto Sans Thai",
    "https://raw.githubusercontent.com/google/fonts/8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5/ofl/notosansthai/NotoSansThai%5Bwdth%2Cwght%5D.ttf",
    "5a1c559bb539583c8a1fd99d1c5b9491e5e14478c9cd2bd0970d5c3096cc9ef8",
)
CHAIN_FONTS = {"defont": SANS_BOLD, "gothic": SANS_REGULAR, "mincho": SERIF_REGULAR}
# Ink bounds of "|ÉqÅM" above and below the baseline, in font units.
METRICS_STRING_BOUNDS = {SANS_BOLD: (1010, 284), SANS_REGULAR: (983, 279), SERIF_REGULAR: (973, 272)}
FALLBACK_FONTS = (EMOJI, MATH, SYMBOLS, SANS_SC_REGULAR, SANS_KR_REGULAR, THAI)
FONT_FILES = (*CHAIN_FONTS.values(), *FALLBACK_FONTS)
LICENSE_FILES = (
    LicenseFile(
        "NotoSansCJK.txt",
        "https://github.com/notofonts/noto-cjk/raw/Sans2.004/LICENSE",
        (SANS_BOLD, SANS_REGULAR, SANS_SC_REGULAR, SANS_KR_REGULAR),
    ),
    LicenseFile(
        "NotoSerifCJK.txt", "https://github.com/notofonts/noto-cjk/raw/Serif2.003/Serif/LICENSE", (SERIF_REGULAR,)
    ),
    LicenseFile(
        "NotoEmoji.txt",
        "https://raw.githubusercontent.com/google/fonts/b979dba422e445492b0eb9951ac52ee0b4d648c3/ofl/notoemoji/OFL.txt",
        (EMOJI,),
    ),
    LicenseFile(
        "NotoSansMath.txt",
        "https://raw.githubusercontent.com/google/fonts/dbd1ab6e65dc59bcda3ca8de9fd372f58f98e0af/ofl/notosansmath/OFL.txt",
        (MATH,),
    ),
    LicenseFile(
        "NotoSansSymbols2.txt",
        "https://raw.githubusercontent.com/google/fonts/7b6724ac7ececc713e9ba93af309f7520c9a80a3/ofl/notosanssymbols2/OFL.txt",
        (SYMBOLS,),
    ),
    LicenseFile(
        "NotoSansThai.txt",
        "https://raw.githubusercontent.com/google/fonts/8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5/ofl/notosansthai/OFL.txt",
        (THAI,),
    ),
)
