# Contributing

## Run from a clone

To use a clone with yt-dlp, run these commands in its root directory to download
the fonts and add it to a yt-dlp plugin directory:

```sh
python3 tools/font_data.py
mkdir -p ~/.config/yt-dlp/plugins
ln -s "$PWD" ~/.config/yt-dlp/plugins/yt-dlp-nicocomments
```

## Tests and lint

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright
cd tools/drift
npm ci
npm run lint
```

`npm run format` formats the TypeScript code.

## Fonts

The fonts are not in the repository. `uv run` downloads them to
`yt_dlp_plugins/postprocessor/_nicocomments/font_data` on build. After changing
`font_files.py`, run `python3 tools/font_data.py --licenses` to download the
fonts and update their licenses in `LICENSES`.

## Build dependencies

The build dependencies are pinned in `build-requirements.txt`. After changing
`[build-system]` in `pyproject.toml`, update `build-requirements.in` and run:

```sh
uv pip compile build-requirements.in --universal --python-version 3.10 --generate-hashes --output-file build-requirements.txt
```

## Drift checks

The Drift workflow detects changes in the comment API and the official web
player that can affect the plugin. `tools/drift/api.py` checks the API response
fields that the plugin uses. `tools/drift/player.mts` compares the comment code
of the official player with `tools/drift/official.json`, which intentionally
does not contain the official code.

When the official player changes, run `node tools/drift/player.mts check`
locally to see the changed code, update the plugin, and then run
`node tools/drift/player.mts update`. Local runs save the fetched bundle in
`tools/drift/bundles/`.

## Releases

For each user-facing change, add a file named `release-notes/+<name>.md` that
contains one list item, for example:

```md
- Add the `comments` option to load past comments
```

To make a release, run `release.sh` with `--major`, `--minor`, or `--patch`. It
opens the release notes in the Git editor, then commits and tags the new
version. Then push the commit and the tag:

```sh
./release.sh --minor
git push --atomic --follow-tags origin main
```

To change the notes of a published release, edit `release-notes/X.Y.Z.md`,
commit and push it, then run:

```sh
gh release edit X.Y.Z --notes-file release-notes/X.Y.Z.md
```
