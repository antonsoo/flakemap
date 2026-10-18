# Upstream source executions

The retained gzip reports come from actual local executions of two unchanged
historical releases. The [manifest](upstream/manifest.json) pins their resolved
source commits, raw and normalized report hashes, original case populations and
compressed bytes. Both tracked source trees were clean after execution.

| Project | Source tag | Native producer | Target / actual runtime |
| --- | --- | --- | --- |
| [NodaTime](https://github.com/nodatime/nodatime/tree/3.2.0) | `3.2.0` | NUnit 4.0.1, NUnit3TestAdapter 4.5.0, native `TestOutputXml` | net8.0 / .NET 8.0.31 |
| [Math.NET Numerics](https://github.com/mathnet/mathnet-numerics/tree/v5.0.0) | `v5.0.0` | NUnitLite 3.13.3, native `--result` | net6.0 / .NET 8.0.31 via explicit major roll-forward |

The installed SDK was 8.0.425 on Ubuntu 24.04 under WSL2, 14 logical CPUs.
Math.NET's own default build configuration is Release; NodaTime's is Debug.
The commands were invoked from the parent cache directory, outside each source
tree, so the available SDK was selected rather than Math.NET's SDK 6 global pin.
No upstream source or project file was edited. `NuGetAudit=false` only disables
the dependency audit during these historical builds; the resulting packages
and test assemblies are not product runtime dependencies.

To reproduce, check out the exact manifest revisions and run from their parent
directory. `dotnet` below denotes the selected .NET 8 SDK binary:

```sh
dotnet build nodatime/src/NodaTime.Test/NodaTime.Test.csproj -f net8.0 -p:NuGetAudit=false -v q
dotnet test nodatime/src/NodaTime.Test/NodaTime.Test.csproj --no-build -f net8.0 -- NUnit.TestOutputXml=/tmp/nodatime-native-results
dotnet build mathnet-numerics/src/Numerics.Tests/Numerics.Tests.csproj -f net6.0 -p:NuGetAudit=false -v q
DOTNET_ROLL_FORWARD=Major dotnet mathnet-numerics/src/Numerics.Tests/bin/Release/net6.0/MathNet.Numerics.Tests.dll --result=/tmp/mathnet-native-results.xml --labels=Off
```

NodaTime's process exited 1: `SystemClockTest.Sanity` in this historical release
requires the clock to be before 1 January 2025. This execution took place on
18 October 2026. The failure is retained, rather than filtering the test or
changing the machine clock. Its native XML contains 22,498 cases, while the
adapter's console summary counts 22,493; the import oracle uses the actual XML.
The remaining XML outcomes are 22,486 passes and eleven skips.

Math.NET's NUnitLite process exited 0 with an overall console result of Warning.
Its native root is `Skipped`, label `Ignored`, and contains 20,873 passes,
1,308 inconclusives and 45 skips. Some theory combinations are explicitly
inconclusive (for example incompatible matrix dimensions), so they are not
converted to passing evidence. Forty-one native full names each appear twice,
including abbreviated array arguments such as `[0, 1, 2, 3, 4, ...]`.
Those ambiguous identities stay excluded. This execution uses the managed
linear-algebra, Fourier and sparse-solver providers recorded in native output.

`retain_upstream.py` takes the two checkout/report paths and writes portable,
deterministically compressed XML plus its manifest. It verifies every case
attribute before/after and permits only host metadata and local stack-path
normalization. It never changes counts, verdicts, full names, assertions,
durations or clocks. A host token occurring inside an unrelated literal test
name is preserved; identity text is never redacted by substring guessing.

To replay the retained populations through an installed Flakemap without .NET:

```sh
python studies/nunit3/replay_upstream.py --python /path/to/consumer/bin/python --output /tmp/nunit-upstream-replay --phase after
```

The reports are derived from Apache-2.0 NodaTime and MIT Math.NET material.
Their [license](upstream/NODATIME-LICENSE.txt), [notice](upstream/NODATIME-NOTICE.txt)
and [Math.NET license](upstream/MATHNET-LICENSE.txt) are retained. These two
executions establish native import accounting on these inputs, rather than
current upstream test quality, general runner compatibility or production
flakiness rates.
