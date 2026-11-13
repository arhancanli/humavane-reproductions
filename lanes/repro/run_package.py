"""Lane R: fetch one Dataverse replication package and run its scripts in a sandbox.

  .venv/bin/python lanes/repro/run_package.py fetch doi:10.7910/DVN/XXXX
  .venv/bin/python lanes/repro/run_package.py run doi:10.7910/DVN/XXXX script1.R [script2.R ...]

fetch: downloads every file (tabular files in their ORIGINAL format, since Dataverse's .tab conversion can change values)
into data/repro/<slug>/pkg/, records sha256 of each file in manifest.json. Third-party files are data: nothing is
executed at fetch time.
run: copies pkg/ to a fresh work/ folder and runs each script with `Rscript --vanilla` (no .Rprofile, no site files)
or `python3 -I`, under macOS sandbox-exec: no network, writes only inside work/ and the private temp folder. Logs and
exit codes go to runs.jsonl; everything the scripts write stays in work/ for comparison.
"""
import concurrent.futures
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

import requests

API = "https://dataverse.harvard.edu/api"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "repro"))
RSCRIPT = os.path.expanduser("~/.humavane-r/env/bin/Rscript")
UA = {"User-Agent": "humavane-repro/0.1"}


def slug(pid):
    return pid.split("/")[-1]


MARGIN_GB = 4   # free space that must remain after the package is downloaded


