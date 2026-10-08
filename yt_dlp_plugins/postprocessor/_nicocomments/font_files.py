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


@dataclass(frozen=True)
class LicenseFile:
    filename: str
    url: str
    fonts: tuple[FontFile, ...]


# The official player uses sans-serif at 600 and serif at 400 on Linux, where these fonts are the usual defaults.
SANS_BOLD = FontFile(
    "NotoSansJP-Bold",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/JP/NotoSansJP-Bold.otf",
    "1b0edfb500b73a4fa8a4fcaae1bbbd403994e08e73e3e0da37e70d3853f42c5f",
)
SANS_REGULAR = FontFile(
    "NotoSansJP-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/JP/NotoSansJP-Regular.otf",
    "dff723ba59d57d136764a04b9b2d03205544f7cd785a711442d6d2d085ac5073",
)
SERIF_REGULAR = FontFile(
    "NotoSerifJP-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Serif2.003/Serif/SubsetOTF/JP/NotoSerifJP-Regular.otf",
    "2c9a12dbd4f2408c4610c7ee84a108b62d7236c3775baed618c64d9cb44b2f04",
)
# libass cannot draw color fonts, so the chains use a monochrome emoji font.
# libass finds this variable font only by its family name.
EMOJI = FontFile(
    "Noto Emoji",
    "https://raw.githubusercontent.com/google/fonts/b979dba422e445492b0eb9951ac52ee0b4d648c3/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf",
    "de6c18832938afc99caf132b39d6a30a19bac7f2e812e28db2535b4608d27551",
)
# These fonts have the characters that the Japanese subsets do not have, for example the spaces
# from U+2000 to U+2006 that comment art uses.
MATH = FontFile(
    "Noto Sans Math",
    "https://raw.githubusercontent.com/google/fonts/dbd1ab6e65dc59bcda3ca8de9fd372f58f98e0af/ofl/notosansmath/NotoSansMath-Regular.ttf",
    "3f495fe933c06786e4d5f6d86b8ee70b6753a68ee3b9d87528726de0f6e2c47d",
)
SYMBOLS = FontFile(
    "Noto Sans Symbols 2",
    "https://raw.githubusercontent.com/google/fonts/7b6724ac7ececc713e9ba93af309f7520c9a80a3/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
    "7d5fb73b7ca67a6798101741f5d280a3d016a56a197afcd4199dbb57b4b82a21",
)
# These fonts come last so that they do not replace the glyphs of the other fallback fonts,
# for example the spaces of Noto Sans Math.
SANS_SC_REGULAR = FontFile(
    "NotoSansSC-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf",
    "faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9",
)
SANS_KR_REGULAR = FontFile(
    "NotoSansKR-Regular",
    "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/KR/NotoSansKR-Regular.otf",
    "69975a0ac8472717870aefeab0a4d52739308d90856b9955313b2ad5e0148d68",
)
CHAIN_FONTS = {"defont": SANS_BOLD, "gothic": SANS_REGULAR, "mincho": SERIF_REGULAR}
# Ink bounds of "|ÉqÅM" above and below the baseline, in font units.
METRICS_STRING_BOUNDS = {SANS_BOLD: (1010, 284), SANS_REGULAR: (983, 279), SERIF_REGULAR: (973, 272)}
FALLBACK_FONTS = (EMOJI, MATH, SYMBOLS, SANS_SC_REGULAR, SANS_KR_REGULAR)
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
)
