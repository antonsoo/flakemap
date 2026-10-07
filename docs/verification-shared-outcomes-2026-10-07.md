# Shared-outcome investigation: local verification

Implementation `6499e5887b22edbe865a2fabcb2f5a9c1a8b62d4` was verified in a
fresh detached checkout. It is local and unreleased. No push, package publication
or Pages deployment was performed; the package version remains 0.3.7.

The new report answers a specific triage question: which tests have the same
observed outcome history? It retains source evidence, distinguishes retries and
coverage, and does not assert a common cause. See [rules and limits](shared-outcomes.md).

| Verification | Observed result |
| --- | --- |
| Twelve real pytest runs against a controlled loopback service | One cohort of three endpoint tests, failures in 04/05/10, nine affected test-runs |
| Independent assertion and optional endpoint | Independent failure in 07 excluded from that cohort; skipped/absent coverage does not match |
| Clean-checkout recapture | All 71 reported outcomes and all 46 HTTP requests match the committed capture's outcome/request manifest |
| Python 3.10.21 with lowest direct dependencies; 3.12.12 and 3.14.7 with locked dependencies | 261 tests passed in each environment |
| Independent dense-history oracle | Agrees with sparse grouping over 160 seeded histories, including replicas, errors, retries, gaps and unknowns |
| Ruff lint and format; strict mypy | Passed; 59 formatted Python files and 25 typed source files |
| Wheel built from source distribution, installed outside checkout on Python 3.10/Rich 13.7 | Shared groups and source ordinals match original XML; Markdown, terminal and offline HTML downloads retain the evidence |
| Existing CI exit policies in installed wheel | Shared capture exits 0; explicit recovered-retry gate exits 1; incomplete-input gate exits 2 |
| Clean Node 24.21.0 installation | Three locked development packages installed; npm audit reported zero vulnerabilities |
| Chromium and Firefox, 320/1200px, light/dark, ten report/gallery fixtures | 80 offline browser scenarios passed |
| Accessibility, CSP, page errors, external requests | Zero findings/errors/violations/HTTP(S) requests in those scenarios |
| Working versus clean generated output | All 20 HTML/JSON files byte-identical |

The browser checks use actual standalone `file://` reports. They open and close
native disclosure controls with the keyboard, follow a member link to its actual
test row, scroll the evidence table on phones, and download the full JSON in both
engines. Gallery checks navigate between reports and download their analyses.
All panels are opened before accessibility and layout checks.

A separate labeled synthetic fixture has 22 cohorts, 69 tests and 26 runs. The
largest cohort has 25 members and 625 affected observations. HTML shows 20
cohorts, 20 member links and 40 affected records per cohort; the downloaded JSON
retains all groups and records. Long hostile text remains inert, and run-label
and member omissions are stated. This is a check of the new inspector's bounds,
not a claim that the pre-existing whole report has a global size bound.

A synthetic scale probe analyzed 80,000 observations from 20,000 tests/four runs
in approximately 0.40 seconds locally, with process peak RSS approximately
59 MiB. It produced one 20,000-member cohort. This measurement includes native
analysis only, not HTML rendering; it is not a performance guarantee.

Actual browser work found that a relative JSON file link did not download when
opened offline in Chromium. The gallery now embeds the JSON in its download
link, and both engines verify its content. The keyboard check also uses real Tab
navigation after pointer-triggered downloads: Firefox does not always establish
keyboard focus modality from a programmatic focus followed by Enter alone.

Screenshots were inspected, including the horizontal evidence table on a phone:

- [Desktop gallery and shared-failure evidence](assets/shared-outcomes-desktop-2026-10-07.png)
- [Phone inspector, dark theme](assets/shared-outcomes-mobile-2026-10-07.png)

The [machine evidence](verification-shared-outcomes-2026-10-07.json) records
capture outcomes, package hashes, generated artifact hashes and environment
details. [Browser evidence](browser-shared-outcomes-2026-10-07.json) records all
80 scenarios. The controlled service failures are not production incident data.

Reproduce native and browser checks with the commands in
[Contributing](../CONTRIBUTING.md). Build the local example gallery with
`uv run python scripts/build_demo_site.py`. Recapture the HTTP example using
`uv run python examples/cofailure_project/capture.py scratch/new-capture`.
