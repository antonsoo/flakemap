using System;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace FlakyDotnet.Tests;

/// <summary>
/// Controlled outcomes for real TRX output. FLAKE_RUN (1..12, set by capture.py)
/// picks each run's behavior, so a capture is reproducible.
/// </summary>
[TestClass]
public class CheckoutTests
{
    private static int Run => int.Parse(Environment.GetEnvironmentVariable("FLAKE_RUN") ?? "1");

    [TestMethod]
    public void TotalIncludesTax() => Assert.AreEqual(108.0, 100.0 * 1.08, 1e-9);

    // Fails on runs 2, 5 and 9: a timing-dependent test, flaky all along.
    [TestMethod]
    public void CacheWarmsBeforeFirstRequest()
    {
        Assert.IsFalse(Run is 2 or 5 or 9, $"cache still cold after 50 ms (run {Run})");
    }

    // Passes on runs 1-6 and fails from run 7 on: a real regression, not a flake.
    [TestMethod]
    public void DiscountCodeIsCaseInsensitive()
    {
        if (Run >= 7) throw new InvalidOperationException("discount code 'save10' not found");
    }

    [DataTestMethod]
    [DataRow("EUR", 2)]
    [DataRow("JPY", 0)]
    public void CurrencyHasMinorUnits(string code, int digits)
    {
        Assert.AreEqual(digits, code == "JPY" ? 0 : 2);
    }

    [TestMethod]
    [Ignore("payment sandbox is down")]
    public void RefundReachesSandbox() { }
}
