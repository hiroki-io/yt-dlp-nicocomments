import io
import struct

import pytest
from conftest import pillow_font

from yt_dlp_plugins.postprocessor._nicocomments import fonts
from yt_dlp_plugins.postprocessor._nicocomments.comments import FONT_KEYS

FIRST_FACES = {
    "darwin": {"defont": "HiraginoSans-W6"},
    "win32": {"defont": "Arial-BoldMT", "gothic": "YuGothic-Regular", "mincho": "YuMincho-Regular"},
    "linux": {"defont": "NotoSansCJKjp-Bold", "gothic": "NotoSansCJKjp-Regular", "mincho": "NotoSerifCJKjp-Regular"},
}
TRUETYPE_FACES = {"Arial-BoldMT", "ArialMT", "DejaVuSans-Bold", "DejaVuSans"}


@pytest.fixture(scope="module")
def chains():
    return fonts.load_font_chains()


@pytest.mark.parametrize("key", FONT_KEYS)
def test_chain_starts_with_the_expected_font(chains, key):
    expected = FIRST_FACES[fonts.platform_key()].get(key)
    if expected is None:
        pytest.skip("the first font of this chain is optional on this platform")
    assert chains[key].faces[0].postscript_name == expected


@pytest.mark.parametrize("key", FONT_KEYS)
def test_chain_covers_japanese(chains, key):
    assert chains[key].covers(fonts.JAPANESE_SAMPLE), f"missing fonts: {chains[key].missing}"


@pytest.mark.parametrize("key", FONT_KEYS)
def test_chain_has_metrics_bounds_and_names(chains, key):
    chain = chains[key]
    top, bottom = chain.metrics_bounds(27)
    assert 20 < top < 40
    assert 0 < bottom < 15
    for face in chain.faces:
        assert face.postscript_name
        assert face.units_per_em > 0
        assert face.win_height > face.win_ascent > 0


def test_cff_bounds_match_the_outlines(chains):
    for chain in chains.values():
        for face in chain.faces:
            if not face.is_cff or face.postscript_name not in fonts.CFF_METRICS_STRING_BOUNDS:
                continue
            _, top, _, bottom = pillow_font(face, face.units_per_em).getbbox(fonts.METRICS_STRING, anchor="ls")
            assert fonts.CFF_METRICS_STRING_BOUNDS[face.postscript_name] == (-top, bottom)


def test_truetype_bounds_match_the_outlines():
    found = fonts.find_faces(TRUETYPE_FACES)
    if not found:
        pytest.skip("no TrueType test font is installed")
    for name, (path, offset) in found.items():
        face = fonts.Face.load(path, offset)
        assert not face.is_cff
        _, top, _, bottom = pillow_font(face, face.units_per_em).getbbox(fonts.METRICS_STRING, anchor="ls")
        assert face.metrics_bounds[0] == pytest.approx(-top, abs=2), name
        assert face.metrics_bounds[1] == pytest.approx(bottom, abs=2), name


def test_text_width_matches_pillow(chains):
    text = "あいうABCgjÉ漢字123"
    for chain in chains.values():
        width = chain.text_width(text, 1000)
        expected = 0.0
        for face, part in chain.runs(text):
            expected += pillow_font(face, face.units_per_em).getlength(part) * 1000 / face.units_per_em
        assert width == pytest.approx(expected, rel=0.01)


@pytest.mark.parametrize("platform", fonts.CHAIN_SPECS)
def test_chain_specs_cover_the_font_commands(platform):
    assert set(fonts.CHAIN_SPECS[platform]) == set(FONT_KEYS)


def cmap_table(*subtables: tuple[int, int, bytes]) -> bytes:
    header = struct.pack(">HH", 0, len(subtables))
    offset = 4 + 8 * len(subtables)
    records = b""
    for platform, encoding, data in subtables:
        records += struct.pack(">HHI", platform, encoding, offset)
        offset += len(data)
    return header + records + b"".join(data for _, _, data in subtables)


def cmap_format4(segments: list[tuple[int, int, int, list[int] | None]]) -> bytes:
    seg_count = len(segments)
    glyph_ids = []
    range_offsets = []
    for i, (_, _, _, glyphs) in enumerate(segments):
        if glyphs is None:
            range_offsets.append(0)
        else:
            range_offsets.append(2 * (seg_count - i) + 2 * len(glyph_ids))
            glyph_ids += glyphs
    body = struct.pack(f">{seg_count}H", *(end for _, end, _, _ in segments)) + b"\0\0"
    body += struct.pack(f">{seg_count}H", *(start for start, _, _, _ in segments))
    body += struct.pack(f">{seg_count}h", *(delta for _, _, delta, _ in segments))
    body += struct.pack(f">{seg_count}H", *range_offsets)
    body += struct.pack(f">{len(glyph_ids)}H", *glyph_ids)
    return struct.pack(">7H", 4, 14 + len(body), 0, 2 * seg_count, 0, 0, 0) + body


