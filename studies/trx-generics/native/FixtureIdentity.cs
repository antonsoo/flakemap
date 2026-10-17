// Controlled compiled tests: each closed fixture has a constant result.
using NUnit.Framework;
namespace NativePairs;

[TestFixture(typeof(int), typeof(string))]
[TestFixture(typeof(int), typeof(double))]
public class Pair<T, U>
{
    [Test]
    public void Check() => Assert.That(typeof(U), Is.EqualTo(typeof(string)),
        "Controlled second type argument: String passes; Double fails.");
}

[TestFixture(typeof(int))]
public class Single<T>
{
    [Test] public void Check() => Assert.That(typeof(T), Is.EqualTo(typeof(int)));
}

public class Ordinary
{
    [Test] public void Check() => Assert.That(2 + 2, Is.EqualTo(4));
}
