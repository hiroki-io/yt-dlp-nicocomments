import math
import optparse

from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import PostProcessingError, cli_configuration_args

from ._nicocomments.api import CommentAPIError, fetch_comments
from ._nicocomments.ass import build_ass
from ._nicocomments.filters import NG_SCORE_THRESHOLDS
from ._nicocomments.fonts import JAPANESE_SAMPLE, FontChain, FontError, load_font_chains
from ._nicocomments.hls import PlaylistError, media_duration
from ._nicocomments.pipeline import layout_comments

# yt-dlp derives the language tag from the first two letters of the subtitle key.
SUBTITLE_LANG = "ja-comments"
JSON_SUBTITLE_LANG = "comments"
# The order in which FFmpegEmbedSubtitlePP looks up --ppa arguments for its output file.
EMBED_OUTPUT_ARG_KEYS = [
    "embedsubtitle+ffmpeg_o1",
    "embedsubtitle+ffmpeg_o",
    "embedsubtitle+ffmpeg",
    ("embedsubtitle", "ffmpeg"),
    "default",
]
DEFAULT_DISPOSITION_ARGS = ["-disposition:s:0", "default"]
ASS_CONTAINER = "mkv"
BOOLEAN_VALUES = {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}


def parse_opacity_option(value: str) -> float:
    try:
        result = float(value)
    except ValueError:
        result = math.nan
    if not 0 <= result <= 1:
        raise optparse.OptionValueError(f"NicoComments: opacity must be a number from 0 to 1, not {value}")
    return result


def parse_choice_option(name: str, value: str, choices: dict):
    try:
        return choices[value.lower()]
    except KeyError:
        raise optparse.OptionValueError(
            f"NicoComments: {name} must be one of {', '.join(choices)}, not {value}"
        ) from None


class NicoCommentsPP(PostProcessor):
    def __init__(self, downloader=None, opacity="1", default="true", nglevel="medium", **kwargs):
        if kwargs:
            raise optparse.OptionValueError(f"NicoComments: unknown options: {', '.join(kwargs)}")
        super().__init__(downloader)
        self._opacity = parse_opacity_option(opacity)
        self._default = parse_choice_option("default", default, BOOLEAN_VALUES)
        self._ng_score_threshold = parse_choice_option("nglevel", nglevel, NG_SCORE_THRESHOLDS)
        self._checked_fonts = False

    def run(self, info):
        if info.get("extractor_key") != "Niconico":
            return [], info
        if not self.get_param("writesubtitles"):
            self.report_warning("Comments are not saved. Use --embed-subs or --write-subs")
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
            fetched = fetch_comments(self._downloader, info["id"])
        except (CommentAPIError, FontError) as e:
            raise PostProcessingError(str(e)) from e

        if not self._checked_fonts:
            self._warn_about_missing_japanese_fonts(font_chains)
            self._checked_fonts = True
        slot_layers = layout_comments(
            fetched,
            font_chains,
            self._content_length_ms(info),
            self._ng_score_threshold,
            info["id"],
        )
        self.to_screen(f"Laid out {sum(len(slot_layer.slots) for slot_layer in slot_layers)} comments")

        other_subtitles = dict(info.get("requested_subtitles") or {})
        other_subtitles.pop(JSON_SUBTITLE_LANG, None)
        # FFmpegEmbedSubtitlePP embeds the subtitles in this order, so the comments become the track s:0.
        info["requested_subtitles"] = {
            SUBTITLE_LANG: {
                "ext": "ass",
                "name": "Comments",
                "data": build_ass(slot_layers, width, height, self._opacity),
            },
            **other_subtitles,
        }
        if self._default:
            self._make_first_subtitle_track_default()
        return [], info

    def _content_length_ms(self, info) -> int | None:
        # The official player uses the duration of the media, which is not the rounded duration from the API.
        try:
            duration = media_duration(self._downloader, info)
        except PlaylistError as e:
            self.report_warning(f"Cannot read the media duration from the HLS playlist: {e}")
            duration = None
        duration = duration or info.get("duration")
        return math.floor(duration * 1000) if duration else None

    def _warn_about_missing_japanese_fonts(self, font_chains: dict[str, FontChain]):
        for key, chain in font_chains.items():
            if not chain.covers(JAPANESE_SAMPLE):
                self.report_warning(
                    f"No installed font for {key} comments has Japanese characters, so Japanese text in these "
                    f"comments does not match the layout. Install one of these fonts: {', '.join(chain.missing)}"
                )

    def _select_ass_container(self, info):
        # yt-dlp creates the output file name after the video stage, and the merger
        # selects the container from the extension.
        if not info.get("requested_formats") or info.get("ext") == ASS_CONTAINER:
            return
        if self.get_param("merge_output_format") is not None:
            self.report_warning(f"Comments can lose their layout because {info['ext']} cannot hold ASS subtitles")
            return
        self.to_screen(f"Merging into {ASS_CONTAINER} because {info['ext']} cannot hold ASS subtitles")
        info["ext"] = ASS_CONTAINER

    def _make_first_subtitle_track_default(self):
        pp_args = self._downloader.params.setdefault("postprocessor_args", {})
        if not isinstance(pp_args, dict):
            self.report_warning("Cannot make the subtitle track default because postprocessor_args is not a dict")
            return
        current = cli_configuration_args(pp_args, EMBED_OUTPUT_ARG_KEYS)
        if DEFAULT_DISPOSITION_ARGS[0] not in current:
            pp_args[EMBED_OUTPUT_ARG_KEYS[0]] = [*current, *DEFAULT_DISPOSITION_ARGS]
