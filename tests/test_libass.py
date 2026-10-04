import os
import re
import shutil
import subprocess

import pytest
from conftest import pillow_font
from PIL import Image, ImageDraw

from yt_dlp_plugins.postprocessor._nicocomments import fonts
from yt_dlp_plugins.postprocessor._nicocomments.ass import (
    ass_font_name,
    ass_header,
    ass_runs,
    line_top,
)
from yt_dlp_plugins.postprocessor._nicocomments.comments import FONT_KEYS

WIDTH, HEIGHT = 1920, 1080
EM, X, BASELINE = 72, 100, 300
TEXT = "あいうABCgjÉ漢字123"
FONT_SELECTION = re.compile(r"fontselect: \((.*), \d+, \d+\) -> .*, (\S+)$")


def has_libass() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return re.search(r"^\s*\S+\s+ass\s", filters, re.MULTILINE) is not None


# CI sets REQUIRE_LIBASS so that a missing FFmpeg fails the tests instead of skipping them.
pytestmark = pytest.mark.skipif(
    os.environ.get("REQUIRE_LIBASS") != "1" and not has_libass(), reason="ffmpeg with libass is not installed"
)


def render(chain: fonts.FontChain, tmp_path) -> tuple[Image.Image, dict[str, str]]:
    runs = chain.runs(TEXT)
    (tmp_path / "test.ass").write_text(
        ass_header(WIDTH, HEIGHT) + "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,"
        f"{{\\an7\\pos({X},{line_top(runs, EM, BASELINE):.2f})\\bord0}}{ass_runs(chain, runs, EM, 1.0)}\n",
        encoding="utf-8",
    )
    command = ["ffmpeg", "-v", "verbose", "-y", "-f", "lavfi", "-i", f"color=black:s={WIDTH}x{HEIGHT}:d=0.1"]
    command += ["-vf", "ass=test.ass", "-frames:v", "1", "test.png"]
    log = subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stderr
    selected = {}
    for line in log.splitlines():
        if match := FONT_SELECTION.search(line):
            selected.setdefault(match[1], match[2])
    return Image.open(tmp_path / "test.png"), selected


def render_with_pillow(chain: fonts.FontChain) -> Image.Image:
    image = Image.new("L", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    pen = X
    for face, part in chain.runs(TEXT):
        draw.text((pen, BASELINE), part, font=pillow_font(face, EM), fill=255, anchor="ls")
        pen += sum(face.advance(char) for char in part) * EM / face.units_per_em
    return image


def ink_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    return image.convert("L").point(lambda value: 255 if value > 128 else 0).getbbox()


@pytest.mark.parametrize("key", FONT_KEYS)
def test_libass_selects_the_fonts_in_the_ass_subtitle(key, tmp_path):
    chain = fonts.load_font_chains()[key]
    _, selected = render(chain, tmp_path)
    for face, _ in chain.runs(TEXT):
        assert selected.get(ass_font_name(face)) == face.postscript_name, f"{ass_font_name(face)}: {selected}"


@pytest.mark.parametrize("key", FONT_KEYS)
def test_libass_text_position_matches_pillow(key, tmp_path):
    chain = fonts.load_font_chains()[key]
    drawn, _ = render(chain, tmp_path)
    expected = ink_bounds(render_with_pillow(chain))
    for actual, wanted in zip(ink_bounds(drawn), expected, strict=True):
        assert actual == pytest.approx(wanted, abs=3), (ink_bounds(drawn), expected)
