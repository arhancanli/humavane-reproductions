"""Lane R harvester: list recent replication packages on Harvard Dataverse that we can re-run here.

Keeps a package when no file is restricted, the total size is under --max-mb, it has code (R, Stata, Python) and data,
and it names a publication or a "Replication Data for:" title. Writes one JSON line per package to
data/repro/candidates.jsonl (newest first) with files, languages, size, authors, affiliations and publication.
Run: .venv/bin/python lanes/repro/harvest.py --pages 4
Older deposits whose papers are out: --from 2025-06-01 --to 2026-05-31 --need-pub --runnable --pages 40
"""
import argparse
import json
import os
import time

import requests

API = "https://dataverse.harvard.edu/api"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "data", "repro", "candidates.jsonl")
CODE = {".r": "R", ".rmd": "R", ".qmd": "R", ".do": "Stata", ".ado": "Stata", ".py": "Python", ".ipynb": "Python"}
DATA = {".csv", ".tab", ".dta", ".rds", ".rdata", ".rda", ".sav", ".xlsx", ".xls", ".parquet", ".feather", ".json", ".txt"}
UA = {"User-Agent": "humavane-repro-harvester/0.1"}


def field(fields, name):
    for f in fields:
        if f["typeName"] == name:
            return f["value"]
    return None


def describe(item):
    pid = item["global_id"]
    r = requests.get(f"{API}/datasets/:persistentId/", params={"persistentId": pid}, headers=UA, timeout=60)
    r.raise_for_status()
    v = r.json()["data"]["latestVersion"]
    files = [{"name": f["dataFile"]["filename"], "id": f["dataFile"]["id"], "size": f["dataFile"].get("filesize", 0),
              "restricted": bool(f.get("restricted"))} for f in v.get("files", [])]
    cit = v["metadataBlocks"]["citation"]["fields"]
    authors = [{"name": a["authorName"]["value"], "affiliation": (a.get("authorAffiliation") or {}).get("value")}
               for a in (field(cit, "author") or [])]
    pubs = [{"citation": (p.get("publicationCitation") or {}).get("value"),
             "url": (p.get("publicationURL") or {}).get("value"),
             "id": (p.get("publicationIDNumber") or {}).get("value")} for p in (field(cit, "publication") or [])]
    ext = lambda n: os.path.splitext(n.lower())[1]
    langs = sorted({CODE[ext(f["name"])] for f in files if ext(f["name"]) in CODE})
    return {"pid": pid, "title": item["name"], "published_at": item.get("published_at"),
            "url": item.get("url"), "authors": authors, "publications": pubs, "languages": langs,
            "has_data": any(ext(f["name"]) in DATA for f in files),
            "restricted": any(f["restricted"] for f in files),
            "size_mb": round(sum(f["size"] or 0 for f in files) / 1e6, 2), "files": files}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--max-mb", type=float, default=100)
    ap.add_argument("--start", type=int, default=0, help="first page (50 per page)")
    ap.add_argument("--from", dest="date_from", help="only packages published on or after YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", help="only packages published on or before YYYY-MM-DD")
    ap.add_argument("--need-pub", action="store_true",
                    help="keep only packages whose record links its publication (URL or DOI), so the paper can be found")
    ap.add_argument("--runnable", action="store_true", help="keep only packages with R or Python code (no Stata here)")
    a = ap.parse_args()
    # 13 Nov 2026: 38 of the first 62 fully passing packages had to be parked because their paper was not out yet.
    # A date window on older deposits, with the publication linked, finds studies whose printed numbers exist.
    fq = ['subject_ss:"Social Sciences"']
    if a.date_from or a.date_to:
        lo = (a.date_from + "T00:00:00Z") if a.date_from else "*"
        hi = (a.date_to + "T23:59:59Z") if a.date_to else "*"
        fq.append(f"dateSort:[{lo} TO {hi}]")
    seen = set()
    if os.path.exists(OUT):
        seen = {json.loads(l)["pid"] for l in open(OUT)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    kept = 0
    with open(OUT, "a") as out:
        for page in range(a.pages):
            r = requests.get(f"{API}/search", headers=UA, timeout=60, params={
                "q": "replication", "type": "dataset", "sort": "date", "order": "desc", "per_page": 50,
                "start": (a.start + page) * 50, "fq": fq})
            r.raise_for_status()
            items = r.json()["data"]["items"]
            if not items:
                break
            for item in items:
                if item["global_id"] in seen:
                    continue
                seen.add(item["global_id"])
                try:
                    d = describe(item)
                except requests.RequestException as e:
                    print("skip", item["global_id"], e)
                    continue
                ok = (d["languages"] and d["has_data"] and not d["restricted"] and d["size_mb"] <= a.max_mb
                      and (d["publications"] or d["title"].lower().startswith("replication data for")))
                if a.need_pub:
                    ok = ok and any(p.get("url") or p.get("id") for p in d["publications"])
                if a.runnable:
                    ok = ok and bool({"R", "Python"} & set(d["languages"]))
                if ok:
                    out.write(json.dumps(d) + "\n")
                    kept += 1
                time.sleep(0.3)
    print(f"kept {kept} new candidates -> {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
