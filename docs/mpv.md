# mpv scripts

The repository has two mpv scripts and launcher scripts that run mpv with them.
They are not part of the package. To get them, clone the repository, or open
each file below and select **Download raw file**. Keep the files in one
directory.

| Script                                                            | Purpose                                               |
| ----------------------------------------------------------------- | ----------------------------------------------------- |
| [`nicocomments-display-fps.lua`](../nicocomments-display-fps.lua) | [Smooth scrolling](#smooth-scrolling) of the comments |
| [`nicocomments-url.lua`](../nicocomments-url.lua)                 | [Play a URL](#play-a-url) with its comments           |
| [`nicocomments-play.sh`](../nicocomments-play.sh)                 | [Launcher](#launcher-scripts) for macOS and Linux     |
| [`nicocomments-play.bat`](../nicocomments-play.bat)               | [Launcher](#launcher-scripts) for Windows             |

## Launcher scripts

`nicocomments-play.sh` runs mpv with `nicocomments-display-fps.lua`,
`nicocomments-url.lua`, and `--video-sync=display-resample`, and passes its
arguments to mpv. Put it in the same directory as the two Lua scripts:

```sh
chmod +x nicocomments-play.sh
./nicocomments-play.sh video.mkv
./nicocomments-play.sh https://www.nicovideo.jp/watch/sm9
```

On Windows, use `nicocomments-play.bat` in the same way:

```bat
nicocomments-play.bat video.mkv
```

To play a URL, the plugin and the fonts must be set up as described in
[Play a URL](#play-a-url).

## Smooth scrolling

mpv redraws subtitles only when the video frame changes. To update them at the
display refresh rate, load `nicocomments-display-fps.lua` and set
`video-sync=display-resample`:

```sh
mpv --script=/path/to/nicocomments-display-fps.lua --video-sync=display-resample video.mkv
```

The script converts the video to the refresh rate of the display that shows the
mpv window.

The script adds an `fps` video filter. If mpv or IINA saves the playback
position, it also saves this filter, and the filter stays in effect when you
resume the video without the script.

To use the script for all videos, see
[Load the scripts automatically](#load-the-scripts-automatically).

## Play a URL

mpv can play a Niconico URL without saving the video. To show the comments on
it, load `nicocomments-url.lua`:

```sh
mpv --script=/path/to/nicocomments-url.lua https://www.nicovideo.jp/watch/sm9
```

To load the comments, the script runs the yt-dlp that mpv uses, and passes the
`--ytdl-raw-options` of mpv to it. The plugin must be installed for that yt-dlp
(see [Install](../README.md#install)). If the plugin is installed for another
yt-dlp, set `ytdl_path` to that yt-dlp.

Set the options of the script in `script-opts/nicocomments.conf` in the mpv
configuration directory, or in the environment variables:

| Option      | Environment variable     | Description                                                                   |
| ----------- | ------------------------ | ----------------------------------------------------------------------------- |
| `options`   | `NICOCOMMENTS_OPTIONS`   | Plugin [options](../README.md#options), for example `lang=ja,en;nglevel=high` |
| `fonts_dir` | `NICOCOMMENTS_FONTS_DIR` | Directory that contains the fonts of the comments                             |
| `ytdl_path` |                          | Path to the yt-dlp executable. The default is the yt-dlp that mpv uses        |

```text
options=lang=ja,en;nglevel=high
fonts_dir=/path/to/font_data
```

mpv needs the fonts to show the comments correctly. Set `fonts_dir` to the
`yt_dlp_plugins/postprocessor/_nicocomments/font_data` directory of the
installed plugin, or install the font files linked in [fonts.md](fonts.md).

To use the script for all URLs, see
[Load the scripts automatically](#load-the-scripts-automatically).

## Load the scripts automatically

Each Lua script works without the other, so load only the scripts that you need.
`nicocomments-display-fps.lua` converts all videos, not only the videos with
comments, and it is the only script that needs `video-sync`. After this setup,
run mpv without the launcher scripts.

### mpv

Put the Lua scripts that you need in the mpv scripts directory:

| Platform     | mpv scripts directory    |
| ------------ | ------------------------ |
| macOS, Linux | `~/.config/mpv/scripts/` |
| Windows      | `%APPDATA%\mpv\scripts\` |

If you load `nicocomments-display-fps.lua`, also add
`video-sync=display-resample` to `mpv.conf`.

### IINA

[IINA](https://iina.io/) plays videos with mpv, so it can use the same scripts.
Open **Settings > Advanced**, select **Enable advanced settings**, and add these
entries to **Additional mpv options**:

| Key          | Value                                                   |
| ------------ | ------------------------------------------------------- |
| `scripts`    | Absolute paths to the Lua scripts, separated by a colon |
| `video-sync` | `display-resample`                                      |

The `video-sync` entry is necessary only if you load
`nicocomments-display-fps.lua`.

If you already set up the mpv scripts directory, you can instead select **Use
config directory** and choose `~/.config/mpv`. Restart IINA after you change
these settings.

With IINA 1.5.0 or later on macOS 27, comments may stutter in full screen mode.
To work around this, open **Settings > Interface > Appearance > Liquid Glass**
and turn off **On Screen Display**, or open **Settings > General** and select
**Use legacy full screen**.
