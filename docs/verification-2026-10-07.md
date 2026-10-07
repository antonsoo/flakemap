# Local verification, 2026-10-07

Verified implementation `789c612` in a fresh detached checkout. These changes
are local and unreleased; no push, package publication or Pages deployment was
performed. The package version remains 0.3.7.

| Environment or check | Result |
| --- | --- |
| Python 3.10.21, lowest direct dependencies including Rich 13.7.0 | 239 passed |
| Python 3.12.12, locked dependencies | 239 passed |
| Python 3.14.7, locked dependencies | 239 passed |
| Ruff lint, format, strict mypy | Passed; 23 source files typechecked |
| Source distribution and wheel | Built from the clean checkout |
| Standalone wheel on Python 3.10.21, outside the checkout | Real CLI histories, JSON, HTML, gate and source-preservation checks passed |
| Node 24.21.0 clean `npm ci` | Passed; audit reported no vulnerabilities |
| Chromium and Firefox, offline, 320/1200px, light/dark, four report fixtures | 32 scenarios passed |
| Axe WCAG A/AA and best-practice checks, all detail panels open | No findings in those scenarios |
| Browser page errors, CSP violations, HTTP(S) requests | Zero |
| Clean vs working-checkout generated report hashes | Identical for all four fixtures |

The wheel smoke checked captured Surefire (1 run, 6 tests), pytest (222 runs,
12 tests) and MSTest (12 runs, 6 tests) histories. A separately labeled synthetic
fixture checked truncation, inert XML/HTML examples, unknown TRX outcomes, and
two timings separated by an absent observation. A 50-run generated history
verified that a change at run 10 ages to 40 runs even when the test is absent
in the last 30 runs; the 10-run new-flake gate exits 0 and an explicit 40-run
gate exits 1. Incomplete input takes precedence over retry gates with exit 2,
while JSON and HTML retain the evidence.

Native regressions cover strict TimeSpan bounds, duplicate definitions,
namespace handling, nine encodings across both report formats, replacement
identity ambiguity, XML comments/CDATA, Expat events deferred until EOF,
bounded files and nesting, metadata ambiguity, and failed atomic exports.
An independent Decimal least-squares calculation checks irregular timing
positions at scales from `1e-300` to `1e300`.

Browser checks use the generated standalone files directly, with networking
disabled. They exercise keyboard expansion/collapse and visible focus, source
locations, unknown outcomes, complete names on narrow screens, escaping,
layout and accessibility. Screenshots were inspected:

- [Phone, light](assets/integrity-mobile-2026-10-07.png)
- [Desktop, dark](assets/integrity-desktop-2026-10-07.png)

Reproduce native checks with `uv sync --locked`, `uv run pytest -q`,
`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and
`uv build`. See [Contributing](../CONTRIBUTING.md) for browser commands.
[Machine evidence and artifact hashes](verification-2026-10-07.json) and
[browser results](browser-verification-2026-10-07.json) record the environments.

The synthetic fixtures demonstrate boundary behavior; they are not runner
compatibility captures. The real captures retain their documented provenance.
Per-file limits do not bound the size of a whole history, and warning-free input
does not prove all CI artifacts were collected. Statistical classifications
remain descriptive heuristics, not proof of a root cause or a calibrated
probability that a test is flaky.
