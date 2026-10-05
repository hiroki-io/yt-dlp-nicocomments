import optparse

import pytest
from conftest import FakeDownloader
from yt_dlp.networking.exceptions import TransportError

from yt_dlp_plugins.postprocessor import nicocomments
from yt_dlp_plugins.postprocessor._nicocomments.comments import CommentLayer, FetchedComments
from yt_dlp_plugins.postprocessor.nicocomments import NicoCommentsPP


class CoveringChain:
    def covers(self, text: str) -> bool:
        return True


def video_info(**fields):
    return {
        "extractor_key": "Niconico",
        "id": "sm9",
        "width": 1280,
        "height": 720,
        "ext": "mp4",
        "duration": 320,
        "requested_formats": [{"url": "https://example.com/v.mp4", "protocol": "https"}],
        **fields,
    }


def downloader(**params):
    return FakeDownloader(params={"writesubtitles": True, **params})


@pytest.fixture
def fake_fonts_and_comments(monkeypatch):
    monkeypatch.setattr(nicocomments, "load_font_chains", lambda: {"defont": CoveringChain()})
    monkeypatch.setattr(
        nicocomments, "fetch_comments", lambda ydl, video_id: FetchedComments([CommentLayer(0, False, [])], False)
    )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"opacity": "big"}, "opacity must be a number from 0 to 1, not big"),
        ({"opacity": "nan"}, "opacity must be a number from 0 to 1, not nan"),
        ({"opacity": "1.5"}, "opacity must be a number from 0 to 1, not 1.5"),
        ({"default": "maybe"}, "default must be one of true, yes, 1, false, no, 0, not maybe"),
        ({"ngscore": "max"}, "ngscore must be one of high, middle, low, none, not max"),
        ({"opacty": "0.8", "fontsize": "2"}, "unknown options: opacty, fontsize"),
    ],
)
def test_invalid_options_raise_option_value_error(options, message):
    with pytest.raises(optparse.OptionValueError, match=f"^NicoComments: {message}$"):
        NicoCommentsPP(FakeDownloader(), **options)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("Yes", True), ("1", True), ("FALSE", False), ("no", False), ("0", False)],
)
def test_default_option_accepts_boolean_words_in_any_case(value, expected):
    assert NicoCommentsPP(FakeDownloader(), default=value)._default is expected


def test_comments_are_added_as_the_first_subtitle_track(fake_fonts_and_comments):
    ydl = downloader()
    info = video_info(requested_subtitles={"comments": {"ext": "json"}, "en": {"ext": "vtt"}})
    _, info = NicoCommentsPP(ydl).run(info)
    assert list(info["requested_subtitles"]) == ["ja-comments", "en"]
    assert info["requested_subtitles"]["ja-comments"]["ext"] == "ass"
    assert info["requested_subtitles"]["ja-comments"]["data"].startswith("[Script Info]")


def test_ext_changes_to_mkv_without_merge_output_format(fake_fonts_and_comments):
    _, info = NicoCommentsPP(downloader()).run(video_info())
    assert info["ext"] == "mkv"


def test_other_extractors_are_skipped():
    info = {"extractor_key": "Youtube"}
    assert NicoCommentsPP(downloader()).run(info) == ([], info)


def test_merge_output_format_keeps_the_extension(fake_fonts_and_comments):
    ydl = downloader(merge_output_format="mp4")
    _, info = NicoCommentsPP(ydl).run(video_info())
    assert info["ext"] == "mp4"
    assert ydl.warnings == ["Comments can lose their layout because mp4 cannot hold ASS subtitles"]


@pytest.mark.parametrize(
    ("pp_args", "expected"),
    [
        ({}, ["-disposition:s:0", "default"]),
        ({"embedsubtitle+ffmpeg": ["-metadata", "a=b"]}, ["-metadata", "a=b", "-disposition:s:0", "default"]),
        ({"default": ["-v", "0"]}, ["-v", "0", "-disposition:s:0", "default"]),
        ({"embedsubtitle+ffmpeg_o1": ["-disposition:s:0", "0"]}, ["-disposition:s:0", "0"]),
    ],
)
def test_default_disposition_is_merged_into_postprocessor_args(fake_fonts_and_comments, pp_args, expected):
    ydl = downloader(postprocessor_args=pp_args)
    NicoCommentsPP(ydl).run(video_info())
    assert pp_args["embedsubtitle+ffmpeg_o1"] == expected


def test_default_false_keeps_postprocessor_args(fake_fonts_and_comments):
    ydl = downloader()
    NicoCommentsPP(ydl, default="false").run(video_info())
    assert "postprocessor_args" not in ydl.params


def test_postprocessor_args_that_are_not_a_dict_are_kept_with_a_warning(fake_fonts_and_comments):
    ydl = downloader(postprocessor_args=["-v", "0"])
    NicoCommentsPP(ydl).run(video_info())
    assert ydl.params["postprocessor_args"] == ["-v", "0"]
    assert ydl.warnings == ["Cannot make the subtitle track default because postprocessor_args is not a dict"]


def test_content_length_is_rounded_down():
    ydl = FakeDownloader([b"#EXTINF:10.0,\na.ts\n#EXTINF:5.0006,\nb.ts\n"])
    info = video_info(requested_formats=None, url="https://example.com/v.m3u8", protocol="m3u8_native")
    assert NicoCommentsPP(ydl)._content_length_ms(info) == 15000


def test_content_length_falls_back_to_the_api_duration():
    ydl = FakeDownloader([TransportError("timed out")] * 3)
    info = video_info(
        requested_formats=[{"url": "https://example.com/v.m3u8", "protocol": "m3u8_native"}], duration=100
    )
    assert NicoCommentsPP(ydl)._content_length_ms(info) == 100000
    assert ydl.warnings == ["Cannot read the media duration from the HLS playlist: timed out"]


def test_content_length_without_hls_formats_uses_the_api_duration():
    pp = NicoCommentsPP(FakeDownloader())
    assert pp._content_length_ms(video_info(duration=320.5)) == 320500
    assert pp._content_length_ms(video_info(duration=None)) is None