def fetch(pid):
    free = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
    if free < MARGIN_GB:
        raise SystemExit(f"refusing to fetch: only {free:.1f} GB free (margin {MARGIN_GB} GB)")
    base = os.path.join(ROOT, slug(pid))
    pkg = os.path.join(base, "pkg")
    os.makedirs(pkg, exist_ok=True)
    r = requests.get(f"{API}/datasets/:persistentId/", params={"persistentId": pid}, headers=UA, timeout=60)
    r.raise_for_status()
    v = r.json()["data"]["latestVersion"]
    manifest = {"pid": pid, "version": f'{v.get("versionNumber")}.{v.get("versionMinorNumber")}',
                "fetched_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "files": []}
    jobs = []
    for f in v["files"]:
        df = f["dataFile"]
        name = df.get("originalFileName") or df["filename"]
        rel = os.path.normpath(os.path.join(f.get("directoryLabel") or "", name))
        if rel.startswith("..") or os.path.isabs(rel):
            raise SystemExit(f"refusing path {rel}")
        jobs.append((df, rel))
    need = sum(df.get("originalFileSize") or df.get("filesize") or 0 for df, _ in jobs) / 1e9
    if free - need < MARGIN_GB:
        raise SystemExit(f"refusing to fetch: {need:.2f} GB would leave {free - need:.1f} GB free (margin {MARGIN_GB} GB)")

    def get(job):
        df, rel = job
        dest = os.path.join(pkg, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        params = {"format": "original"} if df.get("originalFileFormat") else {}
        with requests.get(f"{API}/access/datafile/{df['id']}", params=params, headers=UA, timeout=300, stream=True) as d:
            d.raise_for_status()
            h = hashlib.sha256()
            with open(dest, "wb") as out:
                for chunk in d.iter_content(1 << 16):
                    out.write(chunk); h.update(chunk)
        return {"path": rel, "sha256": h.hexdigest(), "bytes": os.path.getsize(dest)}

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        manifest["files"] = sorted(ex.map(get, jobs), key=lambda r: r["path"])
    json.dump(manifest, open(os.path.join(base, "manifest.json"), "w"), indent=2)
    print(f"fetched {len(manifest['files'])} files into {pkg}")


PROFILE = """(version 1)
(deny default)
(allow process-exec* process-fork)
(allow file-read*)
(deny file-read* (subpath "{home}/.ssh") (subpath "{home}/Library/Keychains") (subpath "{home}/.config")
  (subpath "{home}/.aws") (subpath "{home}/.claude") (subpath "{home}/Library/Preferences/.wrangler")
  (subpath "{home}/Library/Mail") (subpath "{home}/Library/Messages"))
(allow file-write* (subpath "{work}") (subpath "{tmp}") (literal "/dev/null"))
(allow sysctl-read)
(allow mach-lookup)
(allow ipc-posix-shm*)
(allow signal (target self))
(allow process-info* (target self))
(deny network*)
"""


SHIM_R = """getActiveDocumentContext <- function() {
  f <- Sys.getenv("HV_SCRIPT")
  if (!nzchar(f)) f <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
  p <- if (length(f) && nzchar(f[1])) normalizePath(f[1]) else file.path(getwd(), "script.R")
  list(id = "", path = p, contents = character(0), selection = list())
}
getSourceEditorContext <- getActiveDocumentContext
isAvailable <- function(...) FALSE
"""


def rstudio_shim(base):
    """Stand-in for rstudioapi when a script does setwd(dirname(rstudioapi::getActiveDocumentContext()$path)).

    In RStudio that call returns the open script's path; ours returns the path Rscript was given, so the script
    lands in its own folder exactly as it would in RStudio. Our code only, installed into base/shimlib; reported."""
    lib = os.path.join(base, "shimlib")
    if os.path.exists(os.path.join(lib, "rstudioapi")):
        return lib
    src = os.path.join(base, "shim", "rstudioapi")
    os.makedirs(os.path.join(src, "R"), exist_ok=True)
    open(os.path.join(src, "DESCRIPTION"), "w").write(
        "Package: rstudioapi\nVersion: 0.0.0.9000\nTitle: Humavane stand-in\nDescription: Script path outside "
        "RStudio.\nLicense: MIT\nAuthor: Humavane\nMaintainer: Humavane <none@humavane.com>\n")
    open(os.path.join(src, "NAMESPACE"), "w").write("export(getActiveDocumentContext, getSourceEditorContext, isAvailable)\n")
    open(os.path.join(src, "R", "shim.R"), "w").write(SHIM_R)
    os.makedirs(lib, exist_ok=True)
    subprocess.run([os.path.join(os.path.dirname(RSCRIPT), "R"), "CMD", "INSTALL", "--no-test-load", "-l", lib, src],
                   check=True, capture_output=True)
    return lib


# Prelude (ours, reported with every result): the package's own setwd() calls point at the authors' machines, and
# install.packages() needs a network the sandbox does not have. Each script runs in a fresh R from its own folder,
# with these two functions made harmless in the global environment; nothing in the script or data is changed.
# Attached on the search path (not the global environment), so a script's rm(list = ls()) cannot remove them.
PRELUDE_R = """attach(list(setwd = function(dir) invisible(getwd()),
            install.packages = function(...) invisible(NULL)), name = "humavane_prelude", warn.conflicts = FALSE)
"""
VENV_PY = os.path.abspath(os.path.join(HERE, "..", "..", ".venv", "bin", "python"))


def run(pid, scripts):
    base = os.path.join(ROOT, slug(pid))
    work = os.path.join(base, "work")
    if os.path.exists(work):
        shutil.rmtree(work)
    shutil.copytree(os.path.join(base, "pkg"), work)
    # here::here() and here::i_am() search upward for a project root; without a marker they climb out of the package
    # to the engine's own git root. An empty .here file (rprojroot's first criterion) keeps the root at the package.
    open(os.path.join(work, ".here"), "a").close()
    # layout.json (optional, written by us and reported): {"copy": {"from": "to"}, "mkdir": ["dir"]}. Only moves
    # files and makes folders the scripts expect; it never edits a script or a data file.
    lay = os.path.join(base, "layout.json")
    spec = json.load(open(lay)) if os.path.exists(lay) else {}
    if spec:
        for d in spec.get("mkdir", []):
            os.makedirs(os.path.join(work, d), exist_ok=True)
        for a, b in spec.get("copy", {}).items():
            os.makedirs(os.path.dirname(os.path.join(work, b)) or work, exist_ok=True)
            shutil.copy2(os.path.join(work, a), os.path.join(work, b))
    tmp = os.path.realpath(os.path.join(base, "tmp"))
    os.makedirs(tmp, exist_ok=True)
    profile = os.path.join(base, "sandbox.sb")
    open(profile, "w").write(PROFILE.format(work=os.path.realpath(work), tmp=tmp, home=os.path.realpath(os.path.expanduser("~"))))
    env = {"PATH": f"{os.path.dirname(RSCRIPT)}:/usr/bin:/bin", "HOME": tmp, "TMPDIR": tmp, "R_LIBS_USER": tmp,
           "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
    if spec.get("rstudio_shim"):
        env["R_LIBS"] = rstudio_shim(base)
    prelude = None
    if spec.get("prelude"):
        prelude = os.path.join(base, "prelude.R")
        open(prelude, "w").write(PRELUDE_R)
    log = open(os.path.join(base, "runs.jsonl"), "a")
    results = []
    for s in scripts:
        path = os.path.realpath(os.path.join(work, s))
        cwd = os.path.dirname(path) if (prelude or spec.get("rstudio_shim")) else work
        env["HV_SCRIPT"] = path
        if s.lower().endswith((".rmd", ".qmd")):
            # Notebook: knitr::purl extracts the R chunks (code is not run; chunks marked eval=FALSE come
            # out commented); the extracted .R then runs like any script, from the notebook's folder.
            purled = path + ".purl.R"
            # purl evaluates chunk options (authors' R expressions), so it runs in the sandbox too.
            subprocess.run(["/usr/bin/sandbox-exec", "-f", profile, RSCRIPT, "--vanilla", "-e", f"knitr::purl({json.dumps(path)}, output = {json.dumps(purled)}, "
                            "documentation = 0, quiet = TRUE)"], check=True, capture_output=True, env=env, cwd=os.path.dirname(path))
            cwd, path = os.path.dirname(path), purled
            src = f"source({json.dumps(prelude)}); " if prelude else ""
            cmd = [RSCRIPT, "--vanilla", "-e", src + f"source({json.dumps(path)}, echo = FALSE)"]
        elif s.lower().endswith(".r"):
            if prelude:
                expr = f"source({json.dumps(prelude)}); source({json.dumps(path)}, echo = FALSE)"
                cmd = [RSCRIPT, "--vanilla", "-e", expr]
            else:
                cmd = [RSCRIPT, "--vanilla", s]
        else:
            cmd = [VENV_PY, "-E", "-s", path]
        t0 = datetime.datetime.now(datetime.timezone.utc)
        try:
            p = subprocess.run(["/usr/bin/sandbox-exec", "-f", profile] + cmd, cwd=cwd, env=env,
                               capture_output=True, text=True, timeout=3600)
            code, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            code, out, err = -9, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "TIMEOUT 3600 s"
        rec = {"script": s, "exit": code, "started_utc": t0.isoformat(timespec="seconds"),
               "seconds": round((datetime.datetime.now(datetime.timezone.utc) - t0).total_seconds(), 1),
               "prelude": bool(prelude), "rstudio_shim": bool(spec.get("rstudio_shim"))}
        results.append(rec)
        name = s.replace("/", "__")
        open(os.path.join(base, f"{name}.out"), "w").write(out)
        open(os.path.join(base, f"{name}.err"), "w").write(err)
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print(("OK  " if code == 0 else "ERR ") + s + f"  ({rec['seconds']} s)", flush=True)
        if code:
            print(err[-1500:], flush=True)
    return results


def all_passed(q):
    """True when every planned script of this package has finished with exit 0 at least once."""
    f = os.path.join(ROOT, q["slug"], "runs.jsonl")
    if not os.path.exists(f):
        return False
    ok = {r.get("script") for r in map(json.loads, open(f)) if r.get("exit") == 0}
    return all(s in ok for s in q["scripts"])


def batch(slugs, pending=False):
    """Run every 'ready' package in queue.jsonl (or the slugs given), one after another, in the sandbox.
    With pending=True, skip packages whose scripts have all passed before."""
    queue = [json.loads(l) for l in open(os.path.join(ROOT, "queue.jsonl"))]
    todo = [q for q in queue if (q["slug"] in slugs if slugs else q["status"] == "ready")]
    if pending:
        todo = [q for q in todo if not all_passed(q)]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = open(os.path.join(ROOT, f"batch_{stamp}.jsonl"), "w")
    print(f"BATCH START {stamp}: {len(todo)} packages", flush=True)
    for q in todo:
        print(f"== {q['slug']} {q['title'][:70]}", flush=True)
        try:
            res = run(q["pid"], q["scripts"])
        except Exception as e:  # noqa: BLE001
            res = [{"error": repr(e)}]
        out.write(json.dumps({"slug": q["slug"], "results": res}) + "\n")
        out.flush()
    print(f"BATCH DONE {stamp}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(sys.argv[2])
    elif sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == "batch":
        args = sys.argv[2:]
        if "--detach" in args:
            args.remove("--detach")
            logf = os.path.join(ROOT, "batch_latest.log")
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "batch"] + args, stdout=open(logf, "w"),
                             stderr=subprocess.STDOUT, start_new_session=True)
            print(f"batch running in the background; log: {logf}")
        else:
            pending = "--pending" in args
            batch([a for a in args if a != "--pending"], pending=pending)
