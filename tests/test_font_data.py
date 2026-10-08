import importlib.util
import struct
from pathlib import Path

import pytest
from conftest import cmap_format12, cmap_table

from yt_dlp_plugins.postprocessor._nicocomments import fonts

FORMAT4 = struct.pack(">HHH", 4, 6, 0)
FORMAT12 = cmap_format12([(0x41, 0x41, 1), (0x1F600, 0x1F600, 2)])


@pytest.fixture(scope="module")
def font_data():
    spec = importlib.util.spec_from_file_location(
        "font_data", Path(__file__).resolve().parent.parent / "tools" / "font_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sfnt(font_data, tables: dict[bytes, bytes]) -> bytes:
    offset = 12 + 16 * len(tables)
    directory = b""
    body = b""
    for tag, data in tables.items():
        directory += struct.pack(">4sIII", tag, font_data.checksum(data), offset + len(body), len(data))
        body += data
        if tag != list(tables)[-1]:
            body += b"\0" * (-len(data) % 4)
    return struct.pack(">IHHHH", 0x00010000, len(tables), 0, 0, 0) + directory + body


def cmap_records(data: bytes) -> list[tuple[int, int]]:
    cmap = fonts._read_tables(data)[b"cmap"]
    return [struct.unpack_from(">HH", cmap, 4 + 8 * i) for i in range(struct.unpack_from(">H", cmap, 2)[0])]


def test_remove_bmp_cmap_removes_the_windows_bmp_subtable(font_data):
    cmap = cmap_table((0, 3, FORMAT4), (0, 4, FORMAT12), (3, 1, FORMAT4), (3, 10, FORMAT12))
    data = sfnt(font_data, {b"cmap": cmap, b"head": bytes(54)})
    result = font_data.remove_bmp_cmap(data)
    assert cmap_records(result) == [(0, 3), (0, 4), (3, 10)]
    assert fonts.parse_cmap(fonts._read_tables(result)[b"cmap"]) == {0x41: 1, 0x1F600: 2}
    assert len(result) == len(data)
    tag, checksum, offset, length = struct.unpack_from(">4sIII", result, 12)
    assert tag == b"cmap"
    assert checksum == font_data.checksum(result[offset : offset + length])
    assert font_data.checksum(result) == 0xB1B0AFBA


@pytest.mark.parametrize(
    "subtables",
    [
        [(0, 3, FORMAT4), (3, 1, FORMAT4)],
        [(0, 4, FORMAT12), (3, 10, FORMAT12)],
    ],
)
def test_remove_bmp_cmap_keeps_fonts_without_both_windows_subtables(font_data, subtables):
    data = sfnt(font_data, {b"cmap": cmap_table(*subtables), b"head": bytes(54)})
    assert font_data.remove_bmp_cmap(data) == data


def test_remove_bmp_cmap_removes_every_windows_bmp_subtable(font_data):
    cmap = cmap_table((3, 1, FORMAT4), (3, 1, FORMAT4), (3, 10, FORMAT12))
    data = sfnt(font_data, {b"cmap": cmap, b"head": bytes(54)})
    result = font_data.remove_bmp_cmap(data)
    assert cmap_records(result) == [(3, 10)]
    assert len(result) == len(data)
    assert font_data.checksum(result) == 0xB1B0AFBA
