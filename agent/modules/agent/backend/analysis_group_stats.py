"""Independent host statistics for group-level regional analyses.

Standard-library only, so it can serve as the host reference for group methods
without importing numpy, scipy or primatex_ops. Agent code may use any library;
results are compared against these values with the same tolerances as the ROI
reference.

Scope (round 14 draft):
  * ordinary least squares with an intercept, categorical and continuous terms;
  * one-degree-of-freedom contrasts (t statistic, two-sided p, df = n - p);
  * Benjamini-Hochberg false discovery rate across all tested regions;
  * Cohen's d for two-group designs and Pearson r for single continuous effects;
  * per-region models over a long ROI table (subject, hemisphere, metric,
    label_key, name, value column).

Sources:
  Student t tail via the regularized incomplete beta function, continued
  fraction evaluation (Press et al., Numerical Recipes, 3rd ed., section 6.4).
  Benjamini Y, Hochberg Y. J R Stat Soc B 1995;57:289-300.
  Cohen J. Statistical Power Analysis for the Behavioral Sciences, 1988.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

EPS = 3.0e-16
TINY = 1.0e-300
MAX_ITER = 400
PIVOT_TOL = 1.0e-10


class DesignError(ValueError):
    """Design cannot be estimated (rank deficiency, missing levels, too few rows)."""


# ---------------------------------------------------------------- distributions

def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    h = d
    for m in range(1, MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            return h
    raise ArithmeticError("Incomplete beta continued fraction did not converge")


def betainc_regularized(a: float, b: float, x: float) -> float:
    """I_x(a, b) for a, b > 0 and 0 <= x <= 1."""
    if not (a > 0 and b > 0):
        raise ValueError("Beta parameters must be positive")
    if x < 0.0 or x > 1.0:
        raise ValueError("x must lie in [0, 1]")
    if x == 0.0 or x == 1.0:
        return x
    log_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                 + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p value of a Student t statistic."""
    if df <= 0:
        raise ValueError("Degrees of freedom must be positive")
    if not math.isfinite(t):
        return 0.0
    return betainc_regularized(df / 2.0, 0.5, df / (df + t * t))


# ------------------------------------------------------------------- algebra

