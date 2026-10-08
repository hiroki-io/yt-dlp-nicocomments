import argparse
import hashlib
import importlib.util
import struct
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIRECTORY = ROOT / "yt_dlp_plugins" / "postprocessor" / "_nicocomments"
LICENSE_DIRECTORY = ROOT / "LICENSES"


def load_font_files():
    # The build environment does not have yt-dlp, which the package imports.
    spec = importlib.util.spec_from_file_location("font_files", PACKAGE_DIRECTORY / "font_files.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def checksum(data: bytes) -> int:
    data = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


def remove_bmp_cmap(data: bytes) -> bytes:
    # libass before 0.17.2 uses the (3, 1) subtable when it comes before (3, 10), and then cannot find
    # the characters outside the BMP.
    font = bytearray(data)
    records = {}
    for i in range(struct.unpack_from(">H", font, 4)[0]):
        tag, _, offset, length = struct.unpack_from(">4sIII", font, 12 + 16 * i)
        records[tag] = (12 + 16 * i, offset, length)
    record, offset, length = records[b"cmap"]
    count = struct.unpack_from(">H", font, offset + 2)[0]
    encodings = [font[offset + 4 + 8 * i : offset + 12 + 8 * i] for i in range(count)]
    kept = [encoding for encoding in encodings if encoding[:4] != b"\0\3\0\1"]
    if len(kept) == count or not any(encoding[:4] == b"\0\3\0\x0a" for encoding in kept):
        return data
    # The removed record leaves unused bytes because the subtable offsets stay the same.
    padding = b"\0" * 8 * (count - len(kept))
    font[offset + 2 : offset + 4 + 8 * count] = struct.pack(">H", len(kept)) + b"".join(kept) + padding
    struct.pack_into(">I", font, record + 4, checksum(font[offset : offset + length]))
    head = records[b"head"][1]
    struct.pack_into(">I", font, head + 8, 0)
    struct.pack_into(">I", font, head + 8, (0xB1B0AFBA - checksum(font)) & 0xFFFFFFFF)
    return bytes(font)


def fetch_fonts() -> list[Path]:
    font_files = load_font_files()
    directory = PACKAGE_DIRECTORY / font_files.FONT_DATA_DIRECTORY
    directory.mkdir(exist_ok=True)
    paths = []
    for font in font_files.FONT_FILES:
        path = directory / font.filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != font.sha256:
            print(f"Downloading {font.url}", file=sys.stderr)
            data = remove_bmp_cmap(download(font.url))
            if hashlib.sha256(data).hexdigest() != font.sha256:
                raise RuntimeError(f"unexpected SHA-256 hash of {font.url}")
            path.write_bytes(data)
        paths.append(path)
    return paths


def fetch_licenses() -> None:
    for license_file in load_font_files().LICENSE_FILES:
        print(f"Downloading {license_file.url}", file=sys.stderr)
        (LICENSE_DIRECTORY / license_file.filename).write_bytes(download(license_file.url))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download the bundled fonts to the package directory.")
    parser.add_argument("--licenses", action="store_true", help="also update the license files in LICENSES")
    args = parser.parse_args()
    fetch_fonts()
    if args.licenses:
        fetch_licenses()
