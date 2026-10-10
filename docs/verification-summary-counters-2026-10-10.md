# Summary-counter verification, 2026-10-10

Verified source commits `f9a664a` (JUnit) and `0eaf533` (TRX), against baseline
`8542d33`. Both repairs make unsupported coverage visible when summary totals
cannot be reconciled with retained results. They preserve the actual result
records and statistical denominators. Nothing was pushed, tagged or published;
the locally built package still carries the existing `0.3.7` version.

## Reproductions and retained evidence

| Evidence | Result |
| --- | --- |
| [JUnit CLI replay](../studies/junit-counters/README.md), 13 scenarios | Six deliberately damaged variants now exit 2; original runner controls keep their behavior. Kubernetes aggregation is also unverified. |
| [TRX CLI replay](../studies/trx-counters/README.md), 21 scenarios | Seven deliberately damaged variants now exit 2; twelve real MSTest reports and the actual nested logger control still reconcile. |
| Complete cached Kubernetes XML corpus | 10,774 files, 1,422,614,273 bytes, 3,486,669 normalized records; before/after input and record hashes match exactly. |
| Installed wheel, Python 3.10.21 / Rich 13.7.0 | All 34 replay receipts equal the committed corrected receipts, including input/statistics hashes and warnings. |
| Installed wheel, Python 3.14.7 / Rich 15.0.0 | The same 34 exact receipt comparisons pass. |
| Additional installed CLI workflows, both environments | 12 each: help/version, 222-run demo, top-10, JSON, Markdown, HTML, new-flake gates, retry report/gate and shared-outcome report. |
| Installed CLI on the cached Kubernetes integration history | 2,162 runs, 136 package identities, 39 flaky and 97 healthy package records; 2,162 counter warnings make individual coverage unverified and the completeness gate exits 2. |

The new-flake gate on the demo correctly exits 0 for the default ten-run window;
its regression started 70 runs ago. Widening the window to 100 exits 1. The
retry gate exits 1 on the retained Surefire retry history. These are expected
behavioral checks, not assumptions that every history should fail a gate.

The [installed receipt](evidence/summary-counters-installed-2026-10-10.json)
records artifact sizes/hashes, import locations under `site-packages`, Python
and Rich versions, commands, exit statuses and output hashes. Both installations
contain only the wheel and its runtime dependencies; neither imports an editable
checkout. Import location was checked with `python -I` outside the source tree.

The [installed Kubernetes CLI receipt](evidence/summary-counters-kubernetes-cli-2026-10-10.json)
retains the command, summary, warning count and JSON/HTML hashes. The actual
standalone HTML is 5,179,598 bytes, including warnings for all 2,162 reports;
the terminal renderer shows its existing first-five-warning preview. This
end-to-end replay took 9.60 seconds on Python 3.14.7 using the warm local cache
(14-vCPU WSL2 Linux, 48 GB RAM). It is a single workflow timing, not a benchmark
claim. Package classifications remain usable; individual test coverage is not
inferred from them.

## Clean source verification

Exported `0eaf533` into a fresh directory using `git archive`, initialized a
local Git directory so Ruff honors the exported `.gitignore`, and installed
dependencies from scratch. No existing virtual environment was copied.

| Environment | Result |
| --- | --- |
| Working checkout, Python 3.12.12, locked dependencies | Ruff lint/format and mypy pass; 348 tests pass. |
| Clean export, Python 3.14.7, locked dependencies | Ruff lint/format and mypy pass; 348 tests pass. |
| Clean export, Python 3.10.21, minimum direct dependencies | 348 tests pass with pytest 9.0.3, pytest-randomly 3.15.0 and Rich 13.7.0. |
| `uv build` in the clean export | Source distribution builds; wheel builds from that source distribution. |
| `npm ci --ignore-scripts --no-audit --no-fund` | Installs the locked browser-check dependencies. |
| `.venv/bin/python scripts/build_demo_site.py` | Builds five local pages under `site/`, including the existing historical Kubernetes report. |

Use explicit interpreter paths for the cross-version checks: `.python-version`
pins 3.12, so an unqualified `uv run` after selecting 3.14 would select 3.12 again.
The minimum-dependency environment belongs in an ignored directory or outside
the export; generated activation scripts are not project source to lint.

Core reproduction commands, in the fresh source directory:

```sh
uv sync --locked --python 3.14.7
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest -q
uv build
uv venv --python 3.10.21 .venv-minimums
uv pip install --python .venv-minimums --resolution lowest-direct -e . --group dev
.venv-minimums/bin/pytest -q
```

For installed verification, create a separate environment and install the wheel
under `dist/`; explicitly pin `rich==13.7.0` for the minimum runtime check.
Use that environment's Python to run both study `replay.py` scripts with a new
`--output` directory and `--check`. Their `results.json` must equal each study's
committed `results/after.json`.

## Browser checks and limits

The clean export also ran `.venv/bin/python scripts/browser_fixtures.py` and
`npm run test:browser`: **104 offline scenarios** passed across thirteen report
fixtures, Chromium/Firefox, 320/1200 pixels and light/dark schemes. Checks include
keyboard interaction, downloadable evidence, escaping, CSP and axe accessibility
rules; all recorded accessibility violations, page errors, CSP violations and
network requests are zero. The
[browser receipt](evidence/summary-counters-browser-2026-10-10.json) includes
browser/tool versions and hashes of the rendered fixtures. The committed
Kubernetes gallery page remains a historical rendering, explicitly identified
as such in the counter study.

The two counter studies each checked 24 offline views across Chromium/Firefox,
375/1200 pixels and light/dark schemes. Warning expansion works by keyboard;
reported counts match CLI JSON. There are no page errors, external requests or
horizontal page overflow. The four committed desktop/phone screenshots were
opened and inspected: the existing warning panel wraps the declared and retained
counts without hiding the remaining observations.

The capture programs and their provenance hashes were checked. The nested TRX
fixture exercises the actual SDK logger using controlled public events; it is
not a second MSTest execution history. The newer data-parent-excluding convention
is source-verified and tested with transformed counters, not claimed as another
captured logger version.

Matching counters cannot prove that all original tests were exported. Missing
counters remain optional. Updating counters while removing results can evade
the check. Some valid producers aggregate records or use counters that cannot be
recovered from their XML; those reports remain usable but their individual-test
coverage is unverified. The Kubernetes collector was not rerun: its existing
cache was replayed in full, with both input and normalized-record hashes retained.

No gallery page, registry package or remote repository was updated. The site
build command is `python scripts/build_demo_site.py`; its output is `site/`.

Suggested repository description: "Inspect JUnit and TRX histories for flaky
tests, hidden retries and incomplete evidence."
Suggested topics: `testing`, `junit`, `trx`, `flaky-tests`, `ci`, `python`.
