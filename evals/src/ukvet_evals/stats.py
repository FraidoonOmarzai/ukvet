"""Small statistics helpers: proportions with Wilson intervals, Cohen's kappa."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Rate:
    """k successes out of n, with a 95% Wilson score interval."""

    k: int
    n: int

    @property
    def value(self) -> float | None:
        return None if self.n == 0 else self.k / self.n

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson(self.k, self.n)

    def to_dict(self) -> dict[str, object]:
        ci = self.interval
        return {
            "k": self.k,
            "n": self.n,
            "rate": None if self.value is None else round(self.value, 4),
            "ci95": None if ci is None else [round(ci[0], 4), round(ci[1], 4)],
        }

    def pct(self) -> str:
        return "n/a" if self.value is None else f"{self.value:.1%}"

    def pct_ci(self) -> str:
        ci = self.interval
        if ci is None or self.value is None:
            return "n/a"
        return f"{self.value:.1%} [{ci[0]:.1%}, {ci[1]:.1%}]"


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; None when n == 0."""
    if n <= 0:
        return None
    if not 0 <= k <= n:
        raise ValueError("k must be between 0 and n")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Agreement between two labellers beyond chance. None if undefined (n=0 or no variation)."""
    if len(a) != len(b):
        raise ValueError("label lists must be the same length")
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    labels = set(a) | set(b)
    expected = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    if math.isclose(expected, 1.0):
        return None
    return (observed - expected) / (1 - expected)
