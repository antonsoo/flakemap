# VSTest nested-result counter capture

`Program.cs` feeds five controlled public result events to the actual TRX logger
shipped with the selected .NET SDK: a failed data-driven parent, a passing row,
a failing row, an ordinary pass and a skip. **This exercises the real logger,
not a test adapter or application tests.** The existing `examples/trx_project`
contains the separate, actual MSTest execution controls.

The retained capture used .NET SDK **8.0.425**, logger informational version
**17.11.1-release-24455-02**. Its XML contains three top-level results, two
nested results and counters `total=5 executed=4 passed=2 failed=2`. There is one
`NotExecuted` result while the auxiliary `notExecuted` counter is zero.

With .NET 8 on `PATH`, from the repository root:

```sh
uv run python examples/trx_counters_project/capture.py --output scratch/trx-capture
```

Choose a new output directory. `--dotnet /path/to/dotnet` can select a local SDK
installation. The project references the SDK's own logger and object-model
assemblies via `MSBuildSDKsPath`; there is no NuGet logger replacement. The
script records the SDK version, logger version output, command and exit status.
It removes machine/deployment names and replaces the run's display name before
retaining XML; counters, outcomes and hierarchy remain unchanged. Both original
and retained SHA-256 hashes are in `captures/capture.json`.

The newer upstream logger excludes the data-driven parent from its counters.
That convention is covered by an explicitly transformed copy in the
[replay study](../../studies/trx-counters/README.md), not presented as a second
captured logger version. SDK version changes can therefore change capture totals.