def _invert(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(matrix)
    scale = max((abs(v) for row in matrix for v in row), default=0.0) or 1.0
    work = [list(map(float, row)) + [1.0 if i == j else 0.0 for j in range(n)]
            for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(work[r][col]))
        if abs(work[pivot][col]) <= PIVOT_TOL * scale:
            raise DesignError("Design matrix is rank deficient")
        work[col], work[pivot] = work[pivot], work[col]
        p = work[col][col]
        work[col] = [v / p for v in work[col]]
        for r in range(n):
            if r != col and work[r][col] != 0.0:
                f = work[r][col]
                work[r] = [a - f * b for a, b in zip(work[r], work[col])]
    return [row[n:] for row in work]


def ols(y: Sequence[float], X: Sequence[Sequence[float]]) -> dict:
    """Fit y = X b + e. X must already contain the intercept column."""
    n = len(y)
    if n != len(X) or n == 0:
        raise DesignError("Response and design have different lengths")
    p = len(X[0])
    if any(len(row) != p for row in X):
        raise DesignError("Ragged design matrix")
    df = n - p
    if df <= 0:
        raise DesignError("Not enough observations for the number of parameters")
    if not all(math.isfinite(v) for v in y):
        raise DesignError("Nonfinite response value")
    xtx = [[math.fsum(X[k][i] * X[k][j] for k in range(n)) for j in range(p)] for i in range(p)]
    xty = [math.fsum(X[k][i] * y[k] for k in range(n)) for i in range(p)]
    inv = _invert(xtx)
    beta = [math.fsum(inv[i][j] * xty[j] for j in range(p)) for i in range(p)]
    fitted = [math.fsum(X[k][i] * beta[i] for i in range(p)) for k in range(n)]
    rss = math.fsum((y[k] - fitted[k]) ** 2 for k in range(n))
    sigma2 = rss / df
    return {"beta": beta, "xtx_inv": inv, "sigma2": sigma2, "rss": rss, "df": df, "n": n, "p": p}


def contrast(fit: Mapping, weights: Sequence[float]) -> dict:
    """One-degree-of-freedom contrast c'b."""
    p = fit["p"]
    if len(weights) != p:
        raise DesignError("Contrast length does not match design")
    inv = fit["xtx_inv"]
    estimate = math.fsum(w * b for w, b in zip(weights, fit["beta"]))
    var = fit["sigma2"] * math.fsum(weights[i] * inv[i][j] * weights[j]
                                    for i in range(p) for j in range(p))
    se = math.sqrt(var) if var > 0 else 0.0
    if se == 0.0:
        t = math.inf if estimate != 0 else 0.0
    else:
        t = estimate / se
    p_value = 1.0 if t == 0.0 else t_two_sided_p(t, fit["df"])
    return {"estimate": estimate, "se": se, "t": t, "df": fit["df"], "p": p_value}


# ------------------------------------------------------------- multiple tests

def fdr_bh(p_values: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg adjusted q values, in input order."""
    m = len(p_values)
    if m == 0:
        return []
    if any(not (0.0 <= p <= 1.0) for p in p_values):
        raise ValueError("p values must lie in [0, 1]")
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, p_values[i] * m / rank)
        q[i] = running
    return q


# ---------------------------------------------------------------- effect sizes

def cohens_d(group_a: Sequence[float], group_b: Sequence[float]) -> float:
    """(mean_a - mean_b) / pooled SD with n-1 denominators."""
    na, nb = len(group_a), len(group_b)
    if na < 2 or nb < 2:
        raise DesignError("Cohen's d needs at least two observations per group")
    ma, mb = math.fsum(group_a) / na, math.fsum(group_b) / nb
    va = math.fsum((v - ma) ** 2 for v in group_a) / (na - 1)
    vb = math.fsum((v - mb) ** 2 for v in group_b) / (nb - 1)
    pooled = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled == 0.0:
        raise DesignError("Zero pooled standard deviation")
    return (ma - mb) / pooled


def pearson(x: Sequence[float], y: Sequence[float]) -> dict:
    n = len(x)
    if n != len(y) or n < 3:
        raise DesignError("Pearson correlation needs at least three paired values")
    mx, my = math.fsum(x) / n, math.fsum(y) / n
    sxy = math.fsum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = math.fsum((a - mx) ** 2 for a in x)
    syy = math.fsum((b - my) ** 2 for b in y)
    if sxx == 0.0 or syy == 0.0:
        raise DesignError("Constant variable in correlation")
    r = max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))
    df = n - 2
    t = math.inf if abs(r) == 1.0 else r * math.sqrt(df / (1.0 - r * r))
    return {"r": r, "t": t, "df": df, "p": 0.0 if abs(r) == 1.0 else t_two_sided_p(t, df), "n": n}


# --------------------------------------------------------------- design building

def build_design(participants: Mapping[str, Mapping[str, object]],
                 subjects: Sequence[str],
                 terms: Sequence[Mapping[str, object]]) -> dict:
    """Build an intercept design from a participants table.

    participants: subject_id -> {column: value}
    terms: [{"column": "group", "kind": "categorical", "reference": "control"},
            {"column": "age", "kind": "continuous", "center": True}, ...]
    Rows with a missing or nonnumeric value in any term are excluded and reported.
    The first term is the effect of interest; its columns are listed in
    ``effect_columns``.
    """
    if not terms:
        raise DesignError("At least one design term is required")
    kept, excluded = [], []
    for subject in subjects:
        row = participants.get(subject)
        if row is None:
            excluded.append({"subject": subject, "reason": "not in participants table"})
            continue
        bad = None
        for term in terms:
            value = row.get(str(term["column"]))
            if value is None or str(value).strip() == "":
                bad = f"missing {term['column']}"
                break
            if term["kind"] == "continuous":
                try:
                    if not math.isfinite(float(value)):
                        raise ValueError
                except (TypeError, ValueError):
                    bad = f"nonnumeric {term['column']}"
                    break
        if bad:
            excluded.append({"subject": subject, "reason": bad})
        else:
            kept.append(subject)
    columns = ["intercept"]
    blocks: list[list[list[float]]] = []
    effect_columns: list[str] = []
    levels_report: dict[str, object] = {}
    for index, term in enumerate(terms):
        name = str(term["column"])
        if term["kind"] == "continuous":
            values = [float(participants[s][name]) for s in kept]
            center = math.fsum(values) / len(values) if (values and term.get("center", True)) else 0.0
            blocks.append([[v - center] for v in values])
            columns.append(name)
            names = [name]
            levels_report[name] = {"kind": "continuous", "center": center}
        elif term["kind"] == "categorical":
            values = [str(participants[s][name]).strip() for s in kept]
            levels = sorted(set(values))
            reference = str(term.get("reference", levels[0] if levels else ""))
            if reference not in levels:
                raise DesignError(f"Reference level {reference!r} absent for {name}")
            others = [lvl for lvl in levels if lvl != reference]
            if not others:
                raise DesignError(f"Term {name} has a single level after exclusions")
            blocks.append([[1.0 if v == lvl else 0.0 for lvl in others] for v in values])
            names = [f"{name}[{lvl}]" for lvl in others]
            columns.extend(names)
            levels_report[name] = {"kind": "categorical", "reference": reference,
                                   "levels": {lvl: values.count(lvl) for lvl in levels}}
        else:
            raise DesignError(f"Unknown term kind {term['kind']!r}")
        if index == 0:
            effect_columns = names
    X = [[1.0] + [v for block in blocks for v in block[i]] for i in range(len(kept))]
    return {"subjects": kept, "excluded": excluded, "columns": columns, "X": X,
            "effect_columns": effect_columns, "levels": levels_report}


# --------------------------------------------------------------- regional models

def regional_glm(rows: Iterable[Mapping[str, object]],
                 participants: Mapping[str, Mapping[str, object]],
                 terms: Sequence[Mapping[str, object]],
                 value_column: str = "mean",
                 min_per_level: int = 2) -> dict:
    """Fit one OLS model per (hemisphere, metric, label_key) region.

    The effect of interest is the first term and must yield exactly one design
    column (a continuous variable or a two-level factor). FDR is applied across
    every region that could be fitted, both hemispheres together.
    """
    regions: dict[tuple, dict[str, float]] = {}
    names: dict[tuple, str] = {}
    for row in rows:
        key = (str(row["hemisphere"]), str(row["metric"]), int(row["label_key"]))
        value = row.get(value_column)
        if value is None or str(value).strip() == "":
            continue
        value = float(value)
        if not math.isfinite(value):
            continue
        subject = str(row["subject"])
        if subject in regions.setdefault(key, {}):
            raise DesignError(f"Duplicate subject {subject} for region {key}")
        regions[key][subject] = value
        names[key] = str(row.get("name", ""))
    results, skipped = [], []
    excluded: dict[str, str] = {}
    for key in sorted(regions):
        values = regions[key]
        design = build_design(participants, sorted(values), terms)
        for item in design["excluded"]:
            excluded.setdefault(item["subject"], item["reason"])
        if len(design["effect_columns"]) != 1:
            raise DesignError("Effect term must produce exactly one design column")
        first = terms[0]
        if first["kind"] == "categorical":
            counts = design["levels"][str(first["column"])]["levels"]
            if min(counts.values()) < min_per_level:
                skipped.append({"region": key, "reason": f"fewer than {min_per_level} per level"})
                continue
        y = [values[s] for s in design["subjects"]]
        try:
            fit = ols(y, design["X"])
        except DesignError as exc:
            skipped.append({"region": key, "reason": str(exc)})
            continue
        idx = design["columns"].index(design["effect_columns"][0])
        weights = [1.0 if i == idx else 0.0 for i in range(fit["p"])]
        test = contrast(fit, weights)
        record = {"hemisphere": key[0], "metric": key[1], "label_key": key[2],
                  "name": names[key], "n": fit["n"], "effect": design["effect_columns"][0],
                  "estimate": test["estimate"], "se": test["se"], "t": test["t"],
                  "df": test["df"], "p": test["p"], "q_fdr": None, "effect_size": None,
                  "effect_size_kind": None}
        if first["kind"] == "categorical" and len(terms) == 1:
            level = design["effect_columns"][0].split("[", 1)[1][:-1]
            col = str(first["column"])
            a = [values[s] for s in design["subjects"] if str(participants[s][col]).strip() == level]
            b = [values[s] for s in design["subjects"] if str(participants[s][col]).strip() != level]
            record["effect_size"], record["effect_size_kind"] = cohens_d(a, b), "cohens_d"
        elif first["kind"] == "continuous" and len(terms) == 1:
            x = [float(participants[s][str(first["column"])]) for s in design["subjects"]]
            record["effect_size"], record["effect_size_kind"] = pearson(x, y)["r"], "pearson_r"
        results.append(record)
    for record, q in zip(results, fdr_bh([r["p"] for r in results])):
        record["q_fdr"] = q
    return {"results": results, "skipped": skipped, "n_tests": len(results),
            "excluded_subjects": [{"subject": k, "reason": v} for k, v in sorted(excluded.items())],
            "correction": "benjamini_hochberg_all_fitted_regions"}
