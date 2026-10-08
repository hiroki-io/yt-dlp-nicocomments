import json
import shutil
import subprocess
import zipfile

import pytest
import yt_dlp
from yt_dlp.postprocessor.ffmpeg import FFmpegEmbedSubtitlePP, FFmpegPostProcessorError

from yt_dlp_plugins.postprocessor._nicocomments import attachments, font_files
from yt_dlp_plugins.postprocessor._nicocomments.attachments import (
    EMBEDDING_KEY,
    CommentEmbedding,
    NicoCommentFontsPP,
)

ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,NotoSansJP-Bold,20

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,comment
"""
SRT = "1\n00:00:00,000 --> 00:00:01,000\nsubtitle\n"
FONTS = (font_files.SANS_BOLD, font_files.MATH)
NOT_ATTACHED_WARNING = "The fonts are not attached because the comments are not ASS subtitles in an MKV file"

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg is not installed"
)


@pytest.fixture
def ydl():
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        yield ydl


@pytest.fixture
def fonts(tmp_path, monkeypatch):
    directory = tmp_path / "fonts"
    directory.mkdir()
    for font in FONTS:
        (directory / font.filename).write_bytes(b"font")
    monkeypatch.setattr(attachments, "font_data_directory", lambda: directory)
    return frozenset(FONTS)


def downloaded_video(ydl, tmp_path, ext, comment_ext="ass"):
    video = tmp_path / f"video.{ext}"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=64x36:d=0.2", "-c:v", "mpeg4", video],
        check=True,
    )
    info = {"filepath": str(video), "ext": ext, "requested_subtitles": {}}
    for key, name, sub_ext in [("ja-comments", "Japanese comments", comment_ext), ("en", "English", "srt")]:
        path = tmp_path / f"video.{key}.{sub_ext}"
        path.write_text(ASS if sub_ext == "ass" else SRT)
        info["requested_subtitles"][key] = {"ext": sub_ext, "name": name, "filepath": str(path)}
    embed_subtitles(ydl, info)
    return info


def embed_subtitles(ydl, info):
    FFmpegEmbedSubtitlePP(ydl, already_have_subtitle=True).run(info)


def run_fonts_pp(ydl, info, fonts, default=True):
    info[EMBEDDING_KEY] = [CommentEmbedding(frozenset({"Japanese comments"}), fonts, default)]
    pp = NicoCommentFontsPP(ydl)
    warnings = []
    pp.report_warning = warnings.append
    pp.run(info)
    return warnings


def streams(info, codec_type):
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", info["filepath"]],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [stream for stream in json.loads(output)["streams"] if stream["codec_type"] == codec_type]


def attachments_of(info):
    return [(stream["tags"]["filename"], stream["tags"]["mimetype"]) for stream in streams(info, "attachment")]


def default_dispositions(info):
    return [stream["disposition"]["default"] for stream in streams(info, "subtitle")]


@requires_ffmpeg
def test_fonts_are_attached_to_mkv_and_the_comment_track_becomes_default(ydl, tmp_path, fonts):
    info = downloaded_video(ydl, tmp_path, "mkv")
    assert run_fonts_pp(ydl, info, fonts) == []
    assert attachments_of(info) == [
        ("Noto Sans Math.ttf", "application/x-truetype-font"),
        ("NotoSansJP-Bold.otf", "application/vnd.ms-opentype"),
    ]
    assert default_dispositions(info) == [1, 0]
    assert EMBEDDING_KEY not in info


@requires_ffmpeg
def test_zipped_fonts_are_extracted_for_ffmpeg(ydl, tmp_path, monkeypatch):
    archive_path = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for font in FONTS:
            archive.writestr(f"font_data/{font.filename}", b"font")
    info = downloaded_video(ydl, tmp_path, "mkv")
    with zipfile.ZipFile(archive_path) as archive:
        monkeypatch.setattr(attachments, "font_data_directory", lambda: zipfile.Path(archive, "font_data/"))
        assert run_fonts_pp(ydl, info, frozenset(FONTS)) == []
    assert [filename for filename, _ in attachments_of(info)] == ["Noto Sans Math.ttf", "NotoSansJP-Bold.otf"]


@requires_ffmpeg
def test_other_subtitle_tracks_are_no_longer_default(ydl, tmp_path, fonts):
    info = downloaded_video(ydl, tmp_path, "mkv")
    run_fonts_pp(ydl, info, frozenset(), default=False)
    info[EMBEDDING_KEY] = [CommentEmbedding(frozenset({"English"}), frozenset(), True)]
    NicoCommentFontsPP(ydl).run(info)
    assert default_dispositions(info) == [0, 1]
    run_fonts_pp(ydl, info, fonts)
    assert default_dispositions(info) == [1, 0]


@requires_ffmpeg
def test_embeddings_of_several_postprocessors_are_combined(ydl, tmp_path, fonts):
    info = downloaded_video(ydl, tmp_path, "mkv")
    info[EMBEDDING_KEY] = [
        CommentEmbedding(frozenset({"English"}), frozenset({font_files.MATH}), False),
        CommentEmbedding(frozenset({"Japanese comments"}), frozenset({font_files.SANS_BOLD}), True),
    ]
    NicoCommentFontsPP(ydl).run(info)
    assert len(attachments_of(info)) == len(FONTS)
    assert default_dispositions(info) == [1, 0]


@requires_ffmpeg
def test_fonts_are_not_attached_twice_when_the_subtitles_are_embedded_again(ydl, tmp_path, fonts):
    info = downloaded_video(ydl, tmp_path, "mkv")
    run_fonts_pp(ydl, info, fonts)
    embed_subtitles(ydl, info)
    run_fonts_pp(ydl, info, fonts)
    assert len(attachments_of(info)) == len(FONTS)


@requires_ffmpeg
@pytest.mark.parametrize(("ext", "comment_ext"), [("mp4", "ass"), ("mkv", "srt")])
def test_fonts_are_attached_only_to_ass_subtitles_in_mkv(ydl, tmp_path, fonts, ext, comment_ext):
    info = downloaded_video(ydl, tmp_path, ext, comment_ext)
    assert run_fonts_pp(ydl, info, fonts) == [NOT_ATTACHED_WARNING]
    assert attachments_of(info) == []
    assert default_dispositions(info) == [1, 0]


def test_nothing_is_probed_without_fonts_to_attach_and_default_false(ydl, tmp_path, monkeypatch):
    path = tmp_path / "video.mkv"
    path.write_bytes(b"")
    monkeypatch.setattr(NicoCommentFontsPP, "get_metadata_object", pytest.fail)
    run_fonts_pp(ydl, {"filepath": str(path), "ext": "mkv"}, frozenset(), default=False)


def test_without_ffprobe_the_file_is_kept_with_a_warning(ydl, tmp_path, fonts, monkeypatch):
    path = tmp_path / "video.mkv"
    path.write_bytes(b"")
    monkeypatch.setattr(NicoCommentFontsPP, "probe_available", False)
    monkeypatch.setattr(NicoCommentFontsPP, "get_metadata_object", pytest.fail)
    assert run_fonts_pp(ydl, {"filepath": str(path), "ext": "mkv"}, fonts) == [
        "The fonts are not attached and the comment track is not made default because ffprobe is not found"
    ]


def test_ffprobe_failure_is_a_warning_and_the_file_is_kept(ydl, tmp_path, fonts, monkeypatch):
    path = tmp_path / "video.mkv"
    path.write_bytes(b"broken")
    monkeypatch.setattr(NicoCommentFontsPP, "probe_available", True)
    monkeypatch.setattr(NicoCommentFontsPP, "probe_basename", "ffprobe")
    monkeypatch.setattr(NicoCommentFontsPP, "get_metadata_object", lambda self, path: json.loads(""))
    monkeypatch.setattr(NicoCommentFontsPP, "run_ffmpeg", pytest.fail)
    [warning] = run_fonts_pp(ydl, {"filepath": str(path), "ext": "mkv"}, fonts)
    assert warning.startswith(f'Cannot read the streams of "{path}": ')
    assert path.read_bytes() == b"broken"


@requires_ffmpeg
def test_ffmpeg_failure_is_a_warning_and_the_temporary_file_is_removed(ydl, tmp_path, fonts, monkeypatch):
    info = downloaded_video(ydl, tmp_path, "mkv")

    def fail(self, path, out_path, opts):
        open(out_path, "wb").close()
        raise FFmpegPostProcessorError("ffmpeg failed")

    monkeypatch.setattr(NicoCommentFontsPP, "run_ffmpeg", fail)
    assert run_fonts_pp(ydl, info, fonts) == [f'Cannot update "{info["filepath"]}": ffmpeg failed']
    assert sorted(path.name for path in tmp_path.glob("video.*")) == [
        "video.en.srt",
        "video.ja-comments.ass",
        "video.mkv",
    ]


def test_videos_without_comments_are_skipped(ydl, tmp_path, monkeypatch):
    monkeypatch.setattr(NicoCommentFontsPP, "get_metadata_object", pytest.fail)
    info = {"filepath": str(tmp_path / "video.mkv"), "ext": "mkv"}
    assert NicoCommentFontsPP(ydl).run(info) == ([], info)
