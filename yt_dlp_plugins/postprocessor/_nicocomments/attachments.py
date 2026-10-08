import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor, FFmpegPostProcessorError
from yt_dlp.utils import PostProcessingError, prepend_extension

from .font_files import FontFile
from .fonts import bundled_font_path, font_data_directory

EMBEDDING_KEY = "__nicocomments_embedding"
ASS_CONTAINER = "mkv"


@dataclass(frozen=True)
class CommentEmbedding:
    track_names: frozenset[str]
    fonts: frozenset[FontFile]
    default: bool


class NicoCommentFontsPP(FFmpegPostProcessor):
    def run(self, info):
        embeddings: list[CommentEmbedding] = info.pop(EMBEDDING_KEY, [])
        path = info.get("filepath")
        if not path or not os.path.exists(path):
            return [], info
        if not any(embedding.fonts or embedding.default for embedding in embeddings):
            return [], info
        if not self.probe_available or self.probe_basename != "ffprobe":
            self.report_warning(
                "The fonts are not attached and the comment track is not made default because ffprobe is not found"
            )
            return [], info
        try:
            metadata = self.get_metadata_object(path)
        except (PostProcessingError, OSError, ValueError) as error:
            self.report_warning(f'Cannot read the streams of "{path}": {error}')
            return [], info
        subtitles = [stream for stream in metadata.get("streams", []) if stream["codec_type"] == "subtitle"]
        # FFmpegEmbedSubtitlePP sets both tags to the track name, and MP4 keeps only handler_name.
        track_names = [{stream.get("tags", {}).get(tag) for tag in ("title", "handler_name")} for stream in subtitles]
        tracks = [
            (embedding, indexes)
            for embedding in embeddings
            if (indexes := [index for index, names in enumerate(track_names) if embedding.track_names & names])
        ]
        if not tracks:
            return [], info

        fonts = {font for embedding, _ in tracks for font in embedding.fonts}
        attachable = info["ext"] == ASS_CONTAINER and any(
            subtitles[index].get("codec_name") == "ass" for _, indexes in tracks for index in indexes
        )
        attaching = bool(fonts) and attachable
        if fonts and not attaching:
            self.report_warning("The fonts are not attached because the comments are not ASS subtitles in an MKV file")
        default_index = next((indexes[0] for embedding, indexes in tracks if embedding.default), None)
        if not attaching and default_index is None:
            return [], info
        opts = []
        if default_index is not None:
            for index in range(len(subtitles)):
                opts += [f"-disposition:s:{index}", "+default" if index == default_index else "-default"]

        temporary_path = prepend_extension(path, "temp")
        if attaching:
            self.to_screen(f'Attaching the Noto fonts to "{path}"')
        try:
            with tempfile.TemporaryDirectory(prefix="yt-dlp-nicocomments-", ignore_cleanup_errors=True) as directory:
                if attaching:
                    opts += self._attach_opts(fonts, Path(directory))
                self.run_ffmpeg(path, temporary_path, [*self.stream_copy_opts(ext=info["ext"]), *opts])
            os.replace(temporary_path, path)
        except (FFmpegPostProcessorError, OSError) as error:
            self.report_warning(f'Cannot update "{path}": {error}')
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        return [], info

    @staticmethod
    def _attach_opts(fonts: set[FontFile], directory: Path) -> list[str]:
        opts = []
        package_directory = font_data_directory()
        for font in sorted(fonts, key=lambda font: font.filename):
            # The fonts are already attached when the subtitles are embedded again in the same file.
            opts += ["-map", f"-0:t:m:filename:{font.filename}"]
            # FFmpeg takes the filename tag from the text after the last slash, also on Windows.
            path = bundled_font_path(font, package_directory, directory)
            opts += [
                "-attach",
                FFmpegPostProcessor._ffmpeg_filename_argument(path.as_posix()),
                f"-metadata:s:t:m:filename:{font.filename}",
                f"mimetype={font.mimetype}",
            ]
        return opts
