import functools
import math
import optparse
import re
from collections.abc import Collection
from typing import TYPE_CHECKING, Any

from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.postprocessor.ffmpeg import FFmpegEmbedSubtitlePP
from yt_dlp.utils import PostProcessingError

from ._nicocomments.api import WATCH_API_LANGUAGES, CommentAPIError, fetch_comments, is_logged_in
from ._nicocomments.ass import build_ass
from ._nicocomments.attachments import (
    ASS_CONTAINER,
    EMBEDDING_KEY,
    JSON_SUBTITLES_KEY,
    CommentEmbedding,
    NicoCommentFontsPP,
    NicoCommentJSONPP,
)
from ._nicocomments.filters import NG_SCORE_THRESHOLDS
from ._nicocomments.font_files import FontFile, add_font_chars
from ._nicocomments.fonts import FontError, load_font_chains
from ._nicocomments.hls import PlaylistError, media_duration
from ._nicocomments.pipeline import layout_comments

if TYPE_CHECKING:
    from yt_dlp import YoutubeDL

JSON_SUBTITLE_LANG = "comments"
LANGUAGE_NAMES = {"ja": "Japanese", "en": "English", "zh": "Chinese"}
BOOLEAN_VALUES = {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}


def format_option_value(value: object) -> str:
    return value if isinstance(value, str) else repr(value)


def parse_opacity_option(value: str | int | float) -> float:
    try:
        result = math.nan if isinstance(value, (bool, bytes, bytearray)) else float(value)
    except (TypeError, ValueError, OverflowError):
        result = math.nan
    if not 0 <= result <= 1:
        raise optparse.OptionValueError(
            f"NicoComments: opacity must be a number from 0 to 1, not {format_option_value(value)}"
        )
    return result


def choice_option_error(name: str, value: object, choices: Collection[str]) -> optparse.OptionValueError:
    return optparse.OptionValueError(
        f"NicoComments: {name} must be one of {', '.join(choices)}, not {format_option_value(value)}"
    )


def parse_choice_option(name: str, value: object, choices: Collection[str]) -> str:
    if not isinstance(value, str) or value.lower() not in choices:
        raise choice_option_error(name, value, choices)
    return value.lower()


def parse_boolean_option(name: str, value: str | int) -> bool:
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return BOOLEAN_VALUES[parse_choice_option(name, value, BOOLEAN_VALUES)]


