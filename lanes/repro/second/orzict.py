"""Second, independent program for doi:10.7910/DVN/ORZICT (Yildirim, Chatagnier and Poletti, "Business Responses to
Geopolitics: European Firms' Divestment from China", Business and Politics, 2026, open access, CC BY).

From the firm panel (pandas), with no shared code, following the article's data steps as the deposit documents them
(drop NACE 51, 55, 60, 66 and thirteen named firms; geopolitical distance = geopolDist_usdis; real GDP logged;
anti-globalization = 1 - attitude; sector panel = country x NACE 2-digit x year means, strategic sector as max):
  - Table 1, both panels: N, min, mean, max, SD of the ten variables;
  - Tables 2 (firms) and 3 (sectors): fractional logit (quasi-binomial, logit link) of next-year ownership share with
    country fixed effects, written here by Newton steps on the Bernoulli quasi-likelihood; standard errors clustered by
    firm (Table 2) or by country-sector (Table 3) with the small-sample factor fixest applies by default
    (G/(G-1) x (n-1)/(n-K), with K = slopes plus every country effect: counting the
    effects as nested, i.e. excluding them, gives SEs about 0.1-0.3% smaller and misses 26 printed SEs); stars from t on G-1
    degrees of freedom at 0.1 / 0.05 / 0.01.
Compares every printed value at the precision printed. Writes results/repro/ORZICT_second.json.
Run: .venv/bin/python -I lanes/repro/second/orzict.py
"""
import json
import os

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CSV = os.path.join(ENGINE, "data", "repro", "ORZICT", "pkg", "Data", "bap_replication_data_ycp.csv")
OUT = os.path.join(ENGINE, "results", "repro", "ORZICT_second.json")
DROP_NACE = {51, 55, 60, 66}
DROP_FIRMS = {88, 2183, 2787, 1936, 2560, 367, 2014, 1394, 1395, 214, 468, 442, 2767}
VARS = ["ownership_lead_frac", "geo_distance", "carrots", "sticks", "anti_trade", "log_rgdp", "log_china_rgdp",
        "ln_auto_intensity", "policy_count", "strategic_sector"]
T1 = {  # panel: var -> (N, min, mean, max, sd) as printed
    "A": [(35206, 0.00, 0.94, 1.00, 0.17), (93822, 0.28, 0.39, 0.62, 0.06), (108834, 0.00, 0.77, 32.00, 2.66),
          (108834, 0.00, 1.20, 22.00, 2.95), (93993, 0.27, 0.37, 0.60, 0.08), (79660, 1.86, 4.78, 6.59, 0.85),
          (103887, 29.03, 29.92, 30.55, 0.45), (74078, -4.19, 6.42, 10.20, 1.03), (84099, 0.00, 0.32, 11.00, 0.88),
          (108834, 0.00, 0.09, 1.00, 0.29)],
    "B": [(4781, 0.00, 0.94, 1.00, 0.14), (7163, 0.28, 0.38, 0.62, 0.06), (8382, 0.00, 0.30, 18.83, 1.25),
          (8382, 0.00, 1.07, 21.00, 2.67), (7239, 0.27, 0.37, 0.60, 0.08), (6827, 1.86, 4.56, 6.59, 0.84),
          (8001, 29.03, 29.92, 30.55, 0.45), (4653, -4.19, 6.36, 10.20, 1.14), (6477, 0.00, 0.25, 7.00, 0.73),
          (8382, 0.00, 0.25, 1.00, 0.43)],
}
BASE = ["geo_distance", "carrots", "sticks", "anti_trade", "strategic_sector"]
CONTROLS = ["log_rgdp", "log_china_rgdp", "ln_auto_intensity", "policy_count"]
MODELS = {"Base": [], "China x Anti-globalization": [("geo_distance", "anti_trade")],
          "All two-way": [("carrots", "geo_distance"), ("sticks", "geo_distance"), ("geo_distance", "anti_trade"),
                          ("carrots", "anti_trade"), ("sticks", "anti_trade")]}
