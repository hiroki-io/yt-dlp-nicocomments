import json
import optparse
from datetime import datetime, timezone

import pytest
from conftest import FakeDownloader, logged_in
from yt_dlp.networking.exceptions import TransportError
from yt_dlp.postprocessor.ffmpeg import FFmpegEmbedSubtitlePP, FFmpegSplitChaptersPP

from yt_dlp_plugins.postprocessor import nicocomments
from yt_dlp_plugins.postprocessor._nicocomments import font_files, fonts
from yt_dlp_plugins.postprocessor._nicocomments.api import RawComments
from yt_dlp_plugins.postprocessor._nicocomments.attachments import (
    EMBEDDING_KEY,
    JSON_SUBTITLES_KEY,
    NicoCommentFontsPP,
    NicoCommentJSONPP,
)
from yt_dlp_plugins.postprocessor._nicocomments.comments import CommentLayer, VideoComments
from yt_dlp_plugins.postprocessor.nicocomments import NicoCommentsPP

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


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


def downloader(embed_subtitles=True, **params):
    ydl = FakeDownloader(params={"writesubtitles": True, **params})
    if embed_subtitles:
        ydl.add_post_processor(FFmpegEmbedSubtitlePP(ydl))
    return ydl


@pytest.fixture
def fake_fonts_and_comments(monkeypatch):
    languages = []

    def fetch_comments(ydl, video_id, language, min_comments, to_screen, report_warning):
        languages.append(language)
        raw = RawComments({"nvComment": {"threadKey": "key"}}, [{"id": "1", "fork": "main", "comments": []}], NOW)
        return VideoComments([CommentLayer(0, False, [])], False), raw

    monkeypatch.setattr(nicocomments, "load_font_chains", dict)
    monkeypatch.setattr(nicocomments, "fetch_comments", fetch_comments)
    return languages


@pytest.fixture
def used_fonts(monkeypatch):
    fonts_of_videos: list[dict[font_files.FontFile, set[str]]] = []

    def build_ass(*args):
        return "[Script Info]\n", fonts_of_videos.pop(0) if fonts_of_videos else {}

    monkeypatch.setattr(nicocomments, "build_ass", build_ass)
    return fonts_of_videos


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"opacity": "big"}, "opacity must be a number from 0 to 1, not big"),
        ({"opacity": "nan"}, "opacity must be a number from 0 to 1, not nan"),
        ({"opacity": "1.5"}, "opacity must be a number from 0 to 1, not 1.5"),
        ({"defaulttrack": "maybe"}, "defaulttrack must be one of true, yes, 1, false, no, 0, not maybe"),
        ({"embedfonts": "none"}, "embedfonts must be one of true, yes, 1, false, no, 0, not none"),
        ({"nglevel": "max"}, "nglevel must be one of high, medium, low, none, not max"),
        ({"lang": "zh-tw"}, "lang must be one of ja, en, zh, not zh-tw"),
        ({"lang": "ja,"}, "lang must be one of ja, en, zh, not "),
        ({"comments": "-1"}, "comments must be a non-negative integer or all, not -1"),
        ({"comments": "many"}, "comments must be a non-negative integer or all, not many"),
        ({"writejson": "maybe"}, "writejson must be one of true, yes, 1, false, no, 0, not maybe"),
        ({"opacty": "0.8", "fontsize": "2"}, "unknown options: opacty, fontsize"),
    ],
)
def test_invalid_options_raise_option_value_error(options, message):
    with pytest.raises(optparse.OptionValueError, match=f"^NicoComments: {message}$"):
        NicoCommentsPP(FakeDownloader(), **options)


@pytest.mark.parametrize(("option", "attribute"), [("defaulttrack", "_default_track"), ("embedfonts", "_embed_fonts")])
@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("Yes", True), ("1", True), ("FALSE", False), ("no", False), ("0", False)],
)
def test_boolean_options_accept_boolean_words_in_any_case(option, attribute, value, expected):
    assert getattr(NicoCommentsPP(FakeDownloader(), **{option: value}), attribute) is expected


@pytest.mark.parametrize(("option", "attribute"), [("defaulttrack", "_default_track"), ("embedfonts", "_embed_fonts")])
@pytest.mark.parametrize(("value", "expected"), [(True, True), (False, False), (1, True), (0, False)])
def test_boolean_options_accept_booleans_and_integers(option, attribute, value, expected):
    assert getattr(NicoCommentsPP(FakeDownloader(), **{option: value}), attribute) is expected


