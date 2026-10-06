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

`npm run lint` also type-checks the TypeScript code. `npm run format` formats
it.

## Drift checks

The Drift workflow detects changes in the comment API and the official web
player that can affect the plugin:

- `tools/drift/api.py` checks the API response fields that the plugin uses.
- `tools/drift/player.mts` compares the comment code of the official player with
  `tools/drift/official.json`. To keep the official code out of this repository,
  the file records only hashes and names. Run `node player.mts check` locally to
  see the changed code.

When the official player changes, update the plugin and run
`node tools/drift/player.mts update`.