def parse_comments_option(value: str | int) -> int | None:
    if isinstance(value, str) and value.strip().lower() == "all":
        return None
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        return int(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    raise optparse.OptionValueError(
        f"NicoComments: comments must be a non-negative integer or all, not {format_option_value(value)}"
    )


def parse_languages_option(value: str | list[str] | tuple[str, ...]) -> list[str]:
    values = value.split(",") if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or not values:
        raise choice_option_error("lang", value, WATCH_API_LANGUAGES.keys())
    languages = [
        parse_choice_option(
            "lang", language.strip() if isinstance(language, str) else language, WATCH_API_LANGUAGES.keys()
        )
        for language in values
    ]
    return list(dict.fromkeys(languages))


class NicoCommentsPP(PostProcessor):
    _downloader: "YoutubeDL"

    def __init__(
        self,
        downloader=None,
        opacity: str | float = "1",
        defaulttrack: str | int = "true",
        nglevel: str = "medium",
        lang: str | list[str] | tuple[str, ...] = "ja",
        embedfonts: str | int = "true",
        comments: str | int = "0",
        writejson: str | int = "false",
        **kwargs: object,
    ):
        if kwargs:
            raise optparse.OptionValueError(f"NicoComments: unknown options: {', '.join(kwargs)}")
        super().__init__(downloader)
        self._opacity = parse_opacity_option(opacity)
        self._default_track = parse_boolean_option("defaulttrack", defaulttrack)
        self._ng_score_threshold = NG_SCORE_THRESHOLDS[parse_choice_option("nglevel", nglevel, NG_SCORE_THRESHOLDS)]
        self._languages = parse_languages_option(lang)
        self._embed_fonts = parse_boolean_option("embedfonts", embedfonts)
        self._min_comments = parse_comments_option(comments)
        self._write_json = parse_boolean_option("writejson", writejson)

    def run(self, info):  # pyright: ignore[reportIncompatibleMethodOverride]
        if info.get("extractor_key") != "Niconico":
            return [], info
        if not self.get_param("writesubtitles"):
            self.report_warning("Comments are not saved. Use --embed-subs or --write-subs")
            return [], info
        subtitles = (info.get("requested_subtitles") or {}).values()
        if "filepath" in info or any("filepath" in subtitle for subtitle in subtitles):
            # yt-dlp writes the subtitle files before the before_dl stage.
            self.report_warning(
                "Comments are skipped because NicoComments ran after the subtitles were written. Use when=video"
            )
            return [], info

        width, height = info.get("width"), info.get("height")
        if not width or not height:
            self.report_warning("Comments are skipped because the selected format has no video")
            return [], info
        self._select_ass_container(info)
        if self.get_param("simulate"):
            return [], info

        min_comments = self._min_comments
        if min_comments != 0 and not is_logged_in(self._downloader):
            self.report_warning(
                "Past comments are not loaded because they need a login. Use --cookies-from-browser or --cookies"
            )
            min_comments = 0
        try:
            font_chains = load_font_chains()
            fetched = {
                language: fetch_comments(
                    self._downloader,
                    info["id"],
                    language,
                    min_comments,
                    functools.partial(self._report_progress, language),
                    self.report_warning,
                )
                for language in self._languages
            }
        except (CommentAPIError, FontError) as e:
            raise PostProcessingError(str(e)) from e

        content_length_ms = self._content_length_ms(info)
        comment_subtitles = {}
        json_subtitles = {}
        font_chars: dict[FontFile, set[str]] = {}
        for language, (comments, raw) in fetched.items():
            slot_layers = layout_comments(
                comments, font_chains, content_length_ms, self._ng_score_threshold, info["id"]
            )
            # yt-dlp derives the language tag from the first two letters of the subtitle key.
            key = f"{language}-comments"
            name = f"{LANGUAGE_NAMES[language]} comments"
            self.to_screen(f"Laid out {sum(len(slot_layer.slots) for slot_layer in slot_layers)} {name}")  # pyright: ignore[reportCallIssue]
            data, used_chars = build_ass(slot_layers, width, height, self._opacity, language)
            add_font_chars(font_chars, used_chars)
            comment_subtitles[key] = {"ext": "ass", "name": name, "data": data}
            if self._write_json:
                json_subtitles[f"{key}-raw"] = {"ext": "json", "data": raw.to_json(info["id"], language)}

        other_subtitles = dict(info.get("requested_subtitles") or {})
        other_subtitles.pop(JSON_SUBTITLE_LANG, None)
        info["requested_subtitles"] = {**comment_subtitles, **other_subtitles, **json_subtitles}
        if json_subtitles and self._insert_json_pp():
            info.setdefault(JSON_SUBTITLES_KEY, []).extend(json_subtitles)
        if self._insert_fonts_pp():
            info.setdefault(EMBEDDING_KEY, []).append(
                CommentEmbedding(
                    frozenset(subtitle["name"] for subtitle in comment_subtitles.values()),
                    {font: frozenset(chars) for font, chars in font_chars.items()} if self._embed_fonts else {},
                    self._default_track,
                )
            )
        return [], info

    def _report_progress(self, language: str, text: str) -> None:
        self.to_screen(f"{LANGUAGE_NAMES[language]}: {text}")  # pyright: ignore[reportCallIssue]

    def _post_processors(self) -> list[Any]:
        # API users can add the postprocessor without listing it in the postprocessors param,
        # and yt-dlp has no public API for the added postprocessors.
        return self._downloader._pps["post_process"]  # pyright: ignore[reportAttributeAccessIssue]

    def _embed_subtitle_index(self) -> int | None:
        pps = self._post_processors()
        return max((i for i, pp in enumerate(pps) if isinstance(pp, FFmpegEmbedSubtitlePP)), default=None)

    def _insert_json_pp(self) -> bool:
        embed_index = self._embed_subtitle_index()
        if embed_index is None:
            return False
        pps = self._post_processors()
        if not any(isinstance(pp, NicoCommentJSONPP) for pp in pps):
            pps.insert(embed_index, NicoCommentJSONPP(self._downloader))
        return True

    def _insert_fonts_pp(self) -> bool:
        embed_index = self._embed_subtitle_index()
        if embed_index is None:
            return False
        pps = self._post_processors()
        if not any(isinstance(pp, NicoCommentFontsPP) for pp in pps):
            # The later postprocessors copy all streams, so FFmpegSplitChapters also copies the fonts
            # to each chapter file. add_post_processor can only append to the end.
            pps.insert(embed_index + 1, NicoCommentFontsPP(self._downloader))
        return True

    def _content_length_ms(self, info) -> int | None:
        # The official player uses the duration of the media, which is not the rounded duration from the API.
        try:
            duration = media_duration(self._downloader, info)
        except PlaylistError as e:
            self.report_warning(f"Cannot read the media duration from the HLS playlist: {e}")
            duration = None
        duration = duration or info.get("duration")
        return math.floor(duration * 1000) if duration else None

    def _select_ass_container(self, info):
        # yt-dlp creates the output file name after the video stage, and the merger
        # selects the container from the extension.
        if (
            self.get_param("skip_download")
            or not info.get("requested_formats")
            or info.get("ext") == ASS_CONTAINER
            or self._embed_subtitle_index() is None
        ):
            return
        if self.get_param("merge_output_format") is not None:
            self.report_warning(f"Comments can lose their layout because {info['ext']} cannot hold ASS subtitles")
            return
        self.to_screen(f"Merging into {ASS_CONTAINER} because {info['ext']} cannot hold ASS subtitles")  # pyright: ignore[reportCallIssue]
        info["ext"] = ASS_CONTAINER
