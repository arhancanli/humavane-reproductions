"""Second, independent program for doi:10.7910/DVN/LBPTEK (Coppock, Green & Porter, "Americans Can Imagine Changing
Partisan Affiliation: Evidence from Hypothetical Scenarios").

Re-derives the paper's headline from the cleaned .rds files (read with pyreadr, a file parser), sharing no code with the
authors' R:
  1. the four switching regressions of in_text_claims.R (Study 1 and 2; Republicans imagining pro-Democratic
     scenarios, Democrats imagining pro-Republican ones), each in long form with one row per respondent and scenario:
     Lin's (2013) estimator (treatment dummies, centred covariate dummies and their interactions) and CR2
     cluster-robust standard errors by respondent, as estimatr::lm_lin computes them;
  2. their random-effects meta-analysis by REML (metafor::rma.uni's default), for the effect and for the status-quo
     rate (the intercepts);
  3. the effects on imagined 7-point party ID (0.56 more Republican, 0.46 more Democratic): per scenario, OLS of the
     hypothetical party ID on treatment and covariate dummies with HC2 SEs (figures 3 and 4 code), then REML pooling
     of the 11 scenario estimates for each arm;
  4. the two single-ad ATEs on the 7-point scale (page 10), OLS with HC2 standard errors.
Writes results/repro/LBPTEK_second.json. Run: .venv/bin/python -I lanes/repro/second/lbptek.py
"""
import json
import os

import numpy as np
import pyreadr

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DATA = os.path.join(ENGINE, "data", "repro", "LBPTEK", "pkg")
OUT = os.path.join(ENGINE, "results", "repro", "LBPTEK_second.json")
TOPICS = {1: ["violence", "ukraine", "economy", "medical", "guns"],
          2: ["violence", "ukraine", "economy", "medical", "guns", "camps"]}


def read(name):
    return pyreadr.read_r(os.path.join(DATA, name))[None]


def dummies(series):
    """k-1 indicator columns for the levels present (the choice of baseline does not affect the treatment effect)."""
    levels = sorted(series.dropna().unique())
    return [(series == lv).to_numpy(float) for lv in levels[1:]]


def symsqrt_inv(M):
    w, V = np.linalg.eigh(M)
    w = np.clip(w, 1e-12, None)
    return V @ np.diag(w ** -0.5) @ V.T


def lin_cr2(d, arm, clusters):
    """Lin estimator of arm vs status quo, with CR2 SEs; returns (effect, se, intercept, intercept_se, n)."""
    t = d.treatment.astype(str)
    treat = {lv: (t == lv).to_numpy(float) for lv in ("Pro-Democrat hypotheticals", "Pro-Republican hypotheticals")}
    covs = dummies(d.pid_7_factor_pre.astype(str)) + dummies(d.batch_pre.astype(str))
    covs = [c - c.mean() for c in covs if c.std() > 0]
    cols, names = [np.ones(len(d))], ["(Intercept)"]
    for lv, z in treat.items():
        cols.append(z); names.append(lv)
    for j, c in enumerate(covs):
        cols.append(c); names.append(f"cov{j}")
        for lv, z in treat.items():
            cols.append(z * c); names.append(f"{lv}:cov{j}")
    X = np.column_stack(cols)
    keep = np.linalg.matrix_rank(X) == X.shape[1]
    assert keep, "design is rank deficient"
    y = d.value.to_numpy(float)
    XtXi = np.linalg.inv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    g = clusters.to_numpy()
    order = np.argsort(g, kind="stable")
    bounds = np.flatnonzero(np.r_[True, g[order][1:] != g[order][:-1], True])
    for a, z in zip(bounds[:-1], bounds[1:]):
        idx = order[a:z]
        Xg = X[idx]
        A = symsqrt_inv(np.eye(len(idx)) - Xg @ XtXi @ Xg.T)
        u = Xg.T @ (A @ e[idx])
        meat += np.outer(u, u)
    V = XtXi @ meat @ XtXi
    j = names.index(arm)
    return float(b[j]), float(np.sqrt(V[j, j])), float(b[0]), float(np.sqrt(V[0, 0])), int(len(y))


def reml(est, se):
    """Random-effects meta-analysis, REML tau^2 by Fisher scoring (metafor's default), returns (mu, se, tau2)."""
    y, v = np.asarray(est), np.asarray(se) ** 2
    tau2 = max(0.0, np.var(y, ddof=1) - v.mean())
    for _ in range(200):
        w = 1 / (v + tau2)
        mu = np.sum(w * y) / np.sum(w)
        P = np.diag(w) - np.outer(w, w) / np.sum(w)
        r = P @ y
        score = 0.5 * (r @ r - np.trace(P))
        info = 0.5 * np.trace(P @ P)
        new = max(0.0, tau2 + score / info)
        if abs(new - tau2) < 1e-12:
            tau2 = new
            break
        tau2 = new
    w = 1 / (v + tau2)
    mu = np.sum(w * y) / np.sum(w)
    return float(mu), float(np.sqrt(1 / np.sum(w))), float(tau2)


def long(study, party, to):
    d = read(f"clean_hypotheticals_study_{study}.rds")
    d = d[d.pid_3_pre.astype(str) == party]
    rows = []
    for tp in TOPICS[study]:
        x = d[["resp_id", "treatment", "pid_7_factor_pre", "batch_pre"]].copy()
        x["value"] = d[f"{tp}_hyp_{to}"].to_numpy(float)
        rows.append(x)
    import pandas as pd
    out = pd.concat(rows, ignore_index=True)
    return out[out.value.notna()].reset_index(drop=True)


