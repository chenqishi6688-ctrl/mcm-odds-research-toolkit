# MCM v1.8 eight-item implementation and promotion plan

The engineering path for all eight items is implemented. Evidence-dependent
items remain in automated chronological collection with
`probability_delta_applied: 0`; the live v1.6.1 matrix and ranking are unchanged.

## Implemented research controls

1. Opponent-strength and schedule-strength candidate for the sporting baseline.
2. Recency weighting and season-transition control; promoted/relegated status is
   contracted but remains unavailable unless a licensed source supplies it.
3. Dixon-Coles or equivalent low-score dependence, compared with the current
   independent-Poisson score matrix.
4. Diagnostic Poisson-rate uncertainty propagated to 1X2 and goal bands; it is
   explicitly not yet a calibrated confidence interval.
5. Strict reviewed cross-provider team identity registry, with exact ID/alias
   resolution and manual review for unknown or conflicting identities.
6. Positioning/liability ingestion only from licensed measured sources; social
   or narrative data remain independent hypotheses, never funded-position facts.
7. Research-only capital threshold candidates by declared competition liquidity
   and time-to-kickoff, unapplied pending calibration.
8. Complete post-result scoring of the capital counterfactual, including helped,
   hurt, unchanged, and causal-explanation-unverified states.

The implementation also includes append-only non-market adjustment calibration,
licensed capital-evidence freezing, multi-event protected-segment evaluation,
and an eight-item state tracker. Engineering completion is never reported as
predictive validation.

## Delivered artifacts

- `references/sporting-history.schema.json` and enriched monitor history rows;
- `references/identity-registry.schema.json` plus `identity_registry.py`;
- `references/shadow-experiment.schema.json` and example preregistration;
- `references/shadow-artifact.schema.json`;
- append-only `shadow_model_lab.py freeze` and `score` commands;
- mandatory live-output invariants in `validate_report.py`.

## Remaining data availability work

Each frozen completed match should add competition/season/stage, venue, team
identifiers, kickoff, final and half-time score, xG when licensed, red cards,
rest days, promoted/relegated status, and source/retrieval timestamps. Optional
lineup, injury, weather, travel, and measured positioning inputs require their
own source group, observation time, missingness reason, and leakage review.
Odds fields are forbidden from sporting-model training inputs.

## Experiment manifest

For every candidate method freeze before evaluation: hypothesis, exact feature
set, training window, validation window, untouched test window, competitions,
exclusions, baseline comparator, seed, thresholds, primary metric, regression
segments, and rollback rule. Store predictions append-only before kickoff and
score every eligible event, including misses, voids, and unavailable cases.

## Promotion gates

- chronological walk-forward evaluation with an untouched final holdout;
- calibration improvement in log loss, Brier/RPS, and reliability curves rather
  than hit rate alone;
- no material regression in favorite strength, low/high goal environments,
  league liquidity, sparse-history teams, or promoted-team segments;
- stable benefit across more than one competition and season window;
- explicit leakage, missingness, identity, and settlement audits;
- capital-layer incremental results reported separately from base-model results;
- documented version, deterministic tests, preserved prior package, and a
  concrete rollback trigger.

Until every applicable gate passes, output the candidate model only as a shadow
comparison and do not change live probabilities, rankings, confidence, or MCM
status.

## Continuing automated work order

Populate reviewed identity entries and licensed optional fields; freeze a
multi-competition chronological dataset; preregister experiments; collect
append-only predictions and settlements; then publish aggregate calibration,
reliability, missingness, identity and protected-segment regressions. Request
promotion review only after the untouched holdout is complete.

