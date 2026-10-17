// Feed controlled public result events through the SDK's actual VSTest TRX logger.
// These are authored hierarchy controls, not a test-adapter or production capture.
using System.Reflection;
using Microsoft.VisualStudio.TestPlatform.Extensions.TrxLogger;
using Microsoft.VisualStudio.TestPlatform.ObjectModel;
using Microsoft.VisualStudio.TestPlatform.ObjectModel.Client;
using Microsoft.VisualStudio.TestPlatform.ObjectModel.Logging;

if (args.Length != 1) throw new ArgumentException("Pass a fresh output directory.");
var output = Path.GetFullPath(args[0]);
if (Directory.Exists(output)) throw new IOException("Output directory already exists.");
Directory.CreateDirectory(output);
var execution = TestProperty.Register("ExecutionId", "ExecutionId", typeof(Guid),
    TestPropertyAttributes.Hidden, typeof(TestResult));
var parent = TestProperty.Register("ParentExecId", "ParentExecId", typeof(Guid),
    TestPropertyAttributes.Hidden, typeof(TestResult));
foreach (var scenario in new[] {
    "passed-parent-failed-row", "failed-parent-failed-row",
    "passed-parent-passing-rows", "passed-parent-skipped-row",
    "skipped-parent-failed-row", "grandchild-events-top-level",
    "failed-parent-passing-rows"
}) {
    var folder = Path.Combine(output, scenario);
    Directory.CreateDirectory(folder);
    var events = new CaptureEvents();
    var logger = new TrxLogger();
    logger.Initialize(events, new Dictionary<string, string?> {
        ["TestRunDirectory"] = folder, ["LogFileName"] = "nested.trx"
    });
    var parentId = Guid.NewGuid();
    var data = new TestCase("Capture.Example.Data", new Uri("executor://capture"), "capture.dll");
    var outcome = scenario.StartsWith("failed-") ? TestOutcome.Failed
        : scenario.StartsWith("skipped-") ? TestOutcome.Skipped : TestOutcome.Passed;
    Send(data, outcome, parentId);
    if (scenario == "grandchild-events-top-level") {
        var branch = Guid.NewGuid();
        Send(data, TestOutcome.Passed, branch, parentId, "Data (branch)");
        Send(data, TestOutcome.Passed, Guid.NewGuid(), branch, "Data (passing leaf)");
        Send(data, TestOutcome.Failed, Guid.NewGuid(), branch, "Data (failing leaf)");
    } else {
        Send(data, TestOutcome.Passed, Guid.NewGuid(), parentId, "Data (passing row)");
        var rowOutcome = scenario.Contains("passing-rows") ? TestOutcome.Passed
            : scenario.Contains("skipped-row") ? TestOutcome.Skipped : TestOutcome.Failed;
        Send(data, rowOutcome, Guid.NewGuid(), parentId, "Data (second row)");
    }
    Send(new TestCase("Capture.Example.Ordinary", new Uri("executor://capture"), "capture.dll"),
        TestOutcome.Passed, Guid.NewGuid());
    Send(new TestCase("Capture.Example.Skipped", new Uri("executor://capture"), "capture.dll"),
        TestOutcome.Skipped, Guid.NewGuid());
    events.Complete();

    void Send(TestCase test, TestOutcome outcome, Guid id, Guid? parentId = null, string? display = null)
    {
        var result = new TestResult(test) { Outcome = outcome, DisplayName = display ?? test.DisplayName };
        result.SetPropertyValue(execution, id);
        if (parentId.HasValue) result.SetPropertyValue(parent, parentId.Value);
        if (outcome == TestOutcome.Failed) result.ErrorMessage = "Controlled nested row failure";
        events.Result(result);
    }
}
Console.WriteLine("Logger: " + typeof(TrxLogger).Assembly.GetName());
Console.WriteLine("Logger informational version: " + typeof(TrxLogger).Assembly
    .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion);

#pragma warning disable CS0067 // The logger only subscribes to result/message/completion events.
sealed class CaptureEvents : TestLoggerEvents
{
    public override event EventHandler<TestRunMessageEventArgs>? TestRunMessage;
    public override event EventHandler<TestRunStartEventArgs>? TestRunStart;
    public override event EventHandler<TestResultEventArgs>? TestResult;
    public override event EventHandler<TestRunCompleteEventArgs>? TestRunComplete;
    public override event EventHandler<DiscoveryStartEventArgs>? DiscoveryStart;
    public override event EventHandler<TestRunMessageEventArgs>? DiscoveryMessage;
    public override event EventHandler<DiscoveredTestsEventArgs>? DiscoveredTests;
    public override event EventHandler<DiscoveryCompleteEventArgs>? DiscoveryComplete;
    public void Result(TestResult result) => TestResult?.Invoke(this, new TestResultEventArgs(result));
    public void Complete() => TestRunComplete?.Invoke(this,
        new TestRunCompleteEventArgs(null, false, false, null, null, null, TimeSpan.Zero));
}
