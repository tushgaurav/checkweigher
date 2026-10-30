"""KPI maths on summed sufficient statistics.

Every input is a SUM over the selected rows of `weighing_15m` (counts, Σw, Σw², ...),
so plant / shift / multi-machine figures are exactly volume-weighted - percentages
are never averaged.

Definitions (to be confirmed with the client; change them here only):

* Rates (overweight %, underweight %, feeding error %, ...) are per product judged
  (``n``, including feeding errors that have no weight).
* EGA % (Excess Give-Away) = Σ(weight − target) over accepted (OK) packs
  ÷ Σ target of those packs × 100.
* SD is the sample standard deviation of individual weights. When several
  products are mixed, ``sd_vs_target`` (SD of weight − target) is the meaningful one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from itertools import pairwise
from typing import Any

SUM_COLUMNS = (
    "n", "n_weighed", "n_ok", "n_hh", "n_hi", "n_lo", "n_ll", "n_td", "n_us", "n_md", "n_ext",
    "sum_w", "sum_w2", "n_dev", "sum_dev", "sum_dev2", "sum_target", "sum_w_ok", "n_dev_ok", "sum_dev_ok",
    "sum_target_ok",
)
SUM_SQL = ", ".join(f"coalesce(sum({c}), 0) AS {c}" for c in SUM_COLUMNS) + ", min(min_w) AS min_w, max(max_w) AS max_w"


@dataclass
class Sums:
    n: float = 0
    n_weighed: float = 0
    n_ok: float = 0
    n_hh: float = 0
    n_hi: float = 0
    n_lo: float = 0
    n_ll: float = 0
    n_td: float = 0
    n_us: float = 0
    n_md: float = 0
    n_ext: float = 0
    sum_w: float = 0
    sum_w2: float = 0
    n_dev: float = 0
    sum_dev: float = 0
    sum_dev2: float = 0
    sum_target: float = 0
    sum_w_ok: float = 0
    n_dev_ok: float = 0
    sum_dev_ok: float = 0
    sum_target_ok: float = 0
    min_w: float | None = None
    max_w: float | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Sums:
        nullable = ("min_w", "max_w")
        return cls(**{
            f.name: float(v) if (v := row.get(f.name)) is not None else (None if f.name in nullable else 0.0)
            for f in fields(cls)
        })


def _ratio(a: float, b: float, scale: float = 1.0) -> float | None:
    return a / b * scale if b else None


def _sd(n: float, s: float, s2: float) -> float | None:
    if n < 2:
        return None
    return math.sqrt(max(0.0, (s2 - s * s / n) / (n - 1)))


def compute_kpis(s: Sums) -> dict[str, Any]:
    over, under, feed = s.n_hh + s.n_hi, s.n_lo + s.n_ll, s.n_td + s.n_us
    return {
        "total": int(s.n),
        "weighed": int(s.n_weighed),
        "passed": int(s.n_ok),
        "rejected": int(s.n - s.n_ok),
        "overweight": int(over),
        "overweight_hihi": int(s.n_hh),
        "underweight": int(under),
        "underweight_lolo": int(s.n_ll),
        "feeding_errors": int(feed),
        "detect_two": int(s.n_td),
        "unsplit": int(s.n_us),
        "metal": int(s.n_md),
        "external": int(s.n_ext),
        "overweight_pct": _ratio(over, s.n, 100),
        "underweight_pct": _ratio(under, s.n, 100),
        "rejected_pct": _ratio(s.n - s.n_ok, s.n, 100),
        "feeding_error_pct": _ratio(feed, s.n, 100),
        "ega_pct": _ratio(s.sum_dev_ok, s.sum_target_ok, 100),
        "ega_g_per_pack": _ratio(s.sum_dev_ok, s.n_dev_ok),
        "quantity_kg": s.sum_w / 1000,
        "passed_kg": s.sum_w_ok / 1000,
        "giveaway_kg": s.sum_dev_ok / 1000,
        "mean_g": _ratio(s.sum_w, s.n_weighed),
        "mean_target_g": _ratio(s.sum_target, s.n_dev),
        "mean_dev_g": _ratio(s.sum_dev, s.n_dev),
        "sd_g": _sd(s.n_weighed, s.sum_w, s.sum_w2),
        "sd_vs_target_g": _sd(s.n_dev, s.sum_dev, s.sum_dev2),
        "min_g": s.min_w,
        "max_g": s.max_w,
    }


def distribution(hist: list[tuple[float, int]]) -> dict[str, Any]:
    """Exact median / mode from (weight, count) pairs sorted by weight."""
    total = sum(n for _, n in hist)
    if not total:
        return {"median_g": None, "mode_g": None, "mode_count": None}
    k1, k2 = (total - 1) // 2, total // 2
    v1 = v2 = None
    cum = 0
    for w, n in hist:
        if v1 is None and cum + n > k1:
            v1 = w
        if cum + n > k2:
            v2 = w
            break
        cum += n
    mode_w, mode_n = max(hist, key=lambda x: (x[1], -x[0]))
    assert v1 is not None and v2 is not None
    return {"median_g": (v1 + v2) / 2, "mode_g": mode_w, "mode_count": mode_n}


def histogram_bins(hist: list[tuple[float, int]], max_bins: int = 40) -> tuple[list[dict[str, float]], float | None]:
    """Group exact weights into at most ``max_bins`` equal-width bins."""
    if not hist:
        return [], None
    lo, hi = hist[0][0], hist[-1][0]
    distinct = len(hist)
    if distinct <= max_bins:
        steps = [b[0] - a[0] for a, b in pairwise(hist)]
        width = min(steps) if steps else 1.0
        return [{"lo": w - width / 2, "hi": w + width / 2, "n": n} for w, n in hist], width
    width = (hi - lo) / max_bins or 1.0
    bins = [{"lo": lo + i * width, "hi": lo + (i + 1) * width, "n": 0} for i in range(max_bins)]
    for w, n in hist:
        bins[min(int((w - lo) / width), max_bins - 1)]["n"] += n
    return bins, width
