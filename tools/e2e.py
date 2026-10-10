import importlib
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.downloader.common import FileDownloader

DURATION = "5"
SOURCE_DIRECTORY = Path(__file__).resolve().parent.parent / "yt_dlp_plugins"
PLUGIN_MODULE = "yt_dlp_plugins.postprocessor.nicocomments"


class PlaceholderFD(FileDownloader):
    def real_download(self, filename, info_dict: Mapping[str, Any]):
        if info_dict.get("vcodec") != "none":
            size = f"{info_dict['width']}x{info_dict['height']}"
            source = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        else:
            source = ["-f", "lavfi", "-i", "sine", "-c:a", "aac"]
        tmpfilename = self.temp_name(filename)
        subprocess.run(["ffmpeg", "-v", "error", "-y", *source, "-t", DURATION, "-f", "mp4", tmpfilename], check=True)
        self.try_rename(tmpfilename, filename)
        file_size = os.path.getsize(filename)
        self._hook_progress(  # pyright: ignore[reportAttributeAccessIssue]
            {"filename": filename, "status": "finished", "downloaded_bytes": file_size, "total_bytes": file_size},
            info_dict,
        )
        return True


def replace_downloader(module):
    get_suitable_downloader = module.get_suitable_downloader

    # Keep None so that yt-dlp still downloads each requested format separately and merges them.
    def get_placeholder_downloader(*args, **kwargs):
        return PlaceholderFD if get_suitable_downloader(*args, **kwargs) else None

    module.get_suitable_downloader = get_placeholder_downloader


def forbid_real_downloads():
    download = FileDownloader.download

    def placeholder_only_download(self, *args, **kwargs):
        if not isinstance(self, PlaceholderFD):
            raise AssertionError(f"{self.FD_NAME} tried to download the media")
        return download(self, *args, **kwargs)

    FileDownloader.download = placeholder_only_download


def check_installed_plugin():
    module = sys.modules.get(PLUGIN_MODULE)
    if module is None or module.__file__ is None:
        raise AssertionError("yt-dlp did not load the plugin")
    print(f"Loaded the plugin from {module.__file__}")
    if Path(module.__file__).resolve().is_relative_to(SOURCE_DIRECTORY):
        raise AssertionError("yt-dlp loaded the plugin from the source tree instead of the built wheel")


if __name__ == "__main__":
    replace_downloader(importlib.import_module("yt_dlp.YoutubeDL"))
    forbid_real_downloads()
    try:
        yt_dlp.main(sys.argv[1:])
    except SystemExit as e:
        if not e.code and os.environ.get("E2E_INSTALLED_PLUGIN") == "1":
            check_installed_plugin()
        raise
