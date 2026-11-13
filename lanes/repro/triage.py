"""Lane R triage: fetch candidate packages and plan their runs by READING the scripts (nothing third-party is run).

For each R/Python candidate in data/repro/candidates.jsonl:
  - fetch it (run_package.fetch) unless already fetched;
  - pick top-level scripts (numbered or master scripts first; scripts that another script source()s are left out);
  - find every quoted relative path: if it is missing but a file with that name sits elsewhere in the package, plan a
    copy; plan the folders that outputs are written into;
  - note setwd()/rstudioapi (handled by the run prelude), install.packages (no network: must be preinstalled),
    absolute data paths, and packages/modules that are not installed here;
  - write data/repro/<slug>/layout.json and one line per package to data/repro/queue.jsonl with status
    ready | needs_packages | blocked and the reasons.

Run: .venv/bin/python -I lanes/repro/triage.py [--limit N] [--only SLUG ...]
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_package as rp  # noqa: E402

CANDS = os.path.join(rp.ROOT, "candidates.jsonl")
QUEUE = os.path.join(rp.ROOT, "queue.jsonl")
VENV_PY = os.path.abspath(os.path.join(rp.HERE, "..", "..", ".venv", "bin", "python"))

R_EXT = (".r", ".rmd", ".qmd")
PY_EXT = (".py",)
STR = re.compile(r"""["']([^"'\n]{1,200})["']""")
FILEISH = re.compile(r"\.(csv|tab|tsv|dta|rds|rdata|rda|sav|xlsx?|parquet|feather|json|txt|shp|gpkg|pdf|png|jpe?g|svg|"
                     r"tex|html|docx?|eps|tiff?|r|py|do)$", re.I)
WRITE_EXT = re.compile(r"\.(pdf|png|jpe?g|svg|tex|html|docx?|eps|tiff?|csv|rds|rdata|txt|xlsx)$", re.I)
R_LIB = re.compile(r"\b(?:library|require|requireNamespace)\s*\(\s*[\"']?([A-Za-z][A-Za-z0-9.]*)[\"']?")
R_NS = re.compile(r"([A-Za-z][A-Za-z0-9.]*)::")
# pandas and friends load these only when a function needs them, so an import scan misses them
PY_OPTIONAL = {"read_excel": "openpyxl", "to_excel": "openpyxl", "read_parquet": "pyarrow", "to_parquet": "pyarrow"}
P_LOAD = re.compile(r"p_load\(([^)]*)\)")
PY_IMPORT = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
SOURCE = re.compile(r"""source\(\s*(?:here::here\([^)]*\)|file\.path\([^)]*\)|["']([^"']+)["'])""")
HERE_CALL = re.compile(r"here(?:::here)?\(\s*((?:[\"'][^\"']+[\"']\s*,?\s*)+)\)")
BASE_R = {"base", "stats", "utils", "graphics", "grDevices", "methods", "datasets", "tools", "parallel", "grid",
          "splines", "stats4", "tcltk", "compiler"}
PY_STD = set(sys.stdlib_module_names)


def strip_comments(text, lang):
    out = []
    for line in text.splitlines():
        if lang == "R":
            line = re.sub(r"#(?=(?:[^\"']*[\"'][^\"']*[\"'])*[^\"']*$).*", "", line)
        else:
            line = re.sub(r"#(?=(?:[^\"']*[\"'][^\"']*[\"'])*[^\"']*$).*", "", line)
        out.append(line)
    return "\n".join(out)


CACHE = os.path.join(rp.ROOT, "_cache")


def known_r():
    names = set()
    for f in ("cran.txt", "bioc.txt"):
        fp = os.path.join(CACHE, f)
        if os.path.exists(fp):
            names |= set(open(fp).read().split())
    return names


CHUNK = re.compile(r"^```+\s*\{r[^}]*\}\s*$(.*?)^```+\s*$", re.S | re.M | re.I)
STRLIT = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'")


def r_code(raw, name):
    if name.lower().endswith((".rmd", ".qmd")):
        return "\n".join(m.group(1) for m in CHUNK.finditer(raw))
    return raw


def py_imports(raw):
    import ast
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module.split(".")[0])
    return out


def installed_r():
    p = subprocess.run([rp.RSCRIPT, "--vanilla", "-e", "cat(rownames(installed.packages()), sep='\\n')"],
                       capture_output=True, text=True)
    return set(p.stdout.split())


def installed_py():
    p = subprocess.run([VENV_PY, "-I", "-c", "import pkgutil;print('\\n'.join(m.name for m in pkgutil.iter_modules()))"],
                       capture_output=True, text=True)
    return set(p.stdout.split())


def plan(slug, have_r, have_py):
    base = os.path.join(rp.ROOT, slug)
    pkg = os.path.join(base, "pkg")
    files = []
    for root, _, fs in os.walk(pkg):
        for f in fs:
            files.append(os.path.relpath(os.path.join(root, f), pkg))
    by_name = {}
    for f in files:
        by_name.setdefault(os.path.basename(f).lower(), []).append(f)
    scripts = [f for f in files if f.lower().endswith(R_EXT + PY_EXT)]
    texts, pyimp = {}, {}
    for s in scripts:
        try:
            raw = open(os.path.join(pkg, s), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if s.lower().endswith(R_EXT):
            texts[s] = strip_comments(r_code(raw, s), "R")
        else:
            texts[s] = strip_comments(raw, "Py")
            pyimp[s] = py_imports(raw)
    sourced = set()
    for s, t in texts.items():
        for m in SOURCE.finditer(t):
            if m.group(1):
                sourced.add(os.path.basename(m.group(1)).lower())
        for name in re.findall(r"""source\([^)]*["']([^"'/]+\.R)["']""", t, re.I):
            sourced.add(name.lower())
    top = [s for s in scripts if os.path.basename(s).lower() not in sourced]
    master = [s for s in top if re.search(r"(master|run_?all|main_?run|replicate_?all|00_?run)", os.path.basename(s), re.I)]
    if master:
        top = master[:1]
    top.sort(key=lambda s: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)])

    reasons, copy, mkdir, need_r, need_py = [], {}, set(), set(), set()
    flags = {"setwd": False, "rstudioapi": False, "install_packages": False}
    for s, t in texts.items():
        sdir = os.path.dirname(s)
        is_r = s.lower().endswith(R_EXT)
        if is_r:
            if re.search(r"\bsetwd\(", t):
                flags["setwd"] = True
            if "rstudioapi" in t:
                flags["rstudioapi"] = True
            if re.search(r"install\.packages\(|install_github\(", t):
                flags["install_packages"] = True
            # library("x") keeps its quotes, so match it on the raw text; pkg:: on text without string literals
            for n in [m.group(1) for m in R_LIB.finditer(t)] + [m.group(1) for m in R_NS.finditer(STRLIT.sub('""', t))]:
                if n and n not in BASE_R:
                    need_r.add(n)
            for m in P_LOAD.finditer(t):
                for n in re.split(r"[,\s]+", m.group(1)):
                    n = n.strip("\"' ")
                    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.]*", n or "") and "=" not in n and n not in ("char", "install", "update", "character.only", "TRUE", "FALSE"):
                        need_r.add(n)
        else:
            for n in pyimp.get(s, set()):
                if n not in PY_STD:
                    need_py.add(n)
            for fn, mod in PY_OPTIONAL.items():
                if fn + "(" in t:
                    need_py.add(mod)
        lits = [m.group(1) for m in STR.finditer(t)]
        for m in HERE_CALL.finditer(t):
            parts = re.findall(r"[\"']([^\"']+)[\"']", m.group(1))
            lits.append("/".join(parts))
        for lit in lits:
            if not FILEISH.search(lit) or "://" in lit or "%" in lit or "{" in lit or "*" in lit:
                continue
            if re.match(r"^([A-Za-z]:[\\/]|/|~)", lit):
                if not WRITE_EXT.search(lit):
                    reasons.append(f"absolute path in {s}: {lit}")
                continue
            lit = lit.replace("\\", "/")
            # paths resolve from the script's folder (setwd to script dir) or the package root
            cands = [os.path.normpath(os.path.join(sdir, lit)), os.path.normpath(lit)]
            if any(c in files for c in cands) or any(c.startswith("..") for c in cands[:1]) and os.path.normpath(os.path.join(sdir, lit)).startswith(".."):
                continue
            target = cands[0] if sdir else cands[1]
            if target.startswith(".."):
                continue
            hits = by_name.get(os.path.basename(lit).lower(), [])
            if len(hits) == 1 and hits[0] != target:
                copy[hits[0]] = target
            if os.path.dirname(target):
                mkdir.add(os.path.dirname(target))
    # self-written intermediate files are fine; only flag reads of data that no file in the package can satisfy
    kr = known_r()
    missing_r = sorted(n for n in need_r if n not in have_r and n != "rstudioapi" and (not kr or n in kr))
    local = {os.path.splitext(os.path.basename(f))[0].lower() for f in files} | {os.path.basename(os.path.dirname(f)).lower() for f in files}
    missing_py = sorted(n for n in need_py if n not in have_py and n.lower() not in local)
    lay = {"copy": copy, "mkdir": sorted(mkdir), "rstudio_shim": flags["rstudioapi"],
           "prelude": flags["setwd"] or flags["install_packages"]}
    json.dump(lay, open(os.path.join(base, "layout.json"), "w"), indent=1)
    status = "blocked" if reasons else ("needs_packages" if missing_r or missing_py else "ready")
    if not top:
        status, reasons = "blocked", reasons + ["no R or Python script"]
    return {"slug": slug, "scripts": top, "status": status, "reasons": reasons[:8], "missing_r": missing_r,
            "missing_py": missing_py, "flags": flags, "layout": lay}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--refresh", action="store_true", help="re-plan packages already fetched; download nothing")
    a = ap.parse_args()
    have_r, have_py = installed_r(), installed_py()
    done = {}
    if os.path.exists(QUEUE):
        for l in open(QUEUE):
            d = json.loads(l)
            done[d["slug"]] = d
    n = 0
    for l in open(CANDS):
        c = json.loads(l)
        slug = rp.slug(c["pid"])
        if a.only and slug not in a.only:
            continue
        if not ({"R", "Python"} & set(c["languages"])):
            continue
        if not os.path.exists(os.path.join(rp.ROOT, slug, "manifest.json")):
            if a.refresh:
                continue
            try:
                rp.fetch(c["pid"])
            except Exception as e:  # noqa: BLE001
                print("fetch failed", slug, e)
                continue
        p = plan(slug, have_r, have_py)
        p.update({"pid": c["pid"], "title": c["title"], "authors": [x["name"] for x in c["authors"]],
                  "publications": c["publications"]})
        done[slug] = p
        with open(QUEUE + ".tmp", "w") as out:
            for d in done.values():
                out.write(json.dumps(d) + "\n")
        os.replace(QUEUE + ".tmp", QUEUE)
        print(f"{p['status']:<15} {slug} scripts={len(p['scripts'])} missing={p['missing_r'] + p['missing_py']} {p['reasons'][:2]}", flush=True)
        n += 1
        if a.limit and n >= a.limit:
            break
    with open(QUEUE, "w") as out:
        for d in done.values():
            out.write(json.dumps(d) + "\n")


if __name__ == "__main__":
    main()