ROWS = ["geo_distance", "carrots", "sticks", "anti_trade", "strategic_sector", "carrots:geo_distance",
        "sticks:geo_distance", "geo_distance:anti_trade", "carrots:anti_trade", "sticks:anti_trade", "log_rgdp",
        "log_china_rgdp", "ln_auto_intensity", "policy_count"]
# Tables 2 and 3: model -> {row: "coef stars|se"}; N, clusters
T2 = {
    "Base": ("-1.835*** 0.465|-0.018 0.027|0.015 0.018|-1.532*** 0.582|0.146 0.163|||||"
             "|-0.330*** 0.123|0.187 0.230|-0.000 0.090|0.047 0.046", 18915, 1648),
    "China x Anti-globalization": ("-4.419 4.199|-0.017 0.027|0.015 0.018|-4.861 5.525|0.146 0.163|||7.992 13.250||"
                                   "|-0.330*** 0.123|0.196 0.226|-0.000 0.090|0.047 0.046", 18915, 1648),
    "All two-way": ("-12.045*** 3.898|0.113 0.225|0.096 0.108|-13.217*** 5.012|0.121 0.162|0.381** 0.163|"
                    "-0.046 0.152|30.114** 12.006|-1.034 0.649|-0.189 0.248|-0.327*** 0.122|0.248 0.235|"
                    "-0.001 0.092|0.066 0.048", 18915, 1648),
}
T3 = {
    "Base": ("-1.399* 0.788|-0.069 0.044|0.088** 0.041|-4.128*** 0.885|-0.214 0.223|||||"
             "|-1.544*** 0.388|0.230 0.290|0.041 0.160|0.381*** 0.096", 2263, 201),
    "China x Anti-globalization": ("-1.994 7.284|-0.068 0.045|0.088** 0.041|-4.878 9.349|-0.214 0.223|||1.839 22.143||"
                                   "|-1.544*** 0.389|0.232 0.294|0.041 0.160|0.381*** 0.096", 2263, 201),
    "All two-way": ("-6.550 7.890|0.172 0.276|-0.148 0.288|-9.800 9.957|-0.204 0.225|0.415 0.310|0.220 0.362|"
                    "13.676 23.759|-1.422** 0.570|0.426 0.642|-1.542*** 0.390|0.292 0.296|0.040 0.161|"
                    "0.382*** 0.095", 2263, 201),
}


def load():
    d = pd.read_csv(CSV, low_memory=False)
    d["nace2"] = pd.to_numeric(d.nace_2digit, errors="coerce")
    d["geo_distance"] = d.geopolDist_usdis
    d["log_rgdp"] = np.log(d.rgdp)
    d = d[~d.nace2.isin(DROP_NACE) & ~d.eu_firm_id.isin(DROP_FIRMS)].copy()
    d["anti_trade"] = 1 - d.attitude
    return d


def sector_panel(d):
    g = d.groupby(["country", "nace2", "year"], dropna=False)
    s = g[["ownership_lead_frac", "anti_trade", "geo_distance", "log_rgdp", "policy_count", "log_china_rgdp",
           "ln_auto_intensity", "carrots", "sticks"]].mean()
    s["strategic_sector"] = g.strategic_sector.max()
    s = s.reset_index()
    s["sector_id"] = s.country.astype(str) + "_" + s.nace2.astype(str)
    return s


