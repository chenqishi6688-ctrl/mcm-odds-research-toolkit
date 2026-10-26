# MCM v1.6.3+evidence1 live execution + v1.8.8 shadow evidence automation

## Meaning of full

The skill is operationally complete when it can ingest, separate, freeze,
compare, validate, and report every required layer. This does not force every
fixture to receive `FULL-MCM`. Status remains evidence-dependent:

- complete, timely, independent inputs may reach `FULL-MCM`;
- a valid independent baseline with material gaps is `MCM-DEGRADED`;
- no independent baseline is `MARKET-STRUCTURE-ONLY`;
- unresolved identity, orientation, horizon, or kickoff is `BLOCKED`.

Never use the phrase full version to bypass these fixture-level gates.

## Required input families

For a genuinely full pre-event fixture, freeze all of the following before
kickoff and preserve timestamps and lineage:

1. verified fixture identity, home/away orientation, kickoff, timezone, and
   90-minute settlement horizon;
2. a market-free independent score baseline with at least two distinct metric
   groups, league home/away scoring environment, venue-specific team attack and
   defence rates, and a sourced first-half goal share when half/full output is
   required;
3. opening, intermediate, latest, and late market observations, with at least
   two genuinely independent books for a full cross-book claim;
4. the complete `0..6, 7+` exact-total market when a market-implied four-band
   distribution is published;
5. verified non-market sporting updates used for any numerical MCM adjustment;
6. narrative signals and measured positioning in separate arrays;
7. a frozen capital-intent card with attraction, protection, feasibility,
   competing non-intent explanation, falsifier, reorder condition, and
   with/without-capital directions;
8. actual integer three-way handicap offers and separately validated Asian
   two-way handicap evidence;
9. historical-rule observations with their promotion status and counterexamples.

If measured bet share, turnover, liability, or exchange volume is absent, write
`narratively attractive`; never write `crowded money` or an equivalent funded
positioning claim.

## Three probability layers

1. Market-implied: de-vig each complete book, then aggregate each book's latest
   verified observation. It remains audited market evidence.
2. Independent baseline: use the market-free score matrix from
   `independent_score_matrix.py`. When only frozen completed-match history is
   available, first run `sporting_baseline_builder.py`. It selects complete xG
   if available, otherwise completed goals, enforces minimum samples and
   pre-freeze times, and shrinks venue-specific team rates toward the league
   home/away environment. The artifact must disclose metric, samples,
   shrinkage weight, reliability, and market-independence status.
3. MCM-adjusted: apply only timestamped non-market sporting deltas. Reweight the
   independent score matrix within each 1X2 settlement class so 1X2, exact
   score, goal band, half/full, and integer-handicap outputs remain tied to one
   coherent matrix. Capital evidence may reorder scenarios only under the
   existing CI gates and may never silently override the numerical matrix.

A legitimate no-adjustment conclusion may preserve the independent matrix as
the adjusted layer. Record `no_qualifying_adjustment`, zero 1X2 deltas, and the
reason that no frozen non-market update cleared the gate. Never call this
layer unavailable once a valid independent baseline exists.

## Capital auto mode

`capital_intent: {"mode":"auto"}` runs the deterministic capital screen. It:

- derives attraction from measured positioning or an explicitly market-independent
  narrative; price accessibility remains a visible fallback but has
  `leg_independence.attraction=false` and cannot close the loop;
- derives protection from persistent, same-direction cross-book normalized
  movement, falling back to a market-versus-independent residual only when the
  movement path is insufficient;
- derives feasibility only from the market-free score matrix;
- uses cross-book dispersion and time-path noise to set event-specific signal
  thresholds;
- emits the loop state, CI grade, candidate label, non-intent alternative,
  strongest contradiction, falsifier, reorder condition, and diagnostics.

The automated screen never proves manipulation and never directly changes the
score matrix. It is capped at CI-2. A supported direction can reorder only a
candidate already inside the frozen near-tie probability band; the record must
preserve complete `without_capital` and `with_capital` rankings with identical
probabilities. A conflict remains `unresolved`.

Measured positioning is independent only when each row declares a supported
measurement type (`bet_share`, `turnover`, `liability`, or `exchange_volume`),
a distinct source group, licensing basis, and pre-freeze observation time.
Rows missing any field are rejected and counted in diagnostics; a direction
label alone cannot close the attraction leg.

## v1.8 observe-only research and evidence layer

When provider-neutral completed-match history is present, the pipeline also
builds `next_phase_shadow`. Its control is the unchanged v1.6.1 probability
Poisson matrix. Its candidates add opponent/schedule strength, exponential
recency, season-transition downweighting, a fixed unpromoted Dixon-Coles
low-score correction, and a diagnostic uncertainty envelope. Rest days and
source-field coverage are audited; missing optional inputs remain unavailable.

The same artifact emits a research-only capital-threshold multiplier by
declared liquidity tier and time-to-kickoff. It is never applied. Every shadow
artifact must say `observe_only`, zero probability delta, unchanged stable
weights/ranking, and automatic-promotion ineligible. Use
`identity_registry.py` for exact reviewed cross-provider identities; it has no
fuzzy auto-accept path. Freeze and score with:

