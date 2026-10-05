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

Put this repository in a yt-dlp plugin directory:

```sh
mkdir -p ~/.config/yt-dlp/plugins
ln -s ~/yt-dlp-nicocomments ~/.config/yt-dlp/plugins/yt-dlp-nicocomments
```

If yt-dlp is installed with pip or uv, you can also install the plugin as a
package:

```sh
uv tool install yt-dlp --with ~/yt-dlp-nicocomments
```

## Usage

```sh
yt-dlp --embed-subs --use-postprocessor "NicoComments:when=video" \
  https://www.nicovideo.jp/watch/sm9
```

Options are passed after the name, separated by semicolons:

- `opacity`: comment opacity (default: 1)
- `default`: mark the embedded subtitle track as default: `true`, `yes`, `1`,
  `false`, `no`, or `0` (default: true)
- `nglevel`: hide comments that many users added to their NG list: `high`,
  `medium`, `low`, or `none` (default: medium). `high` hides the most comments.

```sh
--use-postprocessor "NicoComments:when=video;opacity=0.8"
```

### Shortcut

To shorten the command, define an alias in the yt-dlp configuration file
`~/.config/yt-dlp/config`:

```
--alias --nico "--embed-subs --use-postprocessor NicoComments:when=video"
```

Then use the alias instead of the options:

```sh
yt-dlp --nico https://www.nicovideo.jp/watch/sm9
```

### Burn the comments into the video

To burn the comment track into the video with an FFmpeg build that includes
libass:

```sh
ffmpeg -i video.mkv -vf subtitles=video.mkv -c:a copy video-burned.mp4
```

FFmpeg encodes the video again, so this takes time and lowers the quality.