def test_options_accept_python_values():
    pp = NicoCommentsPP(FakeDownloader(), opacity=0.5, lang=["en", " JA", "en"])
    assert pp._opacity == 0.5
    assert pp._languages == ["en", "ja"]
    assert NicoCommentsPP(FakeDownloader(), opacity=1, lang=("zh",))._languages == ["zh"]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"opacity": None}, "opacity must be a number from 0 to 1, not None"),
        ({"opacity": True}, "opacity must be a number from 0 to 1, not True"),
        ({"opacity": 10**400}, f"opacity must be a number from 0 to 1, not {10**400}"),
        ({"opacity": b"0.5"}, "opacity must be a number from 0 to 1, not b'0.5'"),
        ({"opacity": bytearray(b"0.5")}, r"opacity must be a number from 0 to 1, not bytearray\(b'0.5'\)"),
        ({"defaulttrack": b"1"}, "defaulttrack must be one of true, yes, 1, false, no, 0, not b'1'"),
        ({"defaulttrack": 1.0}, "defaulttrack must be one of true, yes, 1, false, no, 0, not 1.0"),
        ({"nglevel": b"low"}, "nglevel must be one of high, medium, low, none, not b'low'"),
        ({"lang": [b"ja"]}, "lang must be one of ja, en, zh, not b'ja'"),
        ({"defaulttrack": None}, "defaulttrack must be one of true, yes, 1, false, no, 0, not None"),
        ({"defaulttrack": 2}, "defaulttrack must be one of true, yes, 1, false, no, 0, not 2"),
        ({"embedfonts": None}, "embedfonts must be one of true, yes, 1, false, no, 0, not None"),
        ({"nglevel": 1}, "nglevel must be one of high, medium, low, none, not 1"),
        ({"nglevel": None}, "nglevel must be one of high, medium, low, none, not None"),
        ({"lang": ["ja", None]}, "lang must be one of ja, en, zh, not None"),
        ({"lang": ["ja", 5]}, "lang must be one of ja, en, zh, not 5"),
        ({"lang": []}, r"lang must be one of ja, en, zh, not \[\]"),
        ({"lang": 5}, "lang must be one of ja, en, zh, not 5"),
        ({"lang": b"ja"}, "lang must be one of ja, en, zh, not b'ja'"),
        ({"comments": -1}, "comments must be a non-negative integer or all, not -1"),
        ({"comments": True}, "comments must be a non-negative integer or all, not True"),
        ({"comments": 1.5}, "comments must be a non-negative integer or all, not 1.5"),
        ({"comments": None}, "comments must be a non-negative integer or all, not None"),
    ],
)
def test_invalid_python_values_raise_option_value_error(options, message):
    with pytest.raises(optparse.OptionValueError, match=f"^NicoComments: {message}$"):
        NicoCommentsPP(FakeDownloader(), **options)


@pytest.mark.parametrize(("value", "expected"), [("0", 0), (" 12 ", 12), (3, 3), ("ALL", None)])
def test_comments_accepts_comment_counts_and_all(value, expected):
    assert NicoCommentsPP(FakeDownloader(), comments=value)._min_comments == expected


@pytest.fixture
def min_comments_values(fake_fonts_and_comments, monkeypatch):
    values = []
    fetch_comments = nicocomments.fetch_comments

    def record_min_comments(ydl, video_id, language, min_comments, to_screen, report_warning):
        values.append(min_comments)
        return fetch_comments(ydl, video_id, language, min_comments, to_screen, report_warning)

    monkeypatch.setattr(nicocomments, "fetch_comments", record_min_comments)
    return values


def test_past_comments_are_not_loaded_by_default(min_comments_values):
    NicoCommentsPP(logged_in(downloader())).run(video_info())
    assert min_comments_values == [0]


def test_past_comments_are_skipped_without_a_login(min_comments_values):
    ydl = downloader()
    NicoCommentsPP(ydl, lang="ja,en", comments="all").run(video_info())
    assert min_comments_values == [0, 0]
    assert ydl.warnings == [
        "Past comments are not loaded because they need a login. Use --cookies-from-browser or --cookies"
    ]


def test_past_comments_are_loaded_with_a_login(min_comments_values):
    ydl = logged_in(downloader())
    NicoCommentsPP(ydl, comments="all").run(video_info())
    assert min_comments_values == [None]
    assert ydl.warnings == []


def test_raw_json_is_not_saved_by_default(fake_fonts_and_comments):
    _, info = NicoCommentsPP(downloader()).run(video_info())
    assert list(info["requested_subtitles"]) == ["ja-comments"]


