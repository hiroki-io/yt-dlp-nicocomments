import functools
import hashlib
import io
import shutil
import struct
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import cmap_format12, cmap_table, pillow_font

from yt_dlp_plugins.postprocessor._nicocomments import font_files, fonts
from yt_dlp_plugins.postprocessor._nicocomments.comments import FONT_KEYS

METRICS_STRING = "|ÉqÅM"


def test_each_font_has_one_license_file():
    fonts_with_licenses = [font for license_file in font_files.LICENSE_FILES for font in license_file.fonts]
    assert sorted(fonts_with_licenses, key=lambda font: font.filename) == sorted(
        font_files.FONT_FILES, key=lambda font: font.filename
    )


def test_license_files_are_in_the_repository():
    directory = Path(__file__).resolve().parent.parent / "LICENSES"
    assert {path.name for path in directory.iterdir()} == {
        license_file.filename for license_file in font_files.LICENSE_FILES
    }


@pytest.mark.parametrize("key", FONT_KEYS)
def test_chain_uses_its_font_and_then_the_fallback_fonts(chains, key):
    assert [chains[key].face_for(char).font for char in "あ\U0001f600\u2004❊们한"] == [
        font_files.CHAIN_FONTS[key],
        font_files.EMOJI,
        font_files.MATH,
        font_files.SYMBOLS,
        font_files.SANS_SC_REGULAR,
        font_files.SANS_KR_REGULAR,
    ]


def test_spaces_for_comment_art_have_their_own_widths(chains):
    assert chains["defont"].text_width("\u2000\u2004\u2006", 600) == pytest.approx(300 + 200 + 100)


def test_metrics_bounds_match_the_outlines(chains, font_directory):
    for chain in chains.values():
        face = chain.faces[0]
        font = pillow_font(font_directory, face, face.units_per_em)
        _, top, _, bottom = font.getbbox(METRICS_STRING, anchor="ls")
        assert chain.metrics_string_bounds == (-top, bottom)


def test_text_width_matches_pillow(chains, font_directory):
    text = "あいうABCgjÉ漢字123"
    for chain in chains.values():
        width = chain.text_width(text, 1000)
        expected = 0.0
        for face, part in chain.runs(text):
            expected += pillow_font(font_directory, face, face.units_per_em).getlength(part) * 1000 / face.units_per_em
        assert width == pytest.approx(expected, rel=0.01)


def test_parse_cmap_maps_format12_groups():
    format12 = cmap_format12([(0x41, 0x42, 5), (0x1F600, 0x1F601, 100)])
    assert fonts.parse_cmap(cmap_table((0, 4, format12), (3, 10, format12))) == {
        0x41: 5,
        0x42: 6,
        0x1F600: 100,
        0x1F601: 101,
    }


def test_parse_cmap_rejects_tables_without_a_windows_format12_subtable():
    format12 = cmap_format12([(0x41, 0x41, 1)])
    with pytest.raises(ValueError, match="no format 12 Unicode cmap subtable"):
        fonts.parse_cmap(cmap_table((0, 4, format12), (1, 0, struct.pack(">HHH", 0, 262, 0) + bytes(256))))


