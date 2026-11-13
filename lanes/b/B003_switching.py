"""Lane B · B003: the multiverse registered in prereg/B003_LBPTEK_switching.md (commit 0c90b76, 12 Nov 2026 +04).

126 specifications (estimator × pooling × comparison arm × scenarios), each with CR2 and CR1 standard errors by
respondent; randomization inference on the paper's specification; the registered decision rule.
Writes results/b/B003.json and B003_summary.txt. Run: .venv/bin/python -I lanes/b/B003_switching.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ENGINE, "lanes", "repro", "second"))
import lbptek as L  # noqa: E402  (data reader, REML, matrix square root; written for the reproduction)

OUT = os.path.join(ENGINE, "results", "b", "B003.json")
SUBS = ((1, "Republican", "dem", "Pro-Democrat hypotheticals", "Pro-Republican hypotheticals"),
        (1, "Democrat", "rep", "Pro-Republican hypotheticals", "Pro-Democrat hypotheticals"),
        (2, "Republican", "dem", "Pro-Democrat hypotheticals", "Pro-Republican hypotheticals"),
        (2, "Democrat", "rep", "Pro-Republican hypotheticals", "Pro-Democrat hypotheticals"))
SQ = "Status quo hypotheticals"


def long_with_topic(study, party, to):
    d = L.read(f"clean_hypotheticals_study_{study}.rds")
    d = d[d.pid_3_pre.astype(str) == party]
    rows = []
    for tp in L.TOPICS[study]:
        x = d[["resp_id", "treatment", "pid_7_factor_pre", "batch_pre"]].copy()
        x["value"] = d[f"{tp}_hyp_{to}"].to_numpy(float)
        x["topic"] = tp
        rows.append(x)
    out = pd.concat(rows, ignore_index=True)
    out = out[out.value.notna()].reset_index(drop=True)
    out["treatment"] = out.treatment.astype(str)
    out["rid"] = f"s{study}_" + out.resp_id.astype(str)
    return out


def covariates(d):
    return L.dummies(d.pid_7_factor_pre.astype(str)) + L.dummies(d.batch_pre.astype(str))


def design(d, estimator, out_arm, ref_arm, sub_ids=None):
    """Columns for one subsample (or a stack: sub_ids gives the subsample of each row). Returns X and the index of the
    effect column (out_arm vs ref_arm)."""
    other = [a for a in (SQ, *{s[3] for s in SUBS}) if a not in (out_arm, ref_arm)]
    # The out-party arm differs by subsample in a stack, so arms are coded by role: out, other non-reference
    t = d.treatment.to_numpy()
    z_out = (t == d["_out"].to_numpy()).astype(float)
    z_oth = ((t != d["_out"].to_numpy()) & (t != d["_ref"].to_numpy())).astype(float)
    cols = [np.ones(len(d)), z_out, z_oth]
    if sub_ids is not None:
        for s in sorted(set(sub_ids))[1:]:
            cols.append((sub_ids == s).astype(float))
    if estimator in ("lin", "ols"):
        groups = [np.ones(len(d), bool)] if sub_ids is None else [sub_ids == s for s in sorted(set(sub_ids))]
        for g in groups:
            sub = d[g]
            for c in covariates(sub):
                full = np.zeros(len(d))
                full[g] = c - (c.mean() if estimator == "lin" else 0)
                if np.std(full) == 0:
                    continue
                cols.append(full)
                if estimator == "lin":
                    cols.append(full * z_out)
                    cols.append(full * z_oth)
    X = np.column_stack(cols)
    return X, 1, other


def fit(X, y, clusters, j):
    XtXi = np.linalg.pinv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    order = np.argsort(clusters, kind="stable")
    cs = clusters[order]
    bounds = np.flatnonzero(np.r_[True, cs[1:] != cs[:-1], True])
    meat2 = np.zeros((X.shape[1],) * 2)
    meat0 = np.zeros_like(meat2)
    for a, z in zip(bounds[:-1], bounds[1:]):
        idx = order[a:z]
        Xg = X[idx]
        A = L.symsqrt_inv(np.eye(len(idx)) - Xg @ XtXi @ Xg.T)
        u2 = Xg.T @ (A @ e[idx])
        u0 = Xg.T @ e[idx]
        meat2 += np.outer(u2, u2)
        meat0 += np.outer(u0, u0)
    G, n, k = len(bounds) - 1, len(y), np.linalg.matrix_rank(X)
    v2 = (XtXi @ meat2 @ XtXi)[j, j]
    v1 = (XtXi @ meat0 @ XtXi)[j, j] * G / (G - 1) * (n - 1) / (n - k)
    return float(b[j]), float(np.sqrt(v2)), float(np.sqrt(v1))


def fe_meta(est, se):
    w = 1 / np.asarray(se) ** 2
    return float(np.sum(w * est) / np.sum(w)), float(np.sqrt(1 / np.sum(w)))


def spec(data, estimator, pooling, comparison, drop):
    parts = []
    for (study, party, to, out_arm, in_arm), d in zip(SUBS, data):
        d = d if drop is None else d[d.topic != drop]
        d = d.copy()
        d["_out"] = out_arm
        d["_ref"] = SQ if comparison == "status_quo" else in_arm
        parts.append(d)
    if pooling == "stacked":
        d = pd.concat(parts, ignore_index=True)
        sub_ids = np.concatenate([np.full(len(p), i) for i, p in enumerate(parts)])
        X, j, _ = design(d, estimator, None, None, sub_ids)
        b, se2, se1 = fit(X, d.value.to_numpy(float), d.rid.to_numpy(), j)
        n, r = len(d), d.rid.nunique()
    else:
        ests = []
        for d in parts:
            X, j, _ = design(d, estimator, None, None)
            ests.append(fit(X, d.value.to_numpy(float), d.rid.to_numpy(), j))
        e = [x[0] for x in ests]
        if pooling == "reml":
            b, se2, _ = L.reml(e, [x[1] for x in ests])
            _, se1, _ = L.reml(e, [x[2] for x in ests])
        else:
            b, se2 = fe_meta(e, [x[1] for x in ests])
            _, se1 = fe_meta(e, [x[2] for x in ests])
        n, r = sum(len(p) for p in parts), sum(p.rid.nunique() for p in parts)
    p2 = 2 * stats.norm.sf(abs(b / se2))
    p1 = 2 * stats.norm.sf(abs(b / se1))
    return {"estimator": estimator, "pooling": pooling, "comparison": comparison, "drop": drop or "none",
            "estimate": b, "se_cr2": se2, "p_cr2": float(p2), "se_cr1": se1, "p_cr1": float(p1), "rows": int(n),
            "respondents": int(r)}


def lin_estimate(d, treat):
    d = d.copy()
    d["treatment"] = treat
    X, j, _ = design(d, "lin", None, None)
    y = d.value.to_numpy(float)
    return float(np.linalg.lstsq(X, y, rcond=None)[0][j])


def main():
    data = [long_with_topic(s[0], s[1], s[2]) for s in SUBS]
    specs = []
    for estimator in ("lin", "ols", "dim"):
        for pooling in ("reml", "fixed", "stacked"):
            for comparison in ("status_quo", "pro_in_party"):
                for drop in (None, "violence", "ukraine", "economy", "medical", "guns", "camps"):
                    specs.append(spec(data, estimator, pooling, comparison, drop))
                    print(len(specs), estimator, pooling, comparison, drop, round(100 * specs[-1]["estimate"], 2),
                          round(100 * specs[-1]["se_cr2"], 2), flush=True)
    paper = [s for s in specs if (s["estimator"], s["pooling"], s["comparison"], s["drop"]) ==
             ("lin", "reml", "status_quo", "none")][0]

    # Randomization inference on the paper's specification (registered statistic: mean of the four Lin estimates)
    prepared = []
    for (study, party, to, out_arm, in_arm), d in zip(SUBS, data):
        d = d.copy()
        d["_out"], d["_ref"] = out_arm, SQ
        resp = d.groupby("rid").treatment.first()
        prepared.append((d, resp))
    obs = np.mean([lin_estimate(d, d.treatment.to_numpy()) for d, _ in prepared])
    rng = np.random.default_rng(20261112)
    R, hits = 2000, 0
    for _ in range(R):
        vals = []
        for d, resp in prepared:
            perm = pd.Series(rng.permutation(resp.to_numpy()), index=resp.index)
            vals.append(lin_estimate(d, d.rid.map(perm).to_numpy()))
        hits += abs(np.mean(vals)) >= abs(obs)
    p_ri = hits / R

    n = len(specs)
    pos = sum(s["estimate"] > 0 for s in specs)
    sig2 = sum(s["estimate"] > 0 and s["p_cr2"] < 0.05 for s in specs)
    sig1 = sum(s["estimate"] > 0 and s["p_cr1"] < 0.05 for s in specs)
    if pos >= 0.95 * n and sig2 >= 0.8 * n and p_ri < 0.01:
        verdict = "robust"
    elif sig2 < 0.5 * n:
        verdict = "fragile"
    else:
        verdict = "mixed"
    est = np.array([s["estimate"] for s in specs])
    by = {}
    for key in ("estimator", "pooling", "comparison", "drop"):
        by[key] = {v: {"median_pp": round(100 * float(np.median([s["estimate"] for s in specs if s[key] == v])), 2),
                       "sig_cr2": int(sum(s["estimate"] > 0 and s["p_cr2"] < 0.05 for s in specs if s[key] == v)),
                       "of": int(sum(s[key] == v for s in specs))}
                   for v in dict.fromkeys(s[key] for s in specs)}
    out = {"registered": "lanes/b/prereg/B003_LBPTEK_switching.md @ 0c90b76", "n_specs": n, "positive": int(pos),
           "positive_p05_cr2": int(sig2), "positive_p05_cr1": int(sig1), "median_pp": round(100 * float(np.median(est)), 2),
           "range_pp": [round(100 * float(est.min()), 2), round(100 * float(est.max()), 2)],
           "paper_spec": paper, "ri": {"statistic": "mean of four Lin estimates", "observed_pp": 100 * obs,
                                       "p": p_ri, "permutations": R, "seed": 20261112},
           "verdict": verdict, "by_choice": by, "specs": specs}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    lines = [f"B003 verdict: {verdict.upper()}",
             f"{pos}/{n} positive; {sig2}/{n} positive with p < .05 (CR2); {sig1}/{n} (CR1)",
             f"median {out['median_pp']} pp, range {out['range_pp'][0]} to {out['range_pp'][1]} pp",
             f"paper spec {100 * paper['estimate']:.2f} pp (CR2 {100 * paper['se_cr2']:.2f}); RI p {'< 1/' + str(R) if p_ri == 0 else '= ' + str(p_ri)} "
             f"({R} permutations; observed mean of four Lin estimates {100 * obs:.2f} pp)"]
    for key, v in by.items():
        lines.append(f"by {key}: " + "; ".join(f"{k}: median {x['median_pp']} pp, sig {x['sig_cr2']}/{x['of']}"
                                                for k, x in v.items()))
    open(os.path.join(os.path.dirname(OUT), "B003_summary.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
