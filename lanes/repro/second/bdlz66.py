"""Second, independent program for doi:10.7910/DVN/BDLZ66 (Musgrave and Sumner, "Using AI to Assess Demographic Balance
of Syllabi and Bibliographies", PS: Political Science & Politics 59(4), 2026, open access).

From the replication CSV (pandas), with no shared code: Table 1, the mean and median difference between each tool's
share of women authors and the hand-coded share in the same document, for bibliographies and syllabi. Compares the 16
values with Table 1 at the two decimals printed. Writes results/repro/BDLZ66_second.json.
Run: .venv/bin/python -I lanes/repro/second/bdlz66.py
"""
import json
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CSV = os.path.join(ENGINE, "data", "repro", "BDLZ66", "pkg", "musgrave-sumner-2026-replication-data.csv")
OUT = os.path.join(ENGINE, "results", "repro", "BDLZ66_second.json")
# type: (bib mean, syl mean, bib median, syl median) as printed
TABLE1 = {"chatgpt": (0.23, -1.29, 0.25, -2.00), "copilot": (-14.48, -5.14, -11.85, 0.30),
          "deepseek": (2.51, -2.86, 2.10, 1.00), "gbat": (3.48, 19.44, 3.45, 24.14)}


def main():
    d = pd.read_csv(CSV)
    hand = d[d.type == "handcode"].set_index("File.Name")["X..Women"]
    d = d[d.type != "handcode"].copy()
    d["diff"] = d["X..Women"] - d["File.Name"].map(hand)
    compared = matched = 0
    diffs, mine_all = [], {}
    for t, printed in TABLE1.items():
        s = d[d.type == t]
        mine = (s[s["syl.or.bib"] == "bib"]["diff"].mean(), s[s["syl.or.bib"] == "syl"]["diff"].mean(),
                s[s["syl.or.bib"] == "bib"]["diff"].median(), s[s["syl.or.bib"] == "syl"]["diff"].median())
        mine_all[t] = [round(float(x), 4) for x in mine]
        for lab, m, p in zip(("bib mean", "syl mean", "bib median", "syl median"), mine, printed):
            compared += 1
            ok = abs(round(m + 1e-12, 2) - p) < 1e-9
            matched += ok
            if not ok:
                diffs.append([t, lab, round(float(m), 4), p])
    n = d.groupby(["type", "syl.or.bib"]).size().unstack().to_dict()
    out = {"pid": "doi:10.7910/DVN/BDLZ66", "compared_to": "Table 1 of the open-access article", "compared": compared,
           "matched": matched, "differences": diffs, "values": mine_all, "documents": n}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1, default=float)
    print(f"{matched}/{compared} printed values matched; documents {n}")
    for x in diffs:
        print("DIFF", x)


if __name__ == "__main__":
    main()