def synthetic_face(name: str, chars: str, advance: int) -> fonts.Face:
    return fonts.Face(
        font_files.FontFile(name, f"https://example.com/{name}.otf", ""),
        1000,
        800,
        1000,
        [500] + [advance] * len(chars),
        {ord(char): i + 1 for i, char in enumerate(chars)},
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
    chain = fonts.FontChain([latin, symbols], (800, 200))
    text = "a❤\ufe0f\u200ba"
    assert chain.text_width(text, 100) == pytest.approx(60 + 100 + 60)
    assert chain.runs(text) == [(latin, "a"), (symbols, "❤\ufe0f\u200b"), (latin, "a")]


FONT_DATA = b"font data"
TEST_FONT = font_files.FontFile(
    "Test-Regular", "https://example.com/Test-Regular.otf", hashlib.sha256(FONT_DATA).hexdigest()
)


OTHER_DATA = b"other font data"
OTHER_FONT = font_files.FontFile(
    "Other-Regular", "https://example.com/Other-Regular.ttf", hashlib.sha256(OTHER_DATA).hexdigest()
)


@pytest.fixture
def package_directory(tmp_path):
    directory = tmp_path / "package"
    directory.mkdir()
    (directory / "Test-Regular.otf").write_bytes(FONT_DATA)
    (directory / "Other-Regular.ttf").write_bytes(OTHER_DATA)
    return directory


@pytest.fixture
def zipped_package_directory(tmp_path_factory):
    path = tmp_path_factory.mktemp("zip") / "plugin.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("font_data/Test-Regular.otf", FONT_DATA)
        archive.writestr("font_data/Other-Regular.ttf", OTHER_DATA)
    with zipfile.ZipFile(path) as archive:
        yield zipfile.Path(archive, "font_data/")


def test_bundled_fonts_are_read_from_the_file_system(package_directory):
    assert fonts.read_bundled_fonts([TEST_FONT, OTHER_FONT], package_directory) == {
        TEST_FONT: FONT_DATA,
        OTHER_FONT: OTHER_DATA,
    }


def test_bundled_fonts_are_read_from_a_zip_file(zipped_package_directory):
    assert fonts.read_bundled_fonts([TEST_FONT], zipped_package_directory) == {TEST_FONT: FONT_DATA}


def test_missing_bundled_font_is_an_error(tmp_path):
    with pytest.raises(fonts.FontError, match="cannot read the bundled font Test-Regular"):
        fonts.read_bundled_fonts([TEST_FONT], tmp_path)


def test_bundled_font_with_another_hash_is_an_error(package_directory):
    (package_directory / "Test-Regular.otf").write_bytes(b"old")
    with pytest.raises(fonts.FontError, match="unexpected SHA-256 hash of the bundled font Test-Regular"):
        fonts.read_bundled_fonts([TEST_FONT], package_directory)


def test_bundled_font_on_the_file_system_is_used_in_place(tmp_path, package_directory):
    path = fonts.bundled_font_path(TEST_FONT, package_directory, tmp_path)
    assert path == package_directory / "Test-Regular.otf"
    assert list(tmp_path.glob("*.otf")) == []


def test_zipped_font_is_extracted_to_the_directory(tmp_path, zipped_package_directory):
    path = fonts.bundled_font_path(TEST_FONT, zipped_package_directory, tmp_path)
    assert path == tmp_path / "Test-Regular.otf"
    assert path.read_bytes() == FONT_DATA


@pytest.fixture
def pyftsubset():
    command = shutil.which("pyftsubset")
    if command is None:
        pytest.skip("pyftsubset is not installed")
    return command


@pytest.fixture
def ttfont():
    return pytest.importorskip("fontTools.ttLib").TTFont


def test_font_subsetter_prefers_the_fonttools_module(monkeypatch):
    monkeypatch.setattr(fonts.importlib.util, "find_spec", lambda name: object())
    assert fonts.font_subsetter() is fonts.subset_font


def test_font_subsetter_uses_pyftsubset_without_the_fonttools_module(monkeypatch):
    monkeypatch.setattr(fonts.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(fonts.shutil, "which", lambda name: f"/bin/{name}")
    subsetter = fonts.font_subsetter()
    assert isinstance(subsetter, functools.partial)
    assert (subsetter.func, subsetter.args) == (fonts.subset_font_with_command, ("/bin/pyftsubset",))


def test_font_subsetter_is_none_without_fonttools(monkeypatch):
    monkeypatch.setattr(fonts.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(fonts.shutil, "which", lambda name: None)
    assert fonts.font_subsetter() is None


def font_names(font):
    return {
        (record.nameID, record.langID, record.toUnicode()) for record in font["name"].names if record.platformID == 3
    }


@pytest.mark.parametrize("font", [font_files.SANS_BOLD, font_files.EMOJI])
def test_pyftsubset_and_the_fonttools_module_keep_the_used_chars_and_the_names(
    font_directory, pyftsubset, ttfont, font
):
    data = (font_directory / font.filename).read_bytes()
    chars = "コメントx\U0001f600"
    original = ttfont(io.BytesIO(data))
    for subset in (fonts.subset_font(data, chars), fonts.subset_font_with_command(pyftsubset, data, chars)):
        subset_font = ttfont(io.BytesIO(subset))
        assert subset_font.getBestCmap().keys() == {ord(char) for char in chars} & original.getBestCmap().keys()
        assert font_names(subset_font) == font_names(original)


def test_pyftsubset_failure_is_a_font_error(pyftsubset):
    with pytest.raises(fonts.FontError, match="pyftsubset exited with code 1: "):
        fonts.subset_font_with_command(pyftsubset, b"broken", "a")


def test_missing_pyftsubset_is_a_font_error(tmp_path):
    with pytest.raises(fonts.FontError, match="cannot run pyftsubset: "):
        fonts.subset_font_with_command(str(tmp_path / "pyftsubset"), b"font", "a")


def test_fonttools_import_failure_is_a_font_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "fontTools", None)
    with pytest.raises(fonts.FontError, match="ModuleNotFoundError"):
        fonts.subset_font(b"font", "a")
