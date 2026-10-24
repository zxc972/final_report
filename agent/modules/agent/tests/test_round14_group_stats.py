"""Round 14: stdlib group statistics used as the host reference for group methods.

Fixed expected values were produced with SciPy 1.18.1 (ttest_ind, pearsonr,
t.sf, false_discovery_control); the optional randomized test re-checks against
SciPy/NumPy when they are installed.
"""
import importlib.util
import math
from pathlib import Path
import random

_PATH = Path(__file__).resolve().parents[1] / "backend" / "analysis_group_stats.py"
_SPEC = importlib.util.spec_from_file_location("analysis_group_stats_r14", _PATH)
gs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gs)

A = [2.41, 2.55, 2.38, 2.62, 2.47, 2.51]
B = [2.30, 2.28, 2.44, 2.35, 2.21, 2.39, 2.33]
AGE = [22, 35, 41, 50, 58, 63, 71]
THICK = [2.62, 2.58, 2.51, 2.47, 2.40, 2.39, 2.30]


def close(a, b, rtol=1e-9, atol=1e-12):
    return abs(a - b) <= atol + rtol * abs(b)


def rows_for(values, label=1, hemi="lh", prefix="s"):
    return [{"subject": f"{prefix}{i}", "hemisphere": hemi, "metric": "thickness",
             "label_key": label, "name": f"r{label}", "mean": v} for i, v in enumerate(values)]


def test_t_distribution_tail():
    assert close(gs.t_two_sided_p(2.5, 10), 0.03144684423660882)
    assert close(gs.t_two_sided_p(-0.3, 3), 0.783763292039919)
    assert gs.t_two_sided_p(0.0, 5) == 1.0


def test_two_group_glm_matches_pooled_t_test_and_cohens_d():
    rows = rows_for(A, prefix="a") + rows_for(B, prefix="b")
    participants = {f"a{i}": {"group": "control"} for i in range(len(A))}
    participants.update({f"b{i}": {"group": "patient"} for i in range(len(B))})
    out = gs.regional_glm(rows, participants, [{"column": "group", "kind": "categorical",
                                                "reference": "control"}])
    r = out["results"][0]
    assert r["effect"] == "group[patient]" and r["n"] == 13 and r["df"] == 11
    assert close(r["t"], -3.5451781683428703)
    assert close(r["p"], 0.0045907718971231245)
    assert r["effect_size_kind"] == "cohens_d"
    assert close(r["effect_size"], -1.9723550534518361)
    assert close(r["q_fdr"], r["p"])


def test_continuous_effect_matches_pearson():
    rows = rows_for(THICK)
    participants = {f"s{i}": {"age": a} for i, a in enumerate(AGE)}
    r = gs.regional_glm(rows, participants, [{"column": "age", "kind": "continuous"}])["results"][0]
    assert r["effect_size_kind"] == "pearson_r"
    assert close(r["effect_size"], -0.9871053194019259)
    assert close(r["p"], 3.601418954172516e-05, rtol=1e-7)
    assert r["estimate"] < 0


def test_fdr_bh_values_and_order():
    q = gs.fdr_bh([0.01, 0.04, 0.03, 0.2, 0.5])
    expected = [0.05, 0.06666666666666667, 0.06666666666666667, 0.25, 0.5]
    assert all(close(a, b) for a, b in zip(q, expected))
    assert gs.fdr_bh([]) == []


def test_fdr_runs_across_all_regions_and_hemispheres():
    rows = []
    participants = {}
    for i, a in enumerate(AGE):
        participants[f"s{i}"] = {"age": a}
    for label in (1, 2):
        for hemi in ("lh", "rh"):
            shift = 0.01 * label
            rows += rows_for([v + shift for v in THICK], label=label, hemi=hemi)
    out = gs.regional_glm(rows, participants, [{"column": "age", "kind": "continuous"}])
    assert out["n_tests"] == 4
    assert [r["hemisphere"] for r in out["results"]] == ["lh", "lh", "rh", "rh"]
    assert all(r["q_fdr"] >= r["p"] for r in out["results"])


def test_covariate_adjustment_and_exclusion_reporting():
    rows = rows_for(THICK + [2.5])
    participants = {f"s{i}": {"age": a, "sex": "F" if i % 2 else "M"} for i, a in enumerate(AGE)}
    participants["s7"] = {"age": "", "sex": "F"}
    out = gs.regional_glm(rows, participants, [{"column": "age", "kind": "continuous"},
                                               {"column": "sex", "kind": "categorical"}])
    r = out["results"][0]
    assert r["n"] == 7 and r["df"] == 4 and r["effect_size"] is None
    assert out["excluded_subjects"] == [{"subject": "s7", "reason": "missing age"}]


def test_design_errors_are_explicit():
    participants = {f"s{i}": {"group": "x"} for i in range(4)}
    try:
        gs.regional_glm(rows_for([1, 2, 3, 4]), participants,
                        [{"column": "group", "kind": "categorical"}])
    except gs.DesignError as exc:
        assert "single level" in str(exc)
    else:
        raise AssertionError("single-level factor must be rejected")
    try:
        gs.ols([1.0, 2.0, 3.0], [[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]])
    except gs.DesignError as exc:
        assert "rank deficient" in str(exc)
    else:
        raise AssertionError("collinear design must be rejected")
    duplicate = rows_for([1.0, 2.0]) + rows_for([3.0])
    try:
        gs.regional_glm(duplicate, {"s0": {"age": 1}, "s1": {"age": 2}},
                        [{"column": "age", "kind": "continuous"}])
    except gs.DesignError as exc:
        assert "Duplicate subject" in str(exc)
    else:
        raise AssertionError("duplicate subject rows must be rejected")


def test_small_groups_are_skipped_not_fitted():
    rows = rows_for([1.0, 1.1, 1.2], prefix="a") + rows_for([2.0], prefix="b")
    participants = {"a0": {"g": "A"}, "a1": {"g": "A"}, "a2": {"g": "A"}, "b0": {"g": "B"}}
    out = gs.regional_glm(rows, participants, [{"column": "g", "kind": "categorical"}])
    assert out["n_tests"] == 0 and "fewer than 2" in out["skipped"][0]["reason"]


def test_randomized_against_scipy_when_available():
    try:
        import numpy as np
        from scipy import stats
    except ImportError:
        return
    rng = random.Random(14)
    for _ in range(50):
        n, p = rng.randint(6, 40), rng.randint(1, 3)
        gen = np.random.default_rng(rng.randint(0, 10**9))
        X = np.column_stack([np.ones(n)] + [gen.normal(size=n) for _ in range(p)])
        y = X @ np.arange(p + 1) + gen.normal(size=n)
        fit = gs.ols(list(y), X.tolist())
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        assert all(close(a, b, rtol=1e-8, atol=1e-10) for a, b in zip(fit["beta"], beta))
        test = gs.contrast(fit, [0, 1] + [0] * (p - 1))
        s2 = float(((y - X @ beta) ** 2).sum()) / (n - p - 1)
        t = beta[1] / math.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
        assert close(test["t"], t, rtol=1e-8)
        assert close(test["p"], 2 * stats.t.sf(abs(t), n - p - 1), rtol=1e-8, atol=1e-15)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
