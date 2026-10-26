# MCM v1.7+ shadow research protocol

The shadow layer measures whether added sporting structure improves predictive
calibration. It is not a second live forecast and cannot change v1.6.1 output.

## Freeze

Use only provider-neutral completed 90-minute results observed before the
analysis freeze. Market, bookmaker, price, odds, handicap and betting fields
are rejected recursively. Resolve cross-provider identities through the
reviewed registry; unresolved or conflicting joins are excluded and counted.
Supply an experiment manifest before the test window begins whenever the run
is intended for later promotion evidence.

The frozen artifact contains the core control, opponent-strength/recency
Poisson candidate, Dixon-Coles candidate, diagnostic uncertainty envelope,
field coverage, rest-day audit and unapplied capital-threshold candidate.
Writing is exclusive: never overwrite a prior prediction.

## Score

After a verified 90-minute result, score every candidate with 1X2 log loss,
Brier, ranked probability score, goal-band log loss and top-class correctness.
When paired rankings exist, classify the capital counterfactual as helped,
hurt or unchanged, while keeping causal explanation unverified. Score all
eligible frozen events, including failures and unavailable cases in the
aggregate denominator.

## Promotion boundary

No single event is promotion evidence. Aggregate using chronological
train/validation/untouched-test windows. Require calibration improvement and
no material regression across favorite strength, goal environment, liquidity,
sparse history, promoted teams and competition/season segments. Any market
leakage, identity conflict, post-freeze row, overwritten prediction, live
probability delta or ranking mutation triggers rollback to v1.6.1 behavior.

