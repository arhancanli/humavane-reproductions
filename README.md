# Humavane reproductions

Published studies in the social sciences, re-run from their own public data and code, with every checked number
recomputed by a second program written separately.

[Humavane](https://humavane.com) is a lab for philosophy, history and human behaviour. It tests claims against
something outside its own models; here the test is the paper's printed numbers. This repository holds the work for
each reproduced study: a report of what was run and what matched, the second program, and that program's output.

## How a reproduction is done

1. The authors' replication package is fetched from its public archive (so far Harvard Dataverse), every file in its
   original format, with a sha256 hash of each (`results/repro/<ID>_files.json`).
2. The authors' own scripts are run unchanged in a sandbox with no network (`lanes/repro/run_package.py`).
3. A second program, written separately in Python and sharing no code with the authors' scripts, recomputes the
   numbers the paper prints from the deposited data (`lanes/repro/second/`).
4. The printed numbers are compared with both. The report (`results/repro/<ID>_report.txt`) says how many match to the
   printed precision and gives every difference exactly.
5. The authors receive the report first. A study is listed here once they have seen it and agreed.

A study counts as reproduced when the authors' code runs and the paper's headline numbers are matched by both routes.
That shows the published numbers follow from the deposited data and code. It does not show that the design, the data
collection or the conclusions are right.

## Studies

| Study | Replication package | Result | Files |
|---|---|---|---|
| Alexander Coppock, Donald P. Green and Ethan Porter, "Americans Can Imagine Changing Partisan Affiliation: Evidence from Hypothetical Scenarios", Quarterly Journal of Political Science 21(1) (2026) | [doi:10.7910/DVN/LBPTEK](https://doi.org/10.7910/DVN/LBPTEK) | 19 of the 20 scripts run unchanged; all 8 headline numbers checked are matched by the authors' code and by the second program | [report](results/repro/LBPTEK_report.txt), [second program](lanes/repro/second/lbptek.py), [its output](results/repro/LBPTEK_second.json), [file hashes](results/repro/LBPTEK_files.json) |
| Aydin B. Yildirim, J. Tyson Chatagnier and Arlo Poletti, "Business Responses to Geopolitics: European Firms' Divestment from China", Business and Politics (2026, First View) | [doi:10.7910/DVN/ORZICT](https://doi.org/10.7910/DVN/ORZICT) | The script runs unchanged; all 310 values compared in Tables 1 to 3 are matched by the second program | [report](results/repro/ORZICT_report.txt), [second program](lanes/repro/second/orzict.py), [its output](results/repro/ORZICT_second.json), [file hashes](results/repro/ORZICT_files.json) |
| Sarah Musgrave and Jane L. Sumner, "Using AI to Assess Demographic Balance of Syllabi and Bibliographies", PS: Political Science & Politics 59(4) (2026) | [doi:10.7910/DVN/BDLZ66](https://doi.org/10.7910/DVN/BDLZ66) | The script runs unchanged and writes a table identical to the published Table 1; all 16 values are matched by the second program | [report](results/repro/BDLZ66_report.txt), [second program](lanes/repro/second/bdlz66.py), [its output](results/repro/BDLZ66_second.json), [file hashes](results/repro/BDLZ66_files.json) |

## Robustness analyses with the plan fixed first

For some reproduced studies we also ask how far a headline result depends on the analyst's choices. The full list of
specifications and the rule for reading the result are written down and committed before any of them is run; the plan
is in `lanes/b/prereg/` unchanged. The plan listed below was committed in our working repository, not at a public
registry, so its time is our own record. Later plans carry a signed timestamp from an independent authority, taken
before any analysis code is run (`lanes/b/stamp.py` gets and verifies it; the tokens sit beside each plan).

| Analysis | Study | Question | Result | Files |
|---|---|---|---|---|
| B003 | LBPTEK | How much does the 7-point imagined party-switching effect depend on the analyst's choices? | 126 of 126 specifications positive with p < .05; median 8.1 points (5.8 to 9.6) (plan committed 12 Nov 2026 19:49:56 +04) | [plan](lanes/b/prereg/B003_LBPTEK_switching.md), [code](lanes/b/B003_switching.py), [summary](results/b/B003_summary.txt), [all specifications](results/b/B003.json) |

## Run it yourself

The second programs need Python 3.12 or later and the packages in `requirements.txt`. They run on any system.

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python lanes/repro/run_package.py fetch doi:10.7910/DVN/LBPTEK
.venv/bin/python -I lanes/repro/second/lbptek.py
```

`fetch` downloads the package into `data/repro/LBPTEK/pkg/` and runs nothing. The second program then writes
`results/repro/LBPTEK_second.json`; `git diff` shows whether your numbers differ from ours.

Running the authors' own scripts (`run_package.py run ...`) uses macOS `sandbox-exec` and an R installation whose
path is set at the top of `run_package.py`; change `RSCRIPT` to your own.

## Licence, citing, contact

Code: MIT (`LICENSE`). Reports and result files: CC BY 4.0. The studies' data and code are not copied here; they stay
in their own archives under their own terms. To cite this repository see `CITATION.cff`.

Found a mistake, or want a study added or removed? Open an issue here.
