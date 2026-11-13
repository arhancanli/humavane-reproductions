# B003 · Pre-registered multiverse for the imagined party-switching effect (LBPTEK)

Registered: 12 Nov 2026, by signed git commit in the private engine repo before the analysis code exists. The commit
hash and its timestamp are the registration. Nothing below may change after registration; any deviation is reported as
a deviation.

## What was already seen
Data: Harvard Dataverse doi:10.7910/DVN/LBPTEK v1.0, clean_hypotheticals_study_1.rds (sha256 c06aa1c5b2d0ea77…) and
clean_hypotheticals_study_2.rds (7291ea292e09f2ed…). For the reproduction (results/repro/LBPTEK_report.txt) we fitted
exactly the paper's specification: the four Lin-estimator regressions with CR2 errors by respondent and their REML
pooling (7.04 pp, SE 1.47; the four estimates 9.61, 9.21, 3.35, 7.36), the per-scenario imagined party ID models, and
the single-ad ATEs. No other specification below has been estimated.

## Question
Coppock, Green and Porter (QJPS 2026) find that partisans asked to imagine pro-out-party scenarios say they would switch
parties 7 percentage points more often than those imagining status-quo scenarios (SE 1.5). How much does this depend on
the analyst's choices?

## Effect
In each of the four subsamples (Study 1 and 2 × Republicans facing pro-Democratic scenarios, Democrats facing
pro-Republican ones), long data with one row per respondent and scenario, outcome = would switch (0/1): the difference
between the pro-out-party arm and the comparison arm. The four are then pooled.

## The multiverse (3 × 3 × 2 × 7 = 126 specifications; each with two standard errors)
- Estimator (3): Lin (centred covariates interacted with treatment; the paper's); OLS with additive covariates; plain
  difference in means. Covariates as in the paper: pid_7_factor_pre and batch_pre dummies.
- Pooling (3): REML random-effects meta-analysis of the four (the paper's); fixed-effect (inverse-variance) meta-analysis;
  one stacked regression of all four subsamples with subsample fixed effects (and, for Lin, covariates centred and
  interacted within subsample), clustered by respondent.
- Comparison arm (2): status-quo scenarios (the paper's); the pro-in-party scenarios (the other non-out-party arm).
- Scenarios (7): all; or leaving out one scenario topic at a time (violence, ukraine, economy, medical, guns, camps;
  "camps" exists in Study 2 only, so leaving it out changes Study 2 only).
- Standard errors: CR2 by respondent (the paper's) and CR1 (the Stata-style small-sample correction) by respondent,
  both reported; p-values from the normal distribution for the pooled estimates.

## Reported
- For every specification: pooled estimate, SE (CR2 and CR1 versions), two-sided p, total rows and respondents.
- Share of the 126 with a positive estimate; share positive with p < 0.05 (CR2); the same with CR1; median estimate and
  range; the specification curve.
- Randomization inference for the paper's specification: 2,000 permutations of the respondent-level treatment arm
  within each subsample, seed 20261112; statistic = the unweighted mean of the four Lin estimates (no SEs needed);
  two-sided p = share of |permuted| >= |observed|.

## Decision rule (fixed now)
- "Robust": at least 95% of specifications positive AND at least 80% positive with p < 0.05 (CR2), AND randomization
  p < 0.01.
- "Fragile": fewer than 50% positive with p < 0.05 (CR2).
- Otherwise "mixed", and we report which choice drives the difference.

## Not claimed
Whatever the result, this concerns imagined switching in these two surveys, not actual partisan change. Results go to
the authors first, and only if they reply to the reproduction email (no second unsolicited email).
