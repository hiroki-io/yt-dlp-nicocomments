import io
import json
import struct
from pathlib import Path

import pytest
from PIL import ImageFont

from yt_dlp_plugins.postprocessor._nicocomments import fetch, font_files, fonts
from yt_dlp_plugins.postprocessor._nicocomments.comments import FONT_KEYS, Chat


def make_chat(*, no=1, vpos_ms=0, score=0, body="comment", commands=(), fork="main") -> Chat:
    return Chat.parse(no=no, vpos_ms=vpos_ms, score=score, body=body, commands=list(commands), fork=fork)


def cmap_table(*subtables: tuple[int, int, bytes]) -> bytes:
    header = struct.pack(">HH", 0, len(subtables))
    offset = 4 + 8 * len(subtables)
    records = b""
    for platform, encoding, data in subtables:
        records += struct.pack(">HHI", platform, encoding, offset)
        offset += len(data)
    return header + records + b"".join(data for _, _, data in subtables)


def cmap_format12(groups: list[tuple[int, int, int]]) -> bytes:
    body = b"".join(struct.pack(">III", *group) for group in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body


def cmap_format4(segments: list[tuple[int, int, int, list[int] | None]]) -> bytes:
    count = len(segments)
    glyphs = []
    range_offsets = []
    for i, (_, _, _, segment_glyphs) in enumerate(segments):
        if segment_glyphs is None:
            range_offsets.append(0)
        else:
            range_offsets.append(2 * (count - i + len(glyphs)))
            glyphs += segment_glyphs
    body = (
        struct.pack(f">{count}H", *(end for _, end, _, _ in segments))
        + b"\0\0"
        + struct.pack(f">{count}H", *(start for start, _, _, _ in segments))
        + struct.pack(f">{count}h", *(delta for _, _, delta, _ in segments))
        + struct.pack(f">{count}H", *range_offsets)
        + struct.pack(f">{len(glyphs)}H", *glyphs)
    )
    return struct.pack(">7H", 4, 14 + len(body), 0, 2 * count, 0, 0, 0) + body


class FixedWidthChain:
    def text_width(self, text: str, px: int) -> float:
        return len(text) * px

    def metrics_bounds(self, px: int) -> tuple[int, int]:
        return px, px // 5


class FakeDownloader:
    def __init__(self, responses=(), params=None):
        self.responses = list(responses)
        self.params = params or {}
        self.requests = []
        self.warnings = []
        self.messages = []
        self._pps = {"post_process": []}

    def urlopen(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, bytes):
            response = json.dumps(response).encode()
        return io.BytesIO(response)

    def to_screen(self, text, *args, **kwargs):
        self.messages.append(text)

    def to_console_title(self, *args, **kwargs):
        pass

    def evaluate_outtmpl(self, outtmpl, info_dict):
        return outtmpl

    def report_warning(self, text, *args, **kwargs):
        self.warnings.append(text)

    def add_post_processor(self, pp, when="post_process"):
        self._pps.setdefault(when, []).append(pp)


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch.time, "sleep", calls.append)
    return calls


@pytest.fixture
def fixed_width_chains():
    return {key: FixedWidthChain() for key in FONT_KEYS}


def pillow_font(font_directory, face: fonts.Face, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_directory / face.font.filename), size)


@pytest.fixture(scope="session")
def font_directory():
    return Path(fonts.__file__).with_name(font_files.FONT_DATA_DIRECTORY)


@pytest.fixture(scope="session")
def chains():
    return fonts.load_font_chains()
