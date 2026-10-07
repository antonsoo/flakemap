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

For report changes, install the locked browser tools (Node 22+) and generate the
fixtures. Checks exercise keyboard operation, 320/1200px layouts, light/dark
themes, accessibility, CSP, escaping and offline file loading in Chromium and Firefox:

```bash
npm ci
npx playwright install chromium firefox   # once, if not already installed
uv run python scripts/browser_fixtures.py
npm run test:browser
```

The reports make no external requests. JSON evidence and screenshots go to
`scratch/browser/`; inspect screenshots as well as the assertions. These Node
dependencies are development-only; the Python package still needs only Rich.
The Java fixture is regenerated separately as described in
[`examples/retry_project/README.md`](examples/retry_project/README.md); ordinary
tests read the committed XML and do not need Java or Maven.

## Adding a JUnit dialect

If you hit a report `flakemap` mis-parses, please attach a redacted sample
(strip anything proprietary) along with which tool produced it. See
`docs/formats.md` for how existing dialects are documented and tested --
new dialects should follow the same pattern: a fixture under
`tests/fixtures/`, a parsing test in `tests/test_junit_parsing.py`, and an
entry in `docs/formats.md`'s dialect table stating whether it was verified
against real tool output or hand-authored from documentation.

## Scope

flakemap reads JUnit XML and TRX and computes statistics; it does not talk to any CI
provider's API, store data server-side, or phone home. Contributions that add
a network dependency for the core analysis path will likely be declined --
open an issue first if you have a use case that seems to need one.

## Community and private reports

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Anton Soloviev
maintains this project and handles conduct reports at
[anton@praviel.com](mailto:anton@praviel.com).

Use the bug or improvement forms for public issues. For a suspected security
vulnerability or a conduct concern, email the maintainer privately with the
repository name and relevant details. Do not post credentials, personal data,
private logs, or confidential documents in a public issue.
