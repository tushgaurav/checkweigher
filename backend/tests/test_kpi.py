import math
import statistics

import pytest

from checkweigher.api.data import merge_sums
from checkweigher.api.kpi import Sums, compute_kpis, distribution, histogram_bins


def sums_for(weights: list[float], target: float, judgements: list[str]) -> Sums:
    s = Sums()
    for w, j in zip(weights, judgements, strict=True):
        s.n += 1
        s.n_weighed += 1
        s.n_ok += j == "OK"
        s.n_hi += j == "HI"
        s.n_lo += j == "LO"
        s.sum_w += w
        s.sum_w2 += w * w
        s.n_dev += 1
        s.sum_dev += w - target
        s.sum_dev2 += (w - target) ** 2
        s.sum_target += target
        if j == "OK":
            s.sum_w_ok += w
            s.n_dev_ok += 1
            s.sum_dev_ok += w - target
            s.sum_target_ok += target
        s.min_w = w if s.min_w is None else min(s.min_w, w)
        s.max_w = w if s.max_w is None else max(s.max_w, w)
    return s


def test_weighted_aggregation_is_not_average_of_percentages():
    # Machine A: 1000 products, 10 overweight (1%). Machine B: 10 products, 5 overweight (50%).
    a = sums_for([500.0] * 990 + [510.0] * 10, 500, ["OK"] * 990 + ["HI"] * 10)
    b = sums_for([500.0] * 5 + [510.0] * 5, 500, ["OK"] * 5 + ["HI"] * 5)
    k = compute_kpis(merge_sums([a, b]))
    assert k["total"] == 1010
    assert k["overweight_pct"] == pytest.approx(15 / 1010 * 100)  # not (1 + 50) / 2
    assert k["overweight_pct"] != pytest.approx(25.5)


def test_mean_sd_match_statistics_module():
    ws = [498.2, 501.3, 503.9, 499.0, 502.2, 500.1]
    k = compute_kpis(sums_for(ws, 500, ["OK"] * len(ws)))
    assert k["mean_g"] == pytest.approx(statistics.mean(ws))
    assert k["sd_g"] == pytest.approx(statistics.stdev(ws))
    assert k["sd_vs_target_g"] == pytest.approx(statistics.stdev(ws))


def test_merged_sd_equals_pooled_raw_sd():
    a = [500.1, 501.2, 499.8, 502.0]
    b = [503.3, 498.4, 500.0]
    k = compute_kpis(merge_sums([sums_for(a, 500, ["OK"] * 4), sums_for(b, 500, ["OK"] * 3)]))
    assert k["sd_g"] == pytest.approx(statistics.stdev(a + b))


def test_ega_only_counts_accepted_packs():
    k = compute_kpis(sums_for([502.0, 504.0, 520.0], 500, ["OK", "OK", "HI"]))
    assert k["ega_pct"] == pytest.approx((2 + 4) / 1000 * 100)
    assert k["ega_g_per_pack"] == pytest.approx(3.0)


def test_empty():
    k = compute_kpis(Sums())
    assert k["total"] == 0 and k["ega_pct"] is None and k["sd_g"] is None and k["overweight_pct"] is None


@pytest.mark.parametrize("ws", [[1.0], [1.0, 2.0], [3.0, 1.0, 2.0, 2.0], [5.0, 1.0, 1.0, 9.0, 9.0, 9.0, 2.0]])
def test_distribution_matches_statistics(ws):
    hist: dict[float, int] = {}
    for w in ws:
        hist[w] = hist.get(w, 0) + 1
    d = distribution(sorted(hist.items()))
    assert d["median_g"] == statistics.median(ws)
    assert d["mode_g"] == min(statistics.multimode(ws))


def test_histogram_bins_cover_all_counts():
    hist = [(round(480 + i * 0.1, 1), (i % 7) + 1) for i in range(400)]
    bins, width = histogram_bins(hist, 40)
    assert len(bins) == 40 and sum(b["n"] for b in bins) == sum(n for _, n in hist)
    assert width and math.isclose(bins[-1]["hi"], hist[-1][0])
    small, w = histogram_bins([(500.0, 3), (500.1, 2)], 40)
    assert len(small) == 2 and w == pytest.approx(0.1)
