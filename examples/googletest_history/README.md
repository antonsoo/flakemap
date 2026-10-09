# Controlled GoogleTest execution history

Eight actual invocations of the [included C++ fixture](../googletest_project/README.md),
using GoogleTest 1.17.0. `run-01` explicitly enables disabled tests and fails;
`run-02` through `run-08` suppress them. These are controlled reader-validation
inputs, not a production CI study.

Each directory retains unedited `report.xml`, unedited `stdout.txt` and a
sequence-only `meta.json` sidecar. The source archive and report hashes,
build instructions, interpretation and before/after output are documented
in the fixture project. The runtime skip and ordinary pass are controls.
