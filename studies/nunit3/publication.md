# Native NUnit publication checks

Checked on 2026-10-18. Source and the public static report are published;
the PyPI release is separate and has not been replaced.

| Surface | Revision and evidence |
| --- | --- |
| Parser and shared native-format router | `4d52c1b340082c87ab40cb655310f348075b3022`; [clean package checks](package-verification.json) |
| Final gallery heading and report caption | `6c14af96a106f71a22ee81efdb5b10e0e5288047`; [final installed artifact](final-artifact.json) |
| Pages deployment | `3f907bdaf0c63e2535da0b8c8aaacd5b38c155c9`; [all served files](hosted-bytes.json) |
| Public browser workflows | [Chromium and Firefox receipt](hosted/browser.json), desktop 1200 px and phone 375 px |
| Separate interactive Space | [Hub revision fef6bbc](https://huggingface.co/spaces/antonsoloviev/flakemap/tree/fef6bbcfcc7105c9580b1627d2a8619270d6e409), engine pinned to `6c14af9`; its adapter refuses uncertain native input |

The clean clone at `4d52c1b` passed lint, types and all 430 unit checks, including
Python 3.10.21 with Rich 13.7.0. Its independent wheel installation retained all
32 Python module hashes, all eighteen controlled native outputs and complete
canonical JSON for the two upstream populations (44,724 native case records).
The minimum environment used pytest 9.0.3. These are local checks, not CI claims.

The [152 browser scenarios](browser-regression.json) cover nineteen report
fixtures in Chromium and Firefox, light/dark and 1200/320 px. They preceded the
small final heading/caption correction; their exact artifact hashes are retained.
The final correction passed 34 targeted unit checks and the four public workflows
below. The full 430 checks are scoped to the earlier parser/router revision.

The final rebuilt wheel has the same version number, 0.3.7. All 32 installed
modules match its source. Eighteen controlled JSON outputs still match. A fresh
pip installation from the public `6c14af9` Git revision also matches all eighteen
native controls. The [public source installation receipt](public-source-install.json)
retains its resolved revision and module comparison.

## Public report and download

Every one of the fifteen fresh gallery files, plus the canonical root URL,
matched the final local build through direct public requests without query cache
busters. The deployment advances the existing Pages branch normally.

In each public browser context, the actual served
[NUnit gallery](https://antonsoo.github.io/flakemap/nunit.html) retained eighteen
identities, two unknown outcomes and the suite teardown warning. Keyboard
disclosures exposed the separate generic fixtures and parent setup evidence.
JSON and native XML ZIP downloads worked after disconnecting the browser.
Accessibility, CSP, page errors and horizontal page overflow checks passed.
All four retained screenshots were inspected visually.

The actual [downloaded native archive](hosted/download.zip) contains the exact
retained NUnit 4 report. An independent installation parsed that download and
produced complete JSON equal to the [browser download](hosted/download.json).
Its exit 2 is expected: unknown results and the suite failure remain visible.
The Pages report is precomputed; the separate Space executes Python in the tab.

## Reproduce

```sh
python -m pip install --force-reinstall "flakemap @ git+https://github.com/antonsoo/flakemap.git@6c14af96a106f71a22ee81efdb5b10e0e5288047"
python studies/nunit3/replay.py --python python --output /tmp/nunit-installed --phase after
python studies/nunit3/replay_upstream.py --python python --output /tmp/nunit-upstream --phase after
```

Run the replay scripts from this checkout. They invoke the selected installed
CLI, rather than importing the checkout's package. These captures establish
their documented boundaries, not compatibility with every NUnit extension.
