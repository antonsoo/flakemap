# Source publication verification, 2026-10-10

Verified a fresh archive of `0022933735841f9afbc2da5a1420f6a59cafb7af`
before pushing the execution-evidence, shared-outcome and incomplete-input
changes to `main`. This does not publish a new PyPI package.

The consequential check used a newly compiled GoogleTest 1.17.0 executable,
not a replay of expected Flakemap output. The release archive's SHA-256 was
`65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c`.
[`capture.py`](../examples/googletest_project/capture.py) ran eight history
invocations and one fail-fast control. The [raw XML and stdout](evidence/source-2026-10-10/fresh-googletest.zip)
are retained, including reporter hashes; only the capture manifest's file
paths were made relative.

An independently installed wheel on Python 3.10.21 with Rich 13.7.0 agreed
with the execution markers in every raw XML record:

| Test | Pass | Fail | Skip |
| --- | ---: | ---: | ---: |
| `Execution.AlwaysPasses` | 8 | 0 | 0 |
| `Execution.ZAfterTrigger` | 8 | 0 | 0 |
| `Execution.DISABLED_FailsWhenEnabled` | 0 | 1 | 7 |
| `DISABLED_UnavailableDevice.NeedsHardware` | 0 | 1 | 7 |
| `Execution.RuntimeSkip` | 0 | 0 | 8 |

The two disabled histories stay insufficient: seven non-executions do not
become seven passes. Unknown and contradictory markers have no failure-rate
denominator and `--fail-on-incomplete` returns 2. The fail-fast control agrees
with the retained reporter evidence. Nine existing CLI workflows, including
the retry gate, also passed. See the [installed-wheel record](evidence/source-2026-10-10/installed-wheel.json)
and [fresh history report](evidence/source-2026-10-10/fresh-history-report.json).

On Python 3.14.7, a locked clean install passed Ruff, formatting, mypy and
307 tests; the sdist and wheel built. On Node 26.7.0/npm 12.0.1, `npm ci`
and all [104 offline Chromium/Firefox scenarios](evidence/source-2026-10-10/browser.json)
passed. Desktop execution evidence and the 320-pixel dark incomplete-input
report were opened and visually inspected. The [five-page gallery build](evidence/source-2026-10-10/build.json)
retains reports from actual runner captures, including the Kubernetes census.

Reproduction commands are in the [GoogleTest example](../examples/googletest_project/README.md)
and [contributing guide](../CONTRIBUTING.md). Other GoogleTest versions remain
unverified. This record establishes source and local artifact behavior;
it does not assert a registry release or successful Pages deployment.