`python scripts/shadow_model_lab.py freeze HISTORY.json --manifest MANIFEST.json --output NEW_SHADOW.json`

`python scripts/shadow_model_lab.py score SHADOW.json RESULT.json --output NEW_SCORE.json`

Both outputs are append-only. Promotion requires chronological aggregate
evaluation; one event can never promote a model or capital threshold.

Freeze and score sourced non-market adjustment signals, then aggregate only
after the configured sample threshold:

`python scripts/adjustment_calibration_lab.py freeze INPUT.json --output FREEZE.json`

`python scripts/adjustment_calibration_lab.py score FREEZE.json RESULT.json --output SCORE.json`

`python scripts/adjustment_calibration_lab.py calibrate SCORE*.json --output CALIBRATION.json`

Freeze licensed bet-share, turnover, liability, or exchange-volume evidence
separately with `capital_evidence_ledger.py freeze`; odds and credentials are
forbidden in that ledger. Aggregate preregistered post-result shadow scores
with `shadow_cohort_evaluator.py evaluate`. It requires overall primary-metric
improvement, multiple competitions, sufficient samples, and no material
protected-segment regression. Finally use `improvement_completion_tracker.py`
to report engineering and evidence maturity separately. None of these commands
promotes a model or changes a live probability/ranking.

## Historical learning boundary

Read the project's candidate gate before using any historical rule. Rules in
`off` or `observe_only` mode may add a shadow annotation, trigger count,
counterexample, or review priority. They must carry `probability_delta: 0`, must
not change ranking or confidence, and must not be described as learned weights.
Promotion requires a genuinely new chronological frozen holdout and the growth
protocol.

## Deterministic execution

When a structured batch input is available, run:

`python scripts/full_mcm_pipeline.py INPUT.json --output OUTPUT_DIR`

The input contract is demonstrated by
`evaluation/examples/synthetic-full-mcm-batch.json` in the development
repository. The pipeline builds all three probability layers, derives unified
candidate and path outputs from one matrix, records capital and positioning
evidence, attaches historical rules only in safe shadow mode, assigns status,
and writes validated machine records plus a Chinese report. New records derive
checkpoint and final cross-book coverage from SHA-256-bound monitor files, not
from `monitoring` counters in the input. The monitor config must declare
`max_quote_age_minutes` and `late_tolerance_minutes`; each snapshot must
match the fixture, scheduled checkpoint, and 90-minute horizon. Missing
artifacts remain unavailable. Two bookmaker IDs alone are not proof of
economic independence, so retain a separate source-family review.

The output directory must be new and empty. `freeze-manifest.json` is written
last and records hashes of the batch contents, report, validation file, and
each machine record, plus whether the receipt was made before kickoff. Check
it with `python scripts/freeze_manifest.py OUTPUT_DIR`. This checks later file
changes relative to the receipt but does not provide a trusted timestamp or
prevent replacement of both the receipt and files. Do not count a historical
replay as a forward-frozen prediction.

For every source-displayed integer three-way handicap, capture side, line,
timestamp, and the complete three-price outcome row. The live v1.6.3 gate
builds either the complete ordinary-plus-handicap pool or, when ordinary 1X2 is verified not displayed, the complete handicap-only win/draw/loss pool first,
then assigns ranks and takes the top two. Missing one candidate, keeping the
handicap only as evidence, or preselecting two 1X2 outcomes causes validation
failure. An unreadable/unverified displayed handicap blocks the final unified
ranking; it is never silently treated as not displayed.

Run `scripts/sporting_baseline_builder.py --self-test`,
`scripts/independent_score_matrix.py --self-test`,
`scripts/capital_intent_engine.py`, `scripts/identity_registry.py self-test`,
`scripts/shadow_model_lab.py self-test`, `scripts/adjustment_calibration_lab.py self-test`,
`scripts/capital_evidence_ledger.py self-test`, `scripts/shadow_cohort_evaluator.py self-test`,
`scripts/improvement_completion_tracker.py self-test`, and the full-pipeline tests after
changing these mechanics. Treat a non-zero exit or validator error as an
incomplete build, not a successful full report.

Also run `scripts/market_quality.py` with no arguments,
`scripts/evidence_integrity.py`, the freeze receipt verifier, and the
evidence-gate regressions after changing the new process gate. Report each
complete market's overround. Top-two coverage that is true for every possible
margin is an exhaustive union, not evidence of predictive success. Do not
label a selection positive value solely because it has a high ranking or an
evidence-completeness `value_grade`.

## Report completion

The batch table must show both leading alternatives from the unified pool,
their exact settlement boundaries, all four goal-band probabilities, three
score paths, and two half/full paths. The per-fixture section must show all
three probability layers, the complete capital counterfactual, positioning
evidence level, historical-shadow status, strongest contradiction, falsifier,
and reorder condition.

At the end, disclose validator version, fixture status counts, independent
baseline coverage, last observation and missed checkpoints, capital labels,
capital-layer changes, historical mode, and unresolved gaps.