def cmap_format12(groups: list[tuple[int, int, int]]) -> bytes:
    body = b"".join(struct.pack(">III", *group) for group in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body


def test_parse_cmap_format4_maps_delta_and_glyph_array_segments_and_skips_glyph_0():
    subtable = cmap_format4(
        [
            (0x41, 0x43, 10 - 0x41, None),
            (0x3042, 0x3044, 5, [20, 0, 22]),
            (0xFFFF, 0xFFFF, 1, None),
        ]
    )
    assert fonts.parse_cmap(cmap_table((3, 1, subtable))) == {
        0x41: 10,
        0x42: 11,
        0x43: 12,
        0x3042: 25,
        0x3044: 27,
    }


def test_parse_cmap_prefers_format12():
    format4 = cmap_format4([(0x41, 0x41, 1, None), (0xFFFF, 0xFFFF, 1, None)])
    format12 = cmap_format12([(0x41, 0x42, 5), (0x1F600, 0x1F601, 100)])
    assert fonts.parse_cmap(cmap_table((3, 1, format4), (3, 10, format12))) == {
        0x41: 5,
        0x42: 6,
        0x1F600: 100,
        0x1F601: 101,
    }


def test_parse_cmap_rejects_tables_without_unicode_subtables():
    with pytest.raises(ValueError, match="no supported Unicode cmap subtable"):
        fonts.parse_cmap(cmap_table((1, 0, struct.pack(">HHH", 0, 262, 0) + bytes(256))))


def test_face_offsets_of_a_collection_are_read_from_the_ttc_header():
    header = b"ttcf" + struct.pack(">II3I", 0x00010000, 3, 24, 300, 600)
    assert fonts._face_offsets(io.BytesIO(header)) == [24, 300, 600]


def test_single_font_has_one_face_at_offset_0():
    assert fonts._face_offsets(io.BytesIO(struct.pack(">IHHHH", 0x00010000, 0, 0, 0, 0))) == [0]


def synthetic_face(name: str, chars: str, advance: int) -> fonts.Face:
    return fonts.Face(
        name,
        name,
        False,
        400,
        1000,
        800,
        1000,
        [500] + [advance] * len(chars),
        {ord(char): i + 1 for i, char in enumerate(chars)},
        (800, 200),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("❤\ufe0f", [False, True]),
        ("a\u200bb", [False, True, False]),
        ("e\u0301", [False, True]),
        ("\U0001f468\u200d\U0001f469\u200d\U0001f467", [False, True, True, True, True]),
        ("\U0001f44d\U0001f3fd", [False, True]),
        ("\U0001f1ef\U0001f1f5\U0001f1fa\U0001f1f8", [False, True, False, True]),
        ("a\u200db", [False, True, False]),
    ],
)
def test_extends_cluster(text, expected):
    assert fonts.extends_cluster(text) == expected


def test_characters_that_extend_a_cluster_add_no_width_and_use_the_previous_face():
    latin = synthetic_face("Latin", "a", 600)
    symbols = synthetic_face("Symbols", "❤", 1000)
    chain = fonts.FontChain([latin, symbols], 400, 0.0)
    text = "a❤\ufe0f\u200ba"
    assert chain.text_width(text, 100) == pytest.approx(60 + 100 + 60)
    assert chain.runs(text) == [(latin, "a"), (symbols, "❤\ufe0f\u200b"), (latin, "a")]


SPEC_FACE_NAMES = {name for spec in fonts.CHAIN_SPECS[fonts.platform_key()].values() for name in spec.face_names}


@pytest.fixture
def install_faces(monkeypatch):
    def install(names: set[str]):
        monkeypatch.setattr(fonts, "find_faces", lambda wanted: {name: (name, 0) for name in wanted & names})
        fonts.load_font_chains.cache_clear()

    monkeypatch.setattr(
        fonts.Face,
        "load",
        lambda path, offset: synthetic_face(path, "😀" if path == fonts.EMOJI_FACE_NAME else "あ", 1000),
    )
    yield install
    fonts.load_font_chains.cache_clear()


def test_emoji_face_is_the_last_face_of_every_chain(install_faces):
    install_faces(SPEC_FACE_NAMES | {fonts.EMOJI_FACE_NAME})
    for chain in fonts.load_font_chains().values():
        assert chain.faces[-1].postscript_name == fonts.EMOJI_FACE_NAME
        assert chain.face_for("あ") is chain.faces[0]
        assert chain.face_for("😀") is chain.faces[-1]
        assert chain.missing == ()
        assert not chain.synthetic_bold(chain.faces[-1])


def test_chains_do_not_contain_the_emoji_face_when_it_is_not_installed(install_faces):
    install_faces(SPEC_FACE_NAMES)
    for chain in fonts.load_font_chains().values():
        assert fonts.EMOJI_FACE_NAME not in [face.postscript_name for face in chain.faces]
        assert chain.missing == ()
