# Contributing

## Setup

```console
$ git clone https://github.com/antonsoo/flakemap
$ cd flakemap
$ uv sync
```

## Workflow

```console
$ uv run pytest -q            # tests
$ uv run ruff check .         # lint
$ uv run ruff format .        # format
$ uv run mypy                 # typecheck (strict)
```

All four must pass before a PR is merged. There is no separate style guide:
`ruff format` is authoritative.

## Adding a JUnit dialect

If you hit a report `flakemap` mis-parses, please attach a redacted sample
(strip anything proprietary) along with which tool produced it. See
`docs/formats.md` for how existing dialects are documented and tested --
new dialects should follow the same pattern: a fixture under
`tests/fixtures/`, a parsing test in `tests/test_junit_parsing.py`, and an
entry in `docs/formats.md`'s dialect table stating whether it was verified
against real tool output or hand-authored from documentation.

## Scope

flakemap reads JUnit XML and computes statistics; it does not talk to any CI
provider's API, store data server-side, or phone home. Contributions that add
a network dependency for the core analysis path will likely be declined --
open an issue first if you have a use case that seems to need one.
