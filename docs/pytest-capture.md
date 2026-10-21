# Keep the failed attempts behind a green pytest result

Pytest's ordinary `--junitxml` output does not preserve the failure details of
pytest-rerunfailures' intermediate attempts. The current native replay produces
31 testcase elements for 15 logical tests, with suite `tests="19"`. Repeated
names alone cannot establish which records were retries. Flakemap keeps those
ordinary records excluded instead of guessing.

The source checkout provides a companion reporter that observes the evidence
while pytest runs. Install the verified revision in the environment that runs
your tests. `--force-reinstall` replaces an existing registry 0.3.7 installation;
this source revision still declares that version.

```sh
python -m pip install --force-reinstall \
  'flakemap[pytest] @ git+https://github.com/antonsoo/flakemap.git@bb6a48e3259dffac29d4ac609934681f2a40b386' \
  'pytest-rerunfailures>=16.7'
pytest -p flakemap.pytest_plugin --reruns 2 \
  --flakemap-xml=flakemap-history/run-001.xml tests/
flakemap flakemap-history --html retries.html --fail-on-retry --fail-on-incomplete
```

The last command exits **1** when an observed test recovered after failed
attempts, and **2** when the capture is incomplete. It still writes the report.
Final test failures retain their separate meaning in the report; these flags
are not a replacement for pytest's own exit status.

Give each CI invocation or matrix job its own report path. Analyze only the
companion history. If CI also needs ordinary JUnit, write it outside that history:

```sh
pytest -p flakemap.pytest_plugin --reruns 2 -n 2 \
  --junitxml=ci-junit.xml --flakemap-xml=flakemap-history/run-002.xml tests/
```

The second command additionally needs `pytest-xdist`. Loading the plugin does
not enable retries; `--reruns` belongs to pytest-rerunfailures. There is no
automatic pytest entry point. Base Flakemap installations still need only Rich.
The reporter is not in the tested PyPI 0.3.7 release. The source upgrade and
installed runtime are verified separately in the [study](../studies/pytest-capture/README.md).

## What the report establishes

```text
One pytest invocation
  test_recovered_call
    attempt 1: setup passed -> call failed -> teardown passed
    attempt 2: setup passed -> call failed -> teardown passed
    attempt 3: setup passed -> call passed -> teardown passed
                     |
                     v
  One passing history observation, two explicit failed attempts
```

The reporter receives original phase outcomes before the retry plugin changes
`failed` to `rerun`. Retry indices and those outcomes travel through xdist's
report serialization. Only the controller writes XML. Setup, call and teardown
must form a complete, ordered sequence, and every intermediate attempt must
contain an explicit failed rerun. A call failure and teardown error in the same
attempt retain both traces in one marker and count as **one** failed attempt.

Case names preserve complete pytest node IDs, including parameter IDs. Keep
the same pytest collection root when accumulating a history. Ordinary JUnit's
dotted names are a different identity convention; do not combine the two report
streams as if they were independent tests or runs.

The report retains per-phase indices, original/reported outcomes and durations
in XML properties. Failed phase traces are retained up to 16,000 characters
each, with explicit truncation. The testcase duration sums measured phases
across attempts, excluding retry sleep delays; it does not measure wall-clock
retry cost. Existing HTML and JSON expose the failed-attempt messages, original
XML locations, final outcomes and reported durations.

## Incomplete execution stays visible

Collection failure, interruption, an early `-x` stop with selected tests left,
missing/duplicate phases, worker crashes and retries ending in a skip produce
an incomplete capture. The report retains completed outcomes and an unknown
capture record where needed. It does not manufacture outcomes for unexecuted
tests. At session start an atomic incomplete report replaces any stale file;
force-killing pytest leaves that marker rather than an older successful report.
Final writing also uses atomic replacement.

Plain skips and expected failures remain skipped. A non-strict unexpected pass
remains passed; a strict unexpected pass remains failed. Pytest's exit code is
unchanged, including pytest-rerunfailures' `--fail-on-flaky` code 7.

Subtests and other nonstandard report protocols are currently excluded as
unknown. The retained native checks use pytest 9.1.1 and pytest-rerunfailures
16.7; the minimum-version replay uses Python 3.10 and pytest 8.2.0 with the same
retry plugin. Older retry plugins that omit intermediate teardown reports do
not provide the complete sequences required here. No report can restore
failure evidence already omitted from a past JUnit export.

[Native outputs, independent execution checks and limitations](../studies/pytest-capture/README.md).
