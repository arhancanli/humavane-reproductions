"""Lane R: install the packages that triage found missing, from conda-forge (R binaries), CRAN (source) and PyPI.

Only well-known public package indexes; nothing from a replication package is run. Heavy or account-bound packages are
skipped and left as the reason a package is not ready. Afterwards re-run triage to refresh statuses.
Run: .venv/bin/python -I lanes/repro/install_deps.py [--dry-run]
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_package as rp  # noqa: E402

MAMBA = os.path.expanduser("~/.humavane-r/bin/micromamba")
ENV = os.path.expanduser("~/.humavane-r/env")
ENGINE = os.path.abspath(os.path.join(rp.HERE, "..", ".."))
SKIP_PY = {"sentence_transformers", "torch", "tensorflow", "jax", "faster_whisper", "whisper", "ee", "osgeo", "feat", "transformers", "openai"}
SKIP_R = {"traktok", "rgee", "reticulate", "tensorflow", "keras", "torch", "arrow"}  # arrow: CRAN builds libarrow from source (GBs, ~1 h)
PY_NAME = {"PIL": "pillow", "sklearn": "scikit-learn", "cv2": "opencv-python", "yaml": "pyyaml",
           "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "Bio": "biopython"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    need_r, need_py = set(), set()
    for l in open(os.path.join(rp.ROOT, "queue.jsonl")):
        q = json.loads(l)
        need_r |= set(q.get("missing_r", [])) - SKIP_R
        need_py |= set(q.get("missing_py", [])) - SKIP_PY
    print("R:", sorted(need_r))
    print("Python:", sorted(need_py))
    if a.dry_run:
        return
    log = open(os.path.join(rp.ROOT, "install_deps.log"), "a")
    # 1. conda-forge binaries: one solve for all recipes that exist, then one at a time only if that fails
    def on_conda_forge(n):
        r = subprocess.run([MAMBA, "search", "-q", "-c", "conda-forge", "--json", f"r-{n.lower()}"],
                           capture_output=True, text=True)
        try:
            return any(x["name"] == f"r-{n.lower()}" for x in json.loads(r.stdout)["result"]["pkgs"])
        except (ValueError, KeyError, TypeError):
            return False

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        found = dict(zip(sorted(need_r), ex.map(on_conda_forge, sorted(need_r))))
    on_cf = [n for n in sorted(need_r) if found[n]]
    left = [n for n in sorted(need_r) if n not in on_cf]
    print(f"conda-forge has {len(on_cf)}, CRAN/Bioc for {len(left)}", flush=True)
    # Keep R at 4.4 and leave installed packages alone, so the solve stays small and nothing built for 4.4 breaks
    # (12 Nov: one 102-package solve without these ran 60+ minutes without finishing).
    def mamba(pkgs, timeout):
        try:
            r = subprocess.run([MAMBA, "install", "-y", "-q", "--freeze-installed", "-p", ENV, "-c", "conda-forge",
                                "r-base=4.4"] + [f"r-{n.lower()}" for n in pkgs], capture_output=True, text=True,
                               timeout=timeout)
            return r.returncode, r.stderr[-1500:]
        except subprocess.TimeoutExpired:
            return -9, "timeout"

    retry = []
    for i in range(0, len(on_cf), 12):
        group = on_cf[i:i + 12]
        code, err = mamba(group, 900)
        log.write(f"conda group {group}: {code} {err}\n")
        print(f"conda group {i // 12 + 1}: {'ok' if code == 0 else 'failed (' + str(code) + ')'} {group}", flush=True)
        if code:
            retry += group
    for n in retry:
        code, err = mamba([n], 300)
        log.write(f"conda r-{n.lower()}: {code} {err}\n")
        if code:
            left.append(n)
        print(("conda ok " if code == 0 else "conda no ") + n, flush=True)
    # 2. CRAN / Bioconductor source for the rest
    if left:
        expr = ("options(repos = c(CRAN = 'https://cloud.r-project.org')); "
                f"pk <- c({', '.join(repr(x) for x in left)}); "
                "for (p in pk) { r <- try(install.packages(p, quiet = TRUE), silent = TRUE); "
                "if (!requireNamespace(p, quietly = TRUE)) { if (!requireNamespace('BiocManager', quietly = TRUE)) "
                "install.packages('BiocManager', quiet = TRUE); try(BiocManager::install(p, ask = FALSE, update = FALSE), "
                "silent = TRUE) }; cat(p, requireNamespace(p, quietly = TRUE), '\\n') }")
        p = subprocess.run([rp.RSCRIPT, "--vanilla", "-e", expr], capture_output=True, text=True,
                           env={**os.environ, "PATH": f"{os.path.dirname(rp.RSCRIPT)}:/usr/bin:/bin"})
        log.write(p.stdout + p.stderr[-3000:])
        print(p.stdout, flush=True)
    # 3. PyPI into the engine venv
    if need_py:
        names = [PY_NAME.get(n, n) for n in sorted(need_py)]
        for n in names:
            p = subprocess.run(["uv", "pip", "install", "-q", "--python", os.path.join(ENGINE, ".venv", "bin", "python"), n],
                               capture_output=True, text=True, cwd=ENGINE)
            log.write(f"pip {n}: {p.returncode} {p.stderr[-300:]}\n")
            print(("pip ok " if not p.returncode else "pip no ") + n, flush=True)


if __name__ == "__main__":
    main()
