import argparse
import hashlib
import importlib.util
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


def fetch_fonts() -> list[Path]:
    font_files = load_font_files()
    directory = PACKAGE_DIRECTORY / font_files.FONT_DATA_DIRECTORY
    directory.mkdir(exist_ok=True)
    paths = []
    for font in font_files.FONT_FILES:
        path = directory / font.filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != font.sha256:
            print(f"Downloading {font.url}", file=sys.stderr)
            data = download(font.url)
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
