# Controlled pytest counter capture

This small project intentionally produces a pass, an assertion failure, a setup
error and a skip. The complex capture adds teardown errors and subtests. It
exercises pytest's actual JUnit writer; these are controlled outcomes, not
production failures or a flakiness benchmark.

From the repository root:

```sh
uv sync --locked
uv run python examples/junit_counters_project/capture.py
```

Both pytest invocations exit 1, as expected. The capture script checks that exit,
retains console output and XML, removes the machine's `hostname` attribute,
makes repository paths in diagnostic text relative, and records raw/retained
hashes plus versions in `captures/capture.json`. Outcomes and counters are unchanged.
The retained capture used pytest 9.1.1 and Python 3.12.12.

`basic.xml` has four testcase records and matching counters. `complex.xml` has
eight records, while pytest declares eleven tests and five failures. Several
subtest failures occupy one testcase; a call failure and teardown error share a
test identifier across two records. Flakemap preserves the records and does not
invent eleven separately identifiable tests. See
[the replay and limits](../../studies/junit-counters/README.md).
