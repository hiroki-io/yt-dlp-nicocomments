# yt-dlp-nicocomments

A [yt-dlp](https://github.com/yt-dlp/yt-dlp) postprocessor plugin that converts
Niconico comments to an ASS subtitle track.

## Requirements

Install the fonts that the official player uses on your platform:

| Platform | Fonts                                                                                                |
| -------- | ---------------------------------------------------------------------------------------------------- |
| macOS    | Hiragino Sans W6 and W4, Hiragino Mincho ProN W3, Yu Gothic Medium, Yu Mincho Medium                 |
| Linux    | Noto Sans CJK JP Regular and Bold, Noto Serif CJK JP Regular (`fonts-noto-cjk` on Debian and Ubuntu) |
| Windows  | Arial, MS PGothic, Yu Gothic Regular, Yu Mincho Regular, SimSun                                      |

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

To use the code from a clone of this repository, put the repository in a plugin
directory:

```sh
mkdir -p ~/.config/yt-dlp/plugins
ln -s ~/yt-dlp-nicocomments ~/.config/yt-dlp/plugins/yt-dlp-nicocomments
```

## Usage

```sh
yt-dlp --embed-subs --use-postprocessor "NicoComments:when=video" \
  https://www.nicovideo.jp/watch/sm9
```

Options are passed after the name, separated by semicolons:

- `opacity`: comment opacity (default: `1`)
- `default`: mark the embedded subtitle track as default (`true`, `yes`, `1`,
  `false`, `no`, or `0`; default: `true`)
- `nglevel`: hide comments that many users added to their NG lists (`high`,
  `medium`, `low`, or `none`; default: `medium`). `high` hides the most
  comments.
- `lang`: comment language (`ja`, `en`, or `zh`; default: `ja`). Each language
  has different comments.

```sh
--use-postprocessor "NicoComments:when=video;opacity=0.8"
```

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

### Burn the comments into the video

To burn the comment track into the video, run this command with an FFmpeg build
that includes libass:

```sh
ffmpeg -i video.mkv -vf subtitles=video.mkv -c:a copy video-burned.mp4
```

FFmpeg encodes the video again, so this takes time and lowers the quality.
