import json
import os
import subprocess
import tempfile
from pathlib import Path

from yt_dlp_plugins.postprocessor._nicocomments.ass import build_ass
from yt_dlp_plugins.postprocessor._nicocomments.assemble import assemble_comments
from yt_dlp_plugins.postprocessor._nicocomments.filters import NG_SCORE_THRESHOLDS
from yt_dlp_plugins.postprocessor._nicocomments.fonts import font_data_directory, load_font_chains
from yt_dlp_plugins.postprocessor._nicocomments.pipeline import layout_comments

ROOT = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT = 960, 540
FPS = 30
DURATION_MS = 8000
# The layout of each copy of the comments depends on the copy before it, so only the middle copy loops seamlessly.
LOOP_COPIES = 3
# oklch(0.38 0.08 240) and oklch(0.38 0.08 275): the same lightness and chroma with different hues.
BACKGROUND_COLORS = ("0x0d4768", "0x363e6c")
# Without a seed, the gradients filter places the colors at random.
BACKGROUND = (
    f"gradients=s={WIDTH}x{HEIGHT}:r={FPS}:d={DURATION_MS / 1000}"
    f":c0={BACKGROUND_COLORS[0]}:c1={BACKGROUND_COLORS[1]}:speed=0:seed=1"
)


def build_sample_ass(comments_path: Path) -> str:
    data = json.loads(comments_path.read_text(encoding="utf-8"))
    for thread in data["threads"]:
        raw_comments = thread["comments"]
        thread["comments"] = [
            {**raw, "no": raw["no"] + copy * len(raw_comments), "vposMs": raw["vposMs"] + copy * DURATION_MS}
            for copy in range(LOOP_COPIES)
            for raw in raw_comments
        ]
    comments = assemble_comments(data["comment"], data["threads"])
    slot_layers = layout_comments(comments, load_font_chains(), None, NG_SCORE_THRESHOLDS["medium"], data["videoId"])
    ass, _ = build_ass(slot_layers, WIDTH, HEIGHT, 1.0, data["language"])
    return ass


def render_avif(ass: str, output: Path) -> None:
    font_directory = Path(str(font_data_directory()))
    with tempfile.TemporaryDirectory() as directory:
        # FFmpeg runs in this directory so that the filter refers to the ASS file by a name that needs no escaping.
        (Path(directory) / "sample.ass").write_text(ass, encoding="utf-8")
        # The filter options use colons as separators, so the colon of a Windows drive letter needs escaping.
        fonts_option = font_directory.as_posix().replace(":", "\\:")
        command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", BACKGROUND]
        middle_copy = f"setpts=PTS+{DURATION_MS / 1000}/TB"
        command += ["-vf", f"{middle_copy},ass=sample.ass:fontsdir='{fonts_option}',setpts=PTS-STARTPTS"]
        command += ["-c:v", "libsvtav1", "-preset", "0", "-crf", "35", "-pix_fmt", "yuv420p10le"]
        # Browsers play animated AVIF images slowly. A short keyframe interval and fast decoding make playback smoother.
        command += ["-g", "30", "-svtav1-params", "fast-decode=1"]
        # bitexact removes the FFmpeg version from the file.
        command += ["-fflags", "+bitexact", "-flags:v", "+bitexact", str(output)]
        # SVT-AV1 writes its settings to stderr and ignores the log level of FFmpeg.
        subprocess.run(command, cwd=directory, check=True, env={**os.environ, "SVT_LOG": "1"})


if __name__ == "__main__":
    output = ROOT / "docs" / "sample.avif"
    render_avif(build_sample_ass(ROOT / "tools" / "sample.json"), output)
    print(f"Wrote {output} ({output.stat().st_size / 1e3:.0f} kB)")
