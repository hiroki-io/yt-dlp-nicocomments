# Contributing

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

`npm run lint` also type-checks the TypeScript code. `npm run format` formats
it.

## Fonts

The fonts are not in the repository. `uv run` downloads them to
`yt_dlp_plugins/postprocessor/_nicocomments/font_data` when it builds the
project, and `uv build` includes them in the distributions. After changing
`font_files.py`, run `python3 tools/font_data.py --licenses`. This command also
updates the license files of the fonts in `LICENSES`, which are in the
repository.

## Build dependencies

The Release workflow builds the distributions with the build dependencies pinned
in `build-requirements.txt`. After changing `[build-system]` in
`pyproject.toml`, update `build-requirements.in` and run:

```sh
uv pip compile build-requirements.in --universal --python-version 3.10 --generate-hashes --output-file build-requirements.txt
```

## Drift checks

The Drift workflow detects changes in the comment API and the official web
player that can affect the plugin:

- `tools/drift/api.py` checks the API response fields that the plugin uses.
- `tools/drift/player.mts` compares the comment code of the official player with
  `tools/drift/official.json`. The file records only hashes and names so that
  the official code stays out of this repository. Run
  `node tools/drift/player.mts check` locally to see the changed code.

When the official player changes, update the plugin and run
`node tools/drift/player.mts update`.

## Releases

For each user-facing change, add a file named `release-notes/+<name>.md` that
contains one list item, for example:

```md
- Add the `comments` option to load past comments
```

To make a release, run:

```sh
./release.sh VERSION
git push --atomic origin main VERSION
```