def hc2(x, y):
    X = np.column_stack([np.ones(len(x)), x])
    XtXi = np.linalg.inv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    h = np.einsum("ij,jk,ik->i", X, XtXi, X)
    V = XtXi @ (X.T * (e ** 2 / (1 - h))) @ X @ XtXi
    return float(b[1]), float(np.sqrt(V[1, 1])), int(len(y))


def ols_hc2_terms(X, y, idx):
    XtXi = np.linalg.inv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    h = np.einsum("ij,jk,ik->i", X, XtXi, X)
    V = XtXi @ (X.T * (e ** 2 / (1 - h))) @ X @ XtXi
    return [(float(b[i]), float(np.sqrt(V[i, i]))) for i in idx]


def imagined_pid():
    est = {"Pro-Democrat hypotheticals": [], "Pro-Republican hypotheticals": []}
    for study in (1, 2):
        d = read(f"clean_hypotheticals_study_{study}.rds")
        for tp in TOPICS[study]:
            x = d[[f"{tp}_hyp", "treatment", "pid_7_factor_pre", "batch_pre"]].dropna()
            t = x.treatment.astype(str)
            cols = [np.ones(len(x))] + [(t == a).to_numpy(float) for a in est]
            cols += dummies(x.pid_7_factor_pre.astype(str)) + dummies(x.batch_pre.astype(str))
            r = ols_hc2_terms(np.column_stack(cols), x[f"{tp}_hyp"].to_numpy(float), [1, 2])
            for a, (b, se) in zip(est, r):
                est[a].append((b, se))
    return {a: reml([b for b, _ in v], [se for _, se in v]) + (len(v),) for a, v in est.items()}


def main():
    fits = []
    for study, party, to, arm in ((1, "Republican", "dem", "Pro-Democrat hypotheticals"),
                                  (1, "Democrat", "rep", "Pro-Republican hypotheticals"),
                                  (2, "Republican", "dem", "Pro-Democrat hypotheticals"),
                                  (2, "Democrat", "rep", "Pro-Republican hypotheticals")):
        d = long(study, party, to)
        eff, se, sq, sq_se, n = lin_cr2(d, arm, d.resp_id)
        fits.append({"study": study, "partisans": party, "arm": arm, "effect": eff, "se": se,
                     "status_quo": sq, "status_quo_se": sq_se, "rows": n, "respondents": int(d.resp_id.nunique())})
    meta = reml([f["effect"] for f in fits], [f["se"] for f in fits])
    sq_meta = reml([f["status_quo"] for f in fits], [f["status_quo_se"] for f in fits])
    five = read("clean_survey_experiments.rds")
    ads = {}
    for s in ("study_1_mturk", "study_2_mturk"):
        x = five[five.study.astype(str) == s][["any_treat", "pid_7_post"]].dropna()
        ads[s] = dict(zip(("ate", "se", "n"), hc2(x.any_treat.to_numpy(float), x.pid_7_post.to_numpy(float))))
    pid7 = imagined_pid()
    paper = {"imagined_pid_pro_rep": 0.56, "imagined_pid_pro_dem": -0.46, "meta_effect_pp": 7.0, "meta_effect_se_pp": 1.5, "status_quo_pct": 5, "pro_outparty_pct": 12,
             "ad_study_1": (-0.08, 0.18), "ad_study_2": (-0.06, 0.15)}
    checks = {
        "meta_effect": round(100 * meta[0], 1) == 7.0,
        "meta_se": round(100 * meta[1], 1) == 1.5,
        "status_quo_5pct": round(100 * sq_meta[0]) == 5,
        "pro_outparty_12pct": round(100 * (sq_meta[0] + meta[0])) == 12,
        "imagined_pid_pro_rep_0.56": round(pid7["Pro-Republican hypotheticals"][0], 2) == 0.56,
        "imagined_pid_pro_dem_0.46": round(pid7["Pro-Democrat hypotheticals"][0], 2) == -0.46,
        "ad_study_1": (round(ads["study_1_mturk"]["ate"], 2), round(ads["study_1_mturk"]["se"], 2)) == (-0.08, 0.18),
        "ad_study_2": (round(ads["study_2_mturk"]["ate"], 2), round(ads["study_2_mturk"]["se"], 2)) == (-0.06, 0.15),
    }
    out = {"pid": "doi:10.7910/DVN/LBPTEK", "fits": fits,
           "meta_effect": {"mu": meta[0], "se": meta[1], "tau2": meta[2]},
           "meta_status_quo": {"mu": sq_meta[0], "se": sq_meta[1], "tau2": sq_meta[2]},
           "imagined_pid": {a: dict(zip(("mu", "se", "tau2", "k"), v)) for a, v in pid7.items()},
           "single_ad": ads, "paper": paper, "checks": checks, "matched": sum(checks.values()), "of": len(checks)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    for f in fits:
        print(f"study {f['study']} {f['partisans']:<10} effect {100 * f['effect']:5.2f} pp (CR2 {100 * f['se']:.2f}); "
              f"status quo {100 * f['status_quo']:.2f}%  rows {f['rows']}")
    print(f"meta effect {100 * meta[0]:.2f} pp (SE {100 * meta[1]:.2f}), tau2 {meta[2]:.2e}; status quo "
          f"{100 * sq_meta[0]:.2f}%")
    print("imagined party ID:", {a: (round(v[0], 3), round(v[1], 3), v[3]) for a, v in pid7.items()})
    print("single ads:", {k: (round(v['ate'], 3), round(v['se'], 3)) for k, v in ads.items()})
    print(f"{out['matched']}/{out['of']} checks match:", checks)


if __name__ == "__main__":
    main()
