# yt-dlp-nicocomments

A [yt-dlp](https://github.com/yt-dlp/yt-dlp) postprocessor plugin that converts
Niconico comments to an ASS subtitle track.

## Fonts

The plugin lays out and draws comments with:

- Noto Sans JP
  ([Regular](https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/JP/NotoSansJP-Regular.otf)
  and
  [Bold](https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/JP/NotoSansJP-Bold.otf))
- Noto Serif JP
  ([Regular](https://github.com/notofonts/noto-cjk/raw/Serif2.003/Serif/SubsetOTF/JP/NotoSerifJP-Regular.otf))
- [Noto Emoji](https://raw.githubusercontent.com/google/fonts/b979dba422e445492b0eb9951ac52ee0b4d648c3/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf)
- [Noto Sans Math](https://raw.githubusercontent.com/google/fonts/dbd1ab6e65dc59bcda3ca8de9fd372f58f98e0af/ofl/notosansmath/NotoSansMath-Regular.ttf)
- [Noto Sans Symbols 2](https://raw.githubusercontent.com/google/fonts/7b6724ac7ececc713e9ba93af309f7520c9a80a3/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf)
- Noto Sans SC
  ([Regular](https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf))
- Noto Sans KR
  ([Regular](https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF/KR/NotoSansKR-Regular.otf))

The package includes these fonts under the SIL Open Font License 1.1. With
`--embed-subs`, the plugin saves the video as an MKV file and attaches the fonts
to it.

To keep the video file small, the plugin removes the unused glyphs from the
fonts using [fontTools](https://github.com/fonttools/fonttools).

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
smaller fonts, install fontTools so that the `pyftsubset` command is on `PATH`,
for example with `brew install fonttools` or `pipx install fonttools`.

To use the code from a clone of this repository, download the fonts and put the
repository in a plugin directory:

```sh
python3 ~/yt-dlp-nicocomments/tools/font_data.py
mkdir -p ~/.config/yt-dlp/plugins
ln -s ~/yt-dlp-nicocomments ~/.config/yt-dlp/plugins/yt-dlp-nicocomments
```

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

| Option    | Values                                    | Default  | Description                                                                            |
| --------- | ----------------------------------------- | -------- | -------------------------------------------------------------------------------------- |
| `lang`    | `ja`, `en`, or `zh`, separated by commas  | `ja`     | Comment languages. Each language becomes a separate subtitle track.                    |
| `nglevel` | `high`, `medium`, `low`, or `none`        | `medium` | Hide comments that many users added to their NG lists. `high` hides the most comments. |
| `opacity` | A number from `0` to `1`                  | `1`      | Comment opacity                                                                        |
| `fonts`   | `true`, `yes`, `1`, `false`, `no`, or `0` | `true`   | Attach the fonts to the video file when `--embed-subs` is used                         |
| `default` | `true`, `yes`, `1`, `false`, `no`, or `0` | `true`   | Mark the subtitle track of the first comment language as default                       |

Example:

```sh
--use-postprocessor "NicoComments:when=video;lang=ja,en;nglevel=high"
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

The ASS file does not contain the fonts, so install the font files linked in
[Fonts](#fonts) on the computer that plays it.

### Burn the comments into the video

To burn the comment track into the video, run this command with an FFmpeg build
that includes libass:

```sh
ffmpeg -i video.mkv -vf subtitles=video.mkv -c:a copy video-burned.mp4
```

FFmpeg encodes the video again, so this takes time and lowers the quality.
