# Read native NUnit evidence directly

Flakemap's former loader treated NUnit's native `<test-run>` as JUnit XML and
reported zero usable tests. Source now reads this format directly, including
output from NUnit 4 and NUnitLite. It adds no runtime dependency and changes no
statistical formulas. [Publication checks](publication.md) distinguish the source,
installed artifact, public gallery and separate browser workbench from PyPI.

## What a conversion can hide

The controlled [compiled fixture](native/Outcomes.cs) runs with pinned NUnit
3.14.0 and 4.3.2. Each version produces nine actual native reports through the
adapter's `TestOutputXml`, covering 28 case records. These are authored outcomes,
not production reliability data.

| Native observation | Import behavior |
| --- | --- |
| `Pair<Int32,String>` passes; `Pair<Int32,Double>` fails | Separate complete `fullname` identities; their shared open `classname` is not a join key |
| Custom names contain dots, quotes and commas | Literal full names survive; no split inside arguments |
| A one-time setup fails | Two explicitly reported error cases retain `site=Parent` and the setup message |
| A one-time teardown fails after the body passes | Keep the passing case; retain suite/site/failure warnings; invent no failed case |
| `Warning` or `Inconclusive` | Unknown, excluded from pass/fail rates |
| One selected case out of eighteen discovered | One observed execution; discovery count does not imply seventeen missing executions |
| A retry eventually passes, with two assertions but no failed attempt record | One pass; assertion count does not prove retry recovery |

The teardown-only capture is particularly useful: the adapter process exits 0,
its only case is `Passed`, and the native run/suite is `Failed`. The new import
surfaces that suite failure and `--fail-on-incomplete` exits 2. NUnit's result
is preserved without changing the passing body into a fabricated failed trial.

```text
test-run: Failed
+-- suite: Failed, site=TearDown
    +-- PassedBody: Passed
```

Both versions' complete captures are in [captured-v3](captured-v3/capture.json)
and [captured-v4](captured-v4/capture.json). Their manifests retain producer
versions, process exits, raw/retained hashes, counters, exact case attributes
and recorded times. Only host/command/process metadata and local stack paths
are normalized. Neither JUnit conversion nor TRX conversion produces these XMLs.

The installed former CLI finds no tests in all eighteen reports:
[before receipt](before/replay.json). The corrected CLI agrees with independent
XML fullnames/verdicts in all eighteen:
[after receipt](after/replay.json). Complete per-input JSON remains alongside
the receipts. Actual standalone HTML is retained for the complete NUnit 4
capture and its teardown-only case.

## Unchanged upstream suites

This was also checked on two independently maintained projects, built and run
from pinned, unchanged source. These are local executions of historical
releases, not collected production CI history or claims about current upstream
quality.

| Source execution | Native case records | Distinct full names | Important retained boundary |
| --- | ---: | ---: | --- |
| NodaTime 3.2.0, NUnit 4.0.1 | 22,498 | 22,498 | 22,486 passes, one clock-bound failure, eleven skips |
| Math.NET Numerics 5.0.0, NUnitLite 3.13.3 | 22,226 | 22,185 | 1,308 inconclusives and 41 duplicated full names stay excluded |

Every imported identity and per-run count matches an independent XML grouping
oracle: [upstream before](upstream/before.json), [upstream after](upstream/after.json).
All per-suite counters reconcile. Math.NET's 41 duplicate identities become
41 unknown observations, with both records retained, rather than 82 passing
trials. Together with 1,308 inconclusives this makes 1,349 excluded observations.
Generated native IDs do not establish stable identities across runs.

The full native reports are retained as gzip files, about 1.6 MB combined,
with [hashes, counts and provenance](upstream/manifest.json). No case attribute,
outcome, assertion, duration, counter or recorded timestamp was rewritten.
The [upstream reproduction](upstream.md) records source pins, build/run commands,
the historical clock-test failure and the actual runtime.

Ten existing JUnit/TRX histories, spanning 62 identities, retain identical
complete canonical CLI JSON: [control receipt](controls.json).

## Use and reproduce

From a source checkout:

```sh
uv sync --locked
uv run flakemap studies/nunit3/captured-v4/all --html /tmp/nunit-report.html
uv run flakemap studies/nunit3/captured-v4/teardown-filter --json --fail-on-incomplete
```

The last command intentionally exits 2. The [gallery's Native NUnit results
example](https://antonsoo.github.io/flakemap/nunit.html) contains
the same controlled report plus offline JSON and native-input archive downloads.
The hosted report is precomputed; it does not run a Python parser in the browser.

Re-execute the controlled native capture using a .NET 8 SDK:

```sh
uv run python studies/nunit3/capture.py --output /tmp/nunit-v3
uv run python studies/nunit3/capture.py --project studies/nunit3/native4 --output /tmp/nunit-v4
```

The output directories must be new. `--dotnet PATH` selects the SDK; NuGet lock
files pin dependencies. Native clocks and durations will differ on a recapture.
`replay.py --python PYTHON --output DIR --phase after` checks an actual installed
CLI against all retained controlled reports.
`replay_upstream.py` accepts the same arguments and verifies the two compressed
upstream populations without .NET or network access.

## Limits

Only native NUnit 3 result XML is supported; NUnit 2 XML and incomplete progress
fragments are separate dialects. Malformed documents are omitted with a warning.
Unknown, contradictory or missing identities/outcomes are not filled in from
suite totals or assertion counts. No missing retry is reconstructed.

The reader follows the [NUnit result-format contract](https://docs.nunit.org/articles/nunit/technical-notes/usage/Test-Result-XML-Format.html),
with boundaries established by the captures above. Passing these captures does
not establish compatibility with every extension, exporter or future version.
The [format contract](../../docs/formats.md#native-nunit-3-xml) documents exact
normalization and resource limits.
