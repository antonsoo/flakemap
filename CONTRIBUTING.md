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

For report changes, generate both fixtures and check keyboard operation, narrow
layouts, light/dark themes and offline loading with Chromium:

```bash
uv run flakemap examples/retry_history --html /tmp/flakemap-retry.html
uv run flakemap examples/demo_project/runs --html /tmp/flakemap-history.html
node scripts/check_report.mjs /tmp/flakemap-retry.html /tmp/flakemap-history.html
```

The optional browser script needs an existing Playwright installation and its
Chromium browser. It can resolve a shared installation through `NODE_PATH`.
It makes no external requests. Inspect a screenshot as well as the assertions.
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

flakemap reads JUnit XML and computes statistics; it does not talk to any CI
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