def frac_logit(d, terms, cluster):
    cols = BASE + [f"{a}:{b}" for a, b in terms] + CONTROLS
    need = ["ownership_lead_frac", "country", cluster] + BASE + CONTROLS
    s = d.dropna(subset=need).copy()
    # country effects for countries whose outcome is constant at 0 or 1 are not identified (fixest drops them)
    keep = s.groupby("country").ownership_lead_frac.transform(lambda v: not ((v == 1).all() or (v == 0).all()))
    s = s[keep.astype(bool)]
    for a, b in terms:
        s[f"{a}:{b}"] = s[a] * s[b]
    Xs = s[cols].to_numpy(float)
    F = pd.get_dummies(s.country.astype(str), dtype=float).to_numpy()
    X = np.column_stack([Xs, F])
    y = s.ownership_lead_frac.to_numpy(float)
    beta = np.zeros(X.shape[1])
    beta[len(cols):] = np.log(np.clip(y.mean(), 1e-6, 1 - 1e-6) / (1 - np.clip(y.mean(), 1e-6, 1 - 1e-6)))
    for _ in range(100):
        mu = 1 / (1 + np.exp(-(X @ beta)))
        W = mu * (1 - mu)
        step = np.linalg.lstsq((X * W[:, None]).T @ X, X.T @ (y - mu), rcond=None)[0]
        beta += step
        if np.abs(step).max() < 1e-11:
            break
    mu = 1 / (1 + np.exp(-(X @ beta)))
    A = np.linalg.pinv((X * (mu * (1 - mu))[:, None]).T @ X)
    sc = X * (y - mu)[:, None]
    g = s[cluster].astype(str).to_numpy()
    tot = pd.DataFrame(sc).groupby(g).sum().to_numpy()
    G, n, K = tot.shape[0], len(y), len(cols) + F.shape[1]   # slopes + every country effect, as fixest counts here
    V = A @ (tot.T @ tot) @ A * (G / (G - 1)) * ((n - 1) / (n - K))
    k = len(cols)
    se = np.sqrt(np.diag(V))[:k]
    p = 2 * stats.t.sf(np.abs(beta[:k] / se), G - 1)
    return {c: (float(beta[i]), float(se[i]), float(p[i])) for i, c in enumerate(cols)}, n, G


def stars(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def fmt(x):
    s = f"{x:.3f}"
    return s


def main():
    firm = load()
    sector = sector_panel(firm)
    compared = matched = 0
    diffs = []
    for panel, data in (("A", firm), ("B", sector)):
        for var, printed in zip(VARS, T1[panel]):
            x = data[var].dropna().astype(float)
            mine = (len(x), x.min(), x.mean(), x.max(), x.std(ddof=1))
            for lab, m, p in zip(("N", "min", "mean", "max", "sd"), mine, printed):
                compared += 1
                ok = (m == p) if lab == "N" else abs(round(float(m) + 0.0, 2) - p) < 1e-9 or f"{m:.2f}" == f"{p:.2f}"
                matched += ok
                if not ok:
                    diffs.append(["Table 1", panel, var, lab, round(float(m), 4), p])
    fits = {}
    for tab, data, cl, printed in (("Table 2", firm, "eu_firm_id", T2), ("Table 3", sector, "sector_id", T3)):
        for model, terms in MODELS.items():
            est, n, G = frac_logit(data, terms, cl)
            fits[f"{tab} {model}"] = {"n": n, "clusters": G, "coef": est}
            cells, pn, pg = printed[model]
            for row, cell in zip(ROWS, cells.split("|")):
                if not cell:
                    continue
                pc, ps = cell.split()
                b, se, p = est[row]
                mine_b = fmt(b)
                mine_b = mine_b if mine_b != "0.000" or b >= 0 else "-0.000"
                for lab, m, t in (("coef", mine_b, f"{float(pc.rstrip('*')):.3f}" if pc.rstrip('*') != "-0.000"
                                   else "-0.000"), ("se", fmt(se), ps), ("stars", stars(p), "*" * pc.count("*"))):
                    compared += 1
                    ok = m == t
                    matched += ok
                    if not ok:
                        diffs.append([tab, model, row, lab, m, t])
            for lab, m, t in (("N", n, pn), ("clusters", G, pg)):
                compared += 1
                matched += m == t
                if m != t:
                    diffs.append([tab, model, lab, "", m, t])
    out = {"pid": "doi:10.7910/DVN/ORZICT", "compared_to": "Tables 1-3 of the open-access article",
           "compared": compared, "matched": matched, "differences": diffs, "fits": fits}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1, default=float)
    print(f"{matched}/{compared} printed values matched")
    for x in diffs[:40]:
        print("DIFF", x)


if __name__ == "__main__":
    main()