def test_writejson_adds_the_raw_comments_as_the_last_subtitles(fake_fonts_and_comments):
    info = video_info(requested_subtitles={"comments": {"ext": "json"}, "en": {"ext": "vtt"}})
    _, info = NicoCommentsPP(downloader(), lang="ja,en", writejson="true").run(info)
    subtitles = info["requested_subtitles"]
    assert list(subtitles) == ["ja-comments", "en-comments", "en", "ja-comments-raw", "en-comments-raw"]
    assert subtitles["ja-comments-raw"]["ext"] == "json"
    saved = json.loads(subtitles["en-comments-raw"]["data"])
    assert (saved["videoId"], saved["language"]) == ("sm9", "en")


def test_json_postprocessor_is_inserted_before_the_embedding(fake_fonts_and_comments, used_fonts):
    ydl = downloader()
    info = video_info()
    NicoCommentsPP(ydl, lang="ja", writejson="true").run(info)
    NicoCommentsPP(ydl, lang="en", writejson="true").run(info)
    assert info[JSON_SUBTITLES_KEY] == ["ja-comments-raw", "en-comments-raw"]
    json_pp, embed_pp, fonts_pp = ydl._pps["post_process"]
    assert isinstance(json_pp, NicoCommentJSONPP)
    assert isinstance(embed_pp, FFmpegEmbedSubtitlePP)
    assert isinstance(fonts_pp, NicoCommentFontsPP)


@pytest.mark.parametrize(("embed_subtitles", "writejson"), [(False, "true"), (True, "false")])
def test_json_postprocessor_is_added_only_for_embedded_raw_json(fake_fonts_and_comments, embed_subtitles, writejson):
    ydl = downloader(embed_subtitles=embed_subtitles)
    info = video_info()
    NicoCommentsPP(ydl, writejson=writejson).run(info)
    assert JSON_SUBTITLES_KEY not in info
    assert not any(isinstance(pp, NicoCommentJSONPP) for pp in ydl._pps["post_process"])


def test_comments_are_added_as_the_first_subtitle_track(fake_fonts_and_comments):
    ydl = downloader()
    info = video_info(requested_subtitles={"comments": {"ext": "json"}, "en": {"ext": "vtt"}})
    _, info = NicoCommentsPP(ydl).run(info)
    assert list(info["requested_subtitles"]) == ["ja-comments", "en"]
    assert info["requested_subtitles"]["ja-comments"]["ext"] == "ass"
    assert info["requested_subtitles"]["ja-comments"]["data"].startswith("[Script Info]")


@pytest.mark.parametrize(
    ("lang", "language", "key"),
    [("ja", "ja", "ja-comments"), ("EN", "en", "en-comments"), ("zh", "zh", "zh-comments")],
)
def test_lang_selects_the_comment_language_and_subtitle_key(fake_fonts_and_comments, lang, language, key):
    _, info = NicoCommentsPP(downloader(), lang=lang).run(video_info())
    assert fake_fonts_and_comments == [language]
    assert list(info["requested_subtitles"]) == [key]


def test_lang_with_multiple_languages_adds_a_track_for_each_language_in_order(fake_fonts_and_comments):
    info = video_info(requested_subtitles={"en": {"ext": "vtt"}})
    _, info = NicoCommentsPP(downloader(), lang="en, ja,en").run(info)
    assert fake_fonts_and_comments == ["en", "ja"]
    assert list(info["requested_subtitles"]) == ["en-comments", "ja-comments", "en"]
    assert info["requested_subtitles"]["en-comments"]["name"] == "English comments"
    assert info["requested_subtitles"]["ja-comments"]["name"] == "Japanese comments"


def test_ext_changes_to_mkv_without_merge_output_format(fake_fonts_and_comments):
    _, info = NicoCommentsPP(downloader()).run(video_info())
    assert info["ext"] == "mkv"


@pytest.mark.parametrize("merge_output_format", [None, "mp4"])
def test_skip_download_keeps_the_extension(fake_fonts_and_comments, merge_output_format):
    ydl = downloader(skip_download=True, merge_output_format=merge_output_format)
    _, info = NicoCommentsPP(ydl).run(video_info())
    assert info["ext"] == "mp4"
    assert ydl.warnings == []
    assert "ja-comments" in info["requested_subtitles"]


