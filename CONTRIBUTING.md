# Contributing

## Tests and lint

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
cd tools/drift
npm ci
npm run lint
```

Run `npm run format` in `tools/drift` to format the TypeScript code.
`npm run lint` also type-checks it.

## Drift checks

The Drift workflow checks that the comment API and the official web player still
match this plugin. It runs every week and on changes to the drift checks or to
the API client. `tools/drift/api.py` checks the fields of the API responses that
the plugin uses. `tools/drift/player.mts` compares the comment code of the
official player with `tools/drift/official.json`. To keep the official code out
of this repository, `official.json` records only hashes and names, and the CI
logs show only the names of the changed code. Run `node player.mts check`
locally to see the new code.

When the official player changes, update the plugin as necessary and record the
new state:

```sh
cd tools/drift
npm ci
node player.mts update
```

`tests/test_official_constants.py` compares the recorded constants with the
constants of the plugin.
