import math
import optparse
from collections.abc import Collection, Mapping

from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.postprocessor.ffmpeg import FFmpegEmbedSubtitlePP
from yt_dlp.utils import PostProcessingError

from ._nicocomments.api import WATCH_API_LANGUAGES, CommentAPIError, fetch_comments
from ._nicocomments.ass import build_ass
from ._nicocomments.attachments import ASS_CONTAINER, EMBEDDING_KEY, CommentEmbedding, NicoCommentFontsPP
from ._nicocomments.filters import NG_SCORE_THRESHOLDS
from ._nicocomments.fonts import FontError, load_font_chains
from ._nicocomments.hls import PlaylistError, media_duration
from ._nicocomments.pipeline import layout_comments

JSON_SUBTITLE_LANG = "comments"
LANGUAGE_NAMES = {"ja": "Japanese", "en": "English", "zh": "Chinese"}
BOOLEAN_VALUES = {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}


def parse_opacity_option(value: str) -> float:
    try:
        result = float(value)
    except ValueError:
        result = math.nan
    if not 0 <= result <= 1:
        raise optparse.OptionValueError(f"NicoComments: opacity must be a number from 0 to 1, not {value}")
    return result


def parse_choice_option(name: str, value: str, choices: Collection[str]):
    key = value.lower()
    if key not in choices:
        raise optparse.OptionValueError(f"NicoComments: {name} must be one of {', '.join(choices)}, not {value}")
    return choices[key] if isinstance(choices, Mapping) else key


def parse_languages_option(value: str) -> list[str]:
    languages = [
        parse_choice_option("lang", language.strip(), WATCH_API_LANGUAGES.keys()) for language in value.split(",")
    ]
    return list(dict.fromkeys(languages))


class NicoCommentsPP(PostProcessor):
    def __init__(self, downloader=None, opacity="1", default="true", nglevel="medium", lang="ja", **kwargs):
        if kwargs:
            raise optparse.OptionValueError(f"NicoComments: unknown options: {', '.join(kwargs)}")
        super().__init__(downloader)
        self._opacity = parse_opacity_option(opacity)
        self._default = parse_choice_option("default", default, BOOLEAN_VALUES)
        self._ng_score_threshold = parse_choice_option("nglevel", nglevel, NG_SCORE_THRESHOLDS)
        self._languages = parse_languages_option(lang)

    def run(self, info):
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

        try:
            font_chains = load_font_chains()
            fetched = {language: fetch_comments(self._downloader, info["id"], language) for language in self._languages}
        except (CommentAPIError, FontError) as e:
            raise PostProcessingError(str(e)) from e

        content_length_ms = self._content_length_ms(info)
        comment_subtitles = {}
        fonts = set()
        for language, comments in fetched.items():
            slot_layers = layout_comments(
                comments, font_chains, content_length_ms, self._ng_score_threshold, info["id"]
            )
            # yt-dlp derives the language tag from the first two letters of the subtitle key.
            key = f"{language}-comments"
            name = f"{LANGUAGE_NAMES[language]} comments"
            self.to_screen(f"Laid out {sum(len(slot_layer.slots) for slot_layer in slot_layers)} {name}")
            data, used_fonts = build_ass(slot_layers, width, height, self._opacity, language)
            fonts |= used_fonts
            comment_subtitles[key] = {"ext": "ass", "name": name, "data": data}

        other_subtitles = dict(info.get("requested_subtitles") or {})
        other_subtitles.pop(JSON_SUBTITLE_LANG, None)
        info["requested_subtitles"] = {**comment_subtitles, **other_subtitles}
        if self._insert_fonts_pp():
            info.setdefault(EMBEDDING_KEY, []).append(
                CommentEmbedding(
                    frozenset(subtitle["name"] for subtitle in comment_subtitles.values()),
                    frozenset(fonts),
                    self._default,
                )
            )
        return [], info

    def _embed_subtitle_index(self) -> int | None:
        # API users can add the postprocessor without listing it in the postprocessors param,
        # and yt-dlp has no public API for the added postprocessors.
        pps = self._downloader._pps["post_process"]
        return max((i for i, pp in enumerate(pps) if isinstance(pp, FFmpegEmbedSubtitlePP)), default=None)

    def _insert_fonts_pp(self) -> bool:
        embed_index = self._embed_subtitle_index()
        if embed_index is None:
            return False
        pps = self._downloader._pps["post_process"]
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
        self.to_screen(f"Merging into {ASS_CONTAINER} because {info['ext']} cannot hold ASS subtitles")
        info["ext"] = ASS_CONTAINER