@pytest.mark.parametrize("merge_output_format", [None, "mp4"])
def test_extension_is_kept_without_embedding_the_subtitles(fake_fonts_and_comments, merge_output_format):
    ydl = downloader(embed_subtitles=False, merge_output_format=merge_output_format)
    _, info = NicoCommentsPP(ydl).run(video_info())
    assert info["ext"] == "mp4"
    assert ydl.warnings == []
    assert not any("Merging" in message for message in ydl.messages)


def test_other_extractors_are_skipped():
    info = {"extractor_key": "Youtube"}
    assert NicoCommentsPP(downloader()).run(info) == ([], info)


def test_merge_output_format_keeps_the_extension(fake_fonts_and_comments):
    ydl = downloader(merge_output_format="mp4")
    _, info = NicoCommentsPP(ydl).run(video_info())
    assert info["ext"] == "mp4"
    assert ydl.warnings == ["Comments can lose their layout because mp4 cannot hold ASS subtitles"]


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


def test_font_errors_raise_postprocessing_error(fake_fonts_and_comments, monkeypatch):
    def fail():
        raise fonts.FontError("cannot read the bundled font NotoSansJP-Bold.otf: no such file")

    monkeypatch.setattr(nicocomments, "load_font_chains", fail)
    with pytest.raises(nicocomments.PostProcessingError, match="no such file"):
        NicoCommentsPP(downloader()).run(video_info())


def test_used_chars_and_comment_tracks_are_saved_for_the_fonts_postprocessor(fake_fonts_and_comments, used_fonts):
    used_fonts += [{font_files.SANS_BOLD: {"a"}, font_files.MATH: {"x"}}, {font_files.SANS_BOLD: {"b"}}]
    info = video_info()
    NicoCommentsPP(downloader(), lang="ja,en").run(info)
    [embedding] = info[EMBEDDING_KEY]
    assert embedding.track_names == {"Japanese comments", "English comments"}
    assert embedding.fonts == {font_files.SANS_BOLD: {"a", "b"}, font_files.MATH: {"x"}}
    assert embedding.default


def test_fonts_are_not_saved_with_the_embedfonts_option_off(fake_fonts_and_comments, used_fonts):
    used_fonts.append({font_files.SANS_BOLD: {"a"}})
    info = video_info()
    NicoCommentsPP(downloader(), embedfonts="false").run(info)
    [embedding] = info[EMBEDDING_KEY]
    assert embedding.track_names == {"Japanese comments"}
    assert embedding.fonts == {}
    assert embedding.default


def test_fonts_postprocessor_is_added_once_after_the_embedding(fake_fonts_and_comments, used_fonts):
    ydl = downloader()
    split_pp = FFmpegSplitChaptersPP(ydl)
    ydl.add_post_processor(split_pp)
    NicoCommentsPP(ydl).run({"extractor_key": "Youtube"})
    assert len(ydl._pps["post_process"]) == 2
    info = video_info()
    NicoCommentsPP(ydl, lang="ja").run(info)
    NicoCommentsPP(ydl, lang="en", defaulttrack="false").run(info)
    assert [(embedding.track_names, embedding.default) for embedding in info[EMBEDDING_KEY]] == [
        ({"Japanese comments"}, True),
        ({"English comments"}, False),
    ]
    embed_pp, fonts_pp, last_pp = ydl._pps["post_process"]
    assert isinstance(embed_pp, FFmpegEmbedSubtitlePP)
    assert isinstance(fonts_pp, NicoCommentFontsPP)
    assert last_pp is split_pp


def test_fonts_postprocessor_is_not_added_without_embedding_the_subtitles(fake_fonts_and_comments, used_fonts):
    ydl = downloader(embed_subtitles=False)
    info = video_info()
    NicoCommentsPP(ydl).run(info)
    assert "ja-comments" in info["requested_subtitles"]
    assert EMBEDDING_KEY not in info
    assert ydl._pps["post_process"] == []


@pytest.mark.parametrize(
    "fields",
    [
        {"filepath": "video.mp4"},
        {"requested_subtitles": {"comments": {"ext": "json", "filepath": "video.comments.json"}}},
    ],
)
def test_comments_are_skipped_after_the_subtitles_are_written(fake_fonts_and_comments, fields):
    ydl = downloader()
    info = video_info(**fields)
    NicoCommentsPP(ydl).run(info)
    assert ydl.warnings == [
        "Comments are skipped because NicoComments ran after the subtitles were written. Use when=video"
    ]
    assert fake_fonts_and_comments == []
    assert info.get("requested_subtitles") == fields.get("requested_subtitles")
    assert len(ydl._pps["post_process"]) == 1
