# Twelve real TRX runs

A controlled MSTest project for checking flakemap against actual
`dotnet test --logger trx` output. It is not a production benchmark: the
`FLAKE_RUN` variable scripts each run's behavior, so the capture is
reproducible.

```bash
uv run python examples/trx_project/capture.py
uv run flakemap examples/trx_history
```

`capture.py` builds the project, runs `dotnet test` twelve times with
`FLAKE_RUN=1..12`, and checks every run's outcomes before keeping its TRX file.
It replaces the machine name, user name and local paths (in attributes and
stack traces), and leaves outcomes, messages, durations and each run's own
`<Times start>` untouched. No metadata sidecar is written, so flakemap orders
the runs by those start times (metadata source `report`).

Captured on 2026-09-30 with the .NET 8 SDK 8.0.425, MSTest 3.6.1 and
Microsoft.NET.Test.Sdk 17.11.1 on Linux/WSL2. The .NET SDK is needed only to
regenerate the fixture, not to run flakemap or its tests.

| Test | Scripted behavior | Flakemap |
|---|---|---|
| `CacheWarmsBeforeFirstRequest` | fails on runs 2, 5 and 9 | flaky, 25% final failures |
| `DiscountCodeIsCaseInsensitive` | passes on runs 1-6, throws from run 7 on | broken, change point at `run-07` |
| `CurrencyHasMinorUnits ("EUR",2)` and `("JPY",0)` | data rows, always pass | healthy, as two separate tests |
| `TotalIncludesTax` | always passes | healthy |
| `RefundReachesSandbox` | `[Ignore]` | insufficient data: no executed outcomes |

What the real output showed, and the parser follows:

- MSTest writes the **short** test name (`CacheWarmsBeforeFirstRequest`), with a
  data row's arguments after a space (`CurrencyHasMinorUnits ("JPY",0)`); the
  class comes from `<TestDefinitions>`.
- An exception thrown by a test is `outcome="Failed"`, not `Error`, and its
  message reads `Test method ... threw exception:` with the exception on the
  next line. Flakemap joins the two lines for message clustering.
- An ignored test is `outcome="NotExecuted"` and carries the ignore reason as
  its message.
- `<Times start>` has seven fractional digits and the local UTC offset.
