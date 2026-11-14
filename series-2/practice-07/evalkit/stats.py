"""
Small statistics helpers. Every score in this series is reported as a
distribution or an interval, never as a lone number.
"""

import math
import statistics
from collections import Counter


def summarize(values):
    """n, mean, sample stdev (0.0 for n=1), min and max."""
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def wilson_interval(successes, n, z=1.96):
    """95% Wilson score interval for a proportion.

    It is used instead of the normal approximation because at n=10 and a
    proportion of 0 or 1 the normal approximation collapses to [0, 0] or
    [1, 1]. A flawless 10/10 would then look certain. Wilson keeps the honest
    width: 10/10 is still consistent with ~72%.
    """
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def raw_agreement(a, b):
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length, non-empty label lists")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def cohen_kappa(a, b):
    """Cohen's kappa for two raters over the same items.

    Report it next to raw_agreement, never on its own. When both raters use one
    label almost everywhere, chance agreement is ~1 and kappa reads ~0 however
    good the raters are. Returns None when kappa is undefined (chance agreement
    of exactly 1).
    """
    p_o = raw_agreement(a, b)
    n = len(a)
    ca, cb = Counter(a), Counter(b)
    p_e = sum(ca[label] * cb[label] for label in set(a) | set(b)) / (n * n)
    if p_e == 1:
        return None
    return (p_o - p_e) / (1 - p_e)
