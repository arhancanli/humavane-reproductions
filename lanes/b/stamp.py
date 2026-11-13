"""Lane B: an outside timestamp for an analysis plan, taken before any analysis code is run.

Why (13 Nov 2026): plans B001-B008 were fixed by signed commits in our private repository, minutes before their
results. Nobody outside can check that order. From B009 on, the plan's SHA-256 goes to an independent RFC 3161
timestamp authority (DigiCert's public service, plus FreeTSA as a second), which signs "this hash existed at this
time". Only the hash is sent, never the plan. The signed tokens are stored beside the plan and published with it.

  .venv/bin/python -I lanes/b/stamp.py stamp  lanes/b/prereg/B009_xxx.md    get the tokens (once, before any code)
  .venv/bin/python -I lanes/b/stamp.py verify lanes/b/prereg/B009_xxx.md    check them against the file

Anyone can verify without this script (macOS/LibreSSL or OpenSSL):
  openssl ts -reply -in PLAN.digicert.tsr -token_out -out token.p7
  openssl pkcs7 -inform DER -in token.p7 -print_certs -out chain.pem
  openssl ts -verify -data PLAN.md -in PLAN.digicert.tsr -CAfile /etc/ssl/cert.pem -untrusted chain.pem

Analysis scripts call require(plan) first: it stops the run unless the plan is committed in git unchanged and its
DigiCert token verifies against the file. The token's time goes into the result file.
"""
import os
import re
import subprocess
import sys
import tempfile

AUTHORITIES = {"digicert": "http://timestamp.digicert.com", "freetsa": "https://freetsa.org/tsr"}
ROOTS = "/etc/ssl/cert.pem"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def token_path(plan, name):
    return os.path.splitext(plan)[0] + f".{name}.tsr"


def token_time(tsr):
    out = run(["openssl", "ts", "-reply", "-in", tsr, "-text"]).stdout
    m = re.search(r"Time stamp:\s*(.+)", out)
    return m.group(1).strip() if m and "Status: Granted" in out else None


def stamp(plan):
    with tempfile.TemporaryDirectory() as tmp:
        tsq = os.path.join(tmp, "q.tsq")
        r = run(["openssl", "ts", "-query", "-data", plan, "-sha256", "-cert", "-out", tsq])
        if r.returncode or not os.path.exists(tsq):
            sys.exit("could not build the timestamp query: " + r.stderr[-300:])
        for name, url in AUTHORITIES.items():
            out = token_path(plan, name)
            if os.path.exists(out):
                print(f"{name}: token already there ({token_time(out)}); a plan is stamped once")
                continue
            r = run(["curl", "-sS", "-m", "60", "-H", "Content-Type: application/timestamp-query",
                     "--data-binary", "@" + tsq, url, "-o", out])
            t = token_time(out) if os.path.exists(out) else None
            if r.returncode or not t:
                if os.path.exists(out):
                    os.remove(out)
                print(f"{name}: no token ({r.stderr.strip()[:120]})")
            else:
                print(f"{name}: {t} -> {os.path.relpath(out)}")
    print(verify(plan))


def verify(plan):
    """Return the DigiCert token's time if it verifies against the plan file; raise SystemExit otherwise."""
    tsr = token_path(plan, "digicert")
    if not os.path.exists(tsr):
        sys.exit(f"no timestamp token for {plan}: run stamp.py stamp on it before any analysis code")
    with tempfile.TemporaryDirectory() as tmp:
        p7, chain = os.path.join(tmp, "t.p7"), os.path.join(tmp, "chain.pem")
        run(["openssl", "ts", "-reply", "-in", tsr, "-token_out", "-out", p7])
        run(["openssl", "pkcs7", "-inform", "DER", "-in", p7, "-print_certs", "-out", chain])
        r = run(["openssl", "ts", "-verify", "-data", plan, "-in", tsr, "-CAfile", ROOTS, "-untrusted", chain])
    if "Verification: OK" not in r.stdout + r.stderr:
        sys.exit(f"the timestamp token does not match {plan} (the plan changed after it was stamped, or the token is bad)")
    return f"verified: {os.path.basename(plan)} existed at {token_time(tsr)} (DigiCert RFC 3161)"


def require(plan):
    """For analysis scripts: the plan must be committed unchanged and carry a valid outside timestamp."""
    plan = os.path.abspath(plan)
    repo = run(["git", "-C", os.path.dirname(plan), "rev-parse", "--show-toplevel"]).stdout.strip()
    rel = os.path.relpath(plan, repo)
    if run(["git", "-C", repo, "cat-file", "-e", f"HEAD:{rel}"]).returncode:
        sys.exit(f"{rel} is not committed: commit the plan (and its tokens) before running the analysis")
    if run(["git", "-C", repo, "status", "--porcelain", "--", rel]).stdout.strip():
        sys.exit(f"{rel} differs from the committed plan: the analysis runs only on the plan as committed")
    msg = verify(plan)
    commit = run(["git", "-C", repo, "log", "-1", "--format=%h %cI", "--", rel]).stdout.strip()
    return {"plan": rel, "plan_commit": commit, "outside_timestamp": token_time(token_path(plan, "digicert")),
            "authority": "DigiCert RFC 3161 (" + AUTHORITIES["digicert"] + ")", "check": msg}


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("stamp", "verify"):
        sys.exit(__doc__)
    if sys.argv[1] == "stamp":
        stamp(sys.argv[2])
    else:
        print(verify(sys.argv[2]))
