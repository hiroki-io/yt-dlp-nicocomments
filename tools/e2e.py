import importlib
import os
import subprocess
import sys

import yt_dlp
from yt_dlp.downloader.common import FileDownloader

DURATION = "5"


class PlaceholderFD(FileDownloader):
    def real_download(self, filename, info_dict):
        if info_dict.get("vcodec") != "none":
            size = f"{info_dict['width']}x{info_dict['height']}"
            source = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        else:
            source = ["-f", "lavfi", "-i", "sine", "-c:a", "aac"]
        tmpfilename = self.temp_name(filename)
        subprocess.run(["ffmpeg", "-v", "error", "-y", *source, "-t", DURATION, "-f", "mp4", tmpfilename], check=True)
        self.try_rename(tmpfilename, filename)
        size = os.path.getsize(filename)
        self._hook_progress(
            {"filename": filename, "status": "finished", "downloaded_bytes": size, "total_bytes": size}, info_dict
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


if __name__ == "__main__":
    replace_downloader(importlib.import_module("yt_dlp.YoutubeDL"))
    forbid_real_downloads()
    yt_dlp.main(sys.argv[1:])
