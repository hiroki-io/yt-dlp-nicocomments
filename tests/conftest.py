import io
import json

import pytest
from PIL import ImageFont

from yt_dlp_plugins.postprocessor._nicocomments import fetch, fonts
from yt_dlp_plugins.postprocessor._nicocomments.comments import FONT_KEYS


class FixedWidthChain:
    adjust_baseline = 0.0

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

    def urlopen(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, bytes):
            response = json.dumps(response).encode()
        return io.BytesIO(response)

    def to_screen(self, *args, **kwargs):
        pass

    def to_console_title(self, *args, **kwargs):
        pass

    def evaluate_outtmpl(self, outtmpl, info_dict):
        return outtmpl

    def report_warning(self, text, *args, **kwargs):
        self.warnings.append(text)


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch.time, "sleep", calls.append)
    return calls


@pytest.fixture
def fixed_width_chains():
    return {key: FixedWidthChain() for key in FONT_KEYS}


def pillow_font(face: fonts.Face, size: int) -> ImageFont.FreeTypeFont:
    path, offset = fonts.find_faces({face.postscript_name})[face.postscript_name]
    with open(path, "rb") as f:
        index = fonts._face_offsets(f).index(offset)
    return ImageFont.truetype(str(path), size, index=index)
