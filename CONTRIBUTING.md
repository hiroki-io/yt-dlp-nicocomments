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

Run `npm run format` in `tools/drift` to format the JavaScript code.

## Drift checks

The Drift workflow checks every week that the comment API and the official web
player still match this plugin. `tools/drift/api.py` checks the fields of the
API responses that the plugin uses. `tools/drift/player.mjs` compares the
comment code of the official player with `tools/drift/official.json`.

When the official player changes, update the plugin as necessary and record the
new state:

```sh
cd tools/drift
npm ci
node player.mjs update
```

`tests/test_official_constants.py` compares the recorded constants with the
constants of the plugin.
