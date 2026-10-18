// Controlled runner observations, not production reliability measurements.
using System;
using NUnit.Framework;
namespace NativeNUnit;

[NonParallelizable]
public class Outcomes
{
    private int retryCalls;

    [Test] public void Pass() => Assert.That(2 + 2, Is.EqualTo(4));
    [Test] public void Failure() => Assert.Fail("Controlled assertion failure.");
    [Test] public void Error() => throw new InvalidOperationException("Controlled unhandled exception.");
    [Test] public void Inconclusive() => Assert.Inconclusive("Controlled inconclusive result.");
    [Test, Ignore("Controlled ignored test.")] public void Ignored() => Assert.Fail("Must not run.");
    [Test] public void Skipped() => Assert.Ignore("Controlled runtime skip.");
    [Test, Explicit("Controlled explicit test.")] public void Explicit() => Assert.Fail("Must not run without selection.");
    [Test] public void Warning() => Assert.Warn("Controlled warning, not a proven pass.");
    [Test, Retry(2)] public void RetryRecovered() => Assert.That(++retryCalls, Is.EqualTo(2), "Controlled first-attempt failure.");

    [TestCase("a.b", TestName = "row.with.dots(\"a.b\")")]
    [TestCase("x,y", TestName = "row.with.dots(\"x,y\")")]
    public void NamedParameter(string value) => Assert.That(value, Is.Not.Empty);
}

[TestFixture(typeof(int), typeof(string))]
[TestFixture(typeof(int), typeof(double))]
public class Pair<T, U>
{
    [Test] public void Check() => Assert.That(typeof(U), Is.EqualTo(typeof(string)), "Controlled generic fixture outcome.");
}

public class BrokenSetup
{
    [OneTimeSetUp] public void SetUp() => throw new InvalidOperationException("Controlled one-time setup failure.");
    [Test] public void NeverReachedA() => Assert.Fail("Body must not run.");
    [Test] public void NeverReachedB() => Assert.Fail("Body must not run.");
}

public class MultipleAssertions
{
    [Test] public void TwoFailures() => Assert.Multiple(() => {
        Assert.That(1, Is.EqualTo(2), "Controlled first assertion.");
        Assert.That(3, Is.EqualTo(4), "Controlled second assertion.");
    });
}

public class BrokenTeardown
{
    [OneTimeTearDown] public void TearDown() => throw new InvalidOperationException("Controlled one-time teardown failure.");
    [Test] public void PassedBody() => Assert.That(true, Is.True);
}

public class InvalidSignature
{
    [Test] public void MissingArgument(int required) => Assert.Fail("Invalid body must not run.");
}
