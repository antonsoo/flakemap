// Feed controlled public result events through the SDK's actual VSTest TRX logger.
// This isolates its nested-row counter convention; it does not run a test adapter.
using System.Reflection;
using Microsoft.VisualStudio.TestPlatform.Extensions.TrxLogger;
using Microsoft.VisualStudio.TestPlatform.ObjectModel;
using Microsoft.VisualStudio.TestPlatform.ObjectModel.Client;
using Microsoft.VisualStudio.TestPlatform.ObjectModel.Logging;

if (args.Length != 1) throw new ArgumentException("Pass a fresh output directory.");
var output = Path.GetFullPath(args[0]);
if (Directory.Exists(output)) throw new IOException("Output directory already exists.");
Directory.CreateDirectory(output);
var events = new CaptureEvents();
var logger = new TrxLogger();
logger.Initialize(events, new Dictionary<string, string?> {
    ["TestRunDirectory"] = output, ["LogFileName"] = "nested.trx"
});
var execution = TestProperty.Register("ExecutionId", "ExecutionId", typeof(Guid),
    TestPropertyAttributes.Hidden, typeof(TestResult));
var parent = TestProperty.Register("ParentExecId", "ParentExecId", typeof(Guid),
    TestPropertyAttributes.Hidden, typeof(TestResult));
var parentId = Guid.NewGuid();
var data = new TestCase("Capture.Example.Data", new Uri("executor://capture"), "capture.dll");
Send(data, TestOutcome.Failed, parentId);
Send(data, TestOutcome.Passed, Guid.NewGuid(), parentId, "Data (passing row)");
Send(data, TestOutcome.Failed, Guid.NewGuid(), parentId, "Data (failing row)");
Send(new TestCase("Capture.Example.Ordinary", new Uri("executor://capture"), "capture.dll"),
    TestOutcome.Passed, Guid.NewGuid());
Send(new TestCase("Capture.Example.Skipped", new Uri("executor://capture"), "capture.dll"),
    TestOutcome.Skipped, Guid.NewGuid());
events.Complete();
Console.WriteLine("Logger: " + typeof(TrxLogger).Assembly.GetName());
Console.WriteLine("Logger informational version: " + typeof(TrxLogger).Assembly
    .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion);

void Send(TestCase test, TestOutcome outcome, Guid id, Guid? parentId = null, string? display = null)
{
    var result = new TestResult(test) { Outcome = outcome, DisplayName = display ?? test.DisplayName };
    result.SetPropertyValue(execution, id);
    if (parentId.HasValue) result.SetPropertyValue(parent, parentId.Value);
    if (outcome == TestOutcome.Failed) result.ErrorMessage = "Controlled counter capture failure";
    events.Result(result);
}

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
