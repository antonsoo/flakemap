"""Null distribution of the change-point statistic, behind MIN_STATISTIC.

For each history length and constant failure rate, simulates series with no
change point and prints percentiles of the maximized likelihood-ratio
statistic (before the rate-shift and significance thresholds are applied), so
the threshold in `flakemap/stats/changepoint.py` can be checked or re-derived:

    uv run python scripts/changepoint_null.py
"""

from __future__ import annotations

import random

from flakemap.stats.changepoint import MIN_SEGMENT, MIN_STATISTIC, _bernoulli_loglik


def max_statistic(series: list[int]) -> float:
    n, total = len(series), sum(series)
    ll_one = _bernoulli_loglik(total, n)
    best, running = 0.0, 0
    for k in range(1, n):
        running += series[k - 1]
        if k < MIN_SEGMENT or n - k < MIN_SEGMENT:
            continue
        ll_two = _bernoulli_loglik(running, k) + _bernoulli_loglik(total - running, n - k)
        best = max(best, 2 * (ll_two - ll_one))
    return best


def main() -> None:
    rng = random.Random(7)
    print(f"MIN_STATISTIC = {MIN_STATISTIC}")
    print(f"{'runs':>5} {'rate':>5} {'95th':>7} {'99th':>7} {'>= MIN':>7}")
    for n in (20, 50, 100, 222, 500, 1000):
        trials = 3000 if n <= 222 else 1000
        for p in (0.05, 0.2, 0.5):
            stats = sorted(
                max_statistic([1 if rng.random() < p else 0 for _ in range(n)])
                for _ in range(trials)
            )
            exceed = sum(s >= MIN_STATISTIC for s in stats) / trials
            q95 = stats[int(0.95 * (trials - 1))]
            q99 = stats[int(0.99 * (trials - 1))]
            print(f"{n:>5} {p:>5} {q95:>7.2f} {q99:>7.2f} {exceed:>7.1%}")


if __name__ == "__main__":
    main()
