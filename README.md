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

| Option         | Values                                   | Default  | Description                                                                                                                         |
| -------------- | ---------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `lang`         | `ja`, `en`, or `zh`, separated by commas | `ja`     | Comment languages. Each language becomes a separate subtitle track.                                                                 |
| `comments`     | A number of comments, or `all`           | `0`      | Minimum number of comments per language (see [Past comments](#past-comments)). With `0`, the plugin loads only the recent comments. |
| `nglevel`      | `high`, `medium`, `low`, or `none`       | `medium` | Hide comments that many users added to their NG lists. `high` hides the most comments.                                              |
| `opacity`      | A number from `0` to `1`                 | `1`      | Comment opacity                                                                                                                     |
| `writejson`    | `true` or `false`                        | `false`  | Write comments to a JSON file                                                                                                       |
| `defaulttrack` | `true` or `false`                        | `true`   | Mark the subtitle track of the first comment language as default                                                                    |
| `embedfonts`   | `true` or `false`                        | `true`   | Attach the fonts to the video file when `--embed-subs` is used                                                                      |

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

### Burn the comments into the video

To burn the comment track into the video, run this command with an FFmpeg build
that includes libass:

```sh
ffmpeg -i video.mkv -vf subtitles=video.mkv -c:a copy video-burned.mp4
```

FFmpeg encodes the video again, so this takes time and lowers the quality.

## Play in mpv

The launcher scripts in the repository run mpv so that the comments scroll
smoothly. They can also play a Niconico URL with its comments without saving the
video. See
[docs/mpv.md](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/docs/mpv.md)
for the setup, including Windows and IINA. After you set up the launcher
scripts, run:

```sh
./nicocomments-play.sh video.mkv
./nicocomments-play.sh https://www.nicovideo.jp/watch/sm9
```

On Windows, use `nicocomments-play.bat` in the same way:

```bat
nicocomments-play.bat video.mkv
```

## Fonts

The package includes Noto fonts under the SIL Open Font License 1.1. With
`--embed-subs`, the plugin saves the video as an MKV file and attaches the fonts
to it (unless `embedfonts=false`). See
[docs/fonts.md](https://github.com/hiroki-io/yt-dlp-nicocomments/blob/main/docs/fonts.md)
for the list of fonts.

## Trademarks

Niconico is a trademark or registered trademark of DWANGO Co., Ltd. This project
is not affiliated with or endorsed by DWANGO Co., Ltd.
