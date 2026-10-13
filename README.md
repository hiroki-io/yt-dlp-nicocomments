# yt-dlp-nicocomments

A [yt-dlp](https://github.com/yt-dlp/yt-dlp) postprocessor plugin that converts
Niconico comments to an ASS subtitle track.

![Sample comments in many colors, sizes, and scripts scrolling over a dark blue background](https://raw.githubusercontent.com/hiroki-io/yt-dlp-nicocomments/main/docs/sample.avif)

## Install

If yt-dlp is installed with uv or pip, install the plugin in the same
environment:

```sh
uv tool install yt-dlp --with yt-dlp-nicocomments
```

```sh
pip install -U yt-dlp-nicocomments
```

If you use the yt-dlp executable, download the `.whl` file from the
[latest release](https://github.com/hiroki-io/yt-dlp-nicocomments/releases/latest)
and put it in a yt-dlp plugin directory:

| Platform     | Plugin directory            |
| ------------ | --------------------------- |
| macOS, Linux | `~/.config/yt-dlp/plugins/` |
| Windows      | `%APPDATA%\yt-dlp\plugins\` |

To make sure that the release workflow of this repository built the file, run:

```sh
gh attestation verify yt_dlp_nicocomments-*.whl -R hiroki-io/yt-dlp-nicocomments
```

The yt-dlp executable cannot load fontTools from the plugin directory. To attach
smaller fonts (see
[docs/fonts.md](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/docs/fonts.md)),
install fontTools so that the `pyftsubset` command is on `PATH`, for example
with `brew install fonttools` or `pipx install fonttools`.

## Usage

```sh
yt-dlp --embed-subs --use-postprocessor "NicoComments:when=video" \
  https://www.nicovideo.jp/watch/sm9
```

`when=video` is necessary because the plugin must run before yt-dlp writes the
subtitles.

### Options

Options are passed after the postprocessor name (`NicoComments:`), separated by
semicolons:

```sh
--use-postprocessor "NicoComments:when=video;lang=ja,en;nglevel=high"
```

| Option         | Values                                   | Default  | Description                                                                            |
| -------------- | ---------------------------------------- | -------- | -------------------------------------------------------------------------------------- |
| `lang`         | `ja`, `en`, or `zh`, separated by commas | `ja`     | Comment languages. Each language becomes a separate subtitle track.                    |
| `comments`     | A number of comments, or `all`           | `0`      | Minimum number of comments per language. See [Past comments](#past-comments).          |
| `nglevel`      | `high`, `medium`, `low`, or `none`       | `medium` | Hide comments that many users added to their NG lists. `high` hides the most comments. |
| `opacity`      | A number from `0` to `1`                 | `1`      | Comment opacity                                                                        |
| `writejson`    | `true` or `false`                        | `false`  | Write comments to a JSON file                                                          |
| `defaulttrack` | `true` or `false`                        | `true`   | Mark the subtitle track of the first comment language as default                       |
| `embedfonts`   | `true` or `false`                        | `true`   | Attach the fonts to the video file when `--embed-subs` is used                         |

### Shortcut

To shorten the command, define an alias in the yt-dlp configuration file
`~/.config/yt-dlp/config`:

```text
--alias --nico "--embed-subs --use-postprocessor NicoComments:when=video"
```

Then use the alias instead of the options:

```sh
yt-dlp --nico https://www.nicovideo.jp/watch/sm9
```

### Save only the comment track

To save the comment track as an ASS file without the video, use `--write-subs`
and `--skip-download`:

```sh
yt-dlp --skip-download --write-subs --use-postprocessor "NicoComments:when=video" \
  https://www.nicovideo.jp/watch/sm9
```

The ASS file does not contain the fonts, so install the font files linked in
[docs/fonts.md](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/docs/fonts.md)
on the computer that plays it.

### Past comments

The comment API returns only the recent comments of a video. When these comments
are fewer than `comments`, the plugin loads older comments until it has at least
that many comments for each language, or until no older comments are left.
`comments=all` loads all past comments.

Fetching past comments requires a free Niconico account. Pass your cookies to
yt-dlp, for example with `--cookies-from-browser`:

```sh
yt-dlp --cookies-from-browser chrome --embed-subs \
  --use-postprocessor "NicoComments:when=video;comments=10000" \
  https://www.nicovideo.jp/watch/sm9
```

### Smooth scrolling in mpv

mpv redraws subtitles only when the video frame changes. To update them at the
display refresh rate, load the mpv script
[`nicocomments-display-fps.lua`](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/nicocomments-display-fps.lua).
The script converts the video to the refresh rate of the display that shows the
mpv window.

The script adds an `fps` video filter. If mpv or IINA saves the playback
position, it also saves this filter, and the filter stays in effect when you
resume the video without the script.

#### mpv

Download the script and run mpv with it:

```sh
mpv --script=/path/to/nicocomments-display-fps.lua --video-sync=display-resample video.mkv
```

[`nicocomments-play.sh`](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/nicocomments-play.sh)
runs the same command and passes its arguments to mpv. Put it in the same
directory as `nicocomments-display-fps.lua`:

```sh
chmod +x nicocomments-play.sh
./nicocomments-play.sh video.mkv
```

On Windows, use
[`nicocomments-play.bat`](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/nicocomments-play.bat)
in the same way:

```bat
nicocomments-play.bat video.mkv
```

To use the script for all videos, put it in the mpv scripts directory and add
`video-sync=display-resample` to `mpv.conf`:

| Platform     | mpv scripts directory    |
| ------------ | ------------------------ |
| macOS, Linux | `~/.config/mpv/scripts/` |
| Windows      | `%APPDATA%\mpv\scripts\` |

#### IINA

[IINA](https://iina.io/) plays videos with mpv, so it can use the same script.
Open **Settings > Advanced**, select **Enable advanced settings**, and add these
entries to **Additional mpv options**:

| Key          | Value                                           |
| ------------ | ----------------------------------------------- |
| `scripts`    | Absolute path to `nicocomments-display-fps.lua` |
| `video-sync` | `display-resample`                              |

If you already set up the mpv scripts directory and `mpv.conf`, you can instead
select **Use config directory** and choose `~/.config/mpv`. Restart IINA after
you change these settings.

With IINA 1.5.0 or later on macOS 27, comments may stutter in full screen mode.
To work around this, open **Settings > Interface > Appearance > Liquid Glass**
and turn off **On Screen Display**, or open **Settings > General** and select
**Use legacy full screen**.

### Burn the comments into the video

To burn the comment track into the video, run this command with an FFmpeg build
that includes libass:

```sh
ffmpeg -i video.mkv -vf subtitles=video.mkv -c:a copy video-burned.mp4
```

FFmpeg encodes the video again, so this takes time and lowers the quality.

## Fonts

The package includes Noto fonts under the SIL Open Font License 1.1. With
`--embed-subs`, the plugin saves the video as an MKV file and attaches the fonts
to it (unless `embedfonts=false`). See
[docs/fonts.md](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/docs/fonts.md)
for the list of fonts.

## Trademarks

Niconico is a trademark or registered trademark of DWANGO Co., Ltd. This project
is not affiliated with or endorsed by DWANGO Co., Ltd.
