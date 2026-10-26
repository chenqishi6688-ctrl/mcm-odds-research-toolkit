# MCM Football Compliance Gates v1.4.5

Read this reference before every football final report, monitoring synthesis, or claim that an MCM task is complete. The purpose is to turn existing analytical boundaries into enforceable fixture-level records.

## 1. Report statuses

Assign one status to every fixture before drafting prose:

- **FULL-MCM:** event identity and 90-minute horizon are verified; a non-circular independent baseline was frozen before the audited market; the required market timeline, meaningful cross-book comparison, late observation, capital card, contradiction screen, and probability layers are complete. `FULL-MCM` permits CI-3 and value grade A only when their separate evidence requirements are also met.
- **MCM-DEGRADED:** the independent baseline is available, but one or more material market, monitoring, context, or late-observation gaps remain. Cap value at B and capital intent at CI-2. State every gap.
- **MARKET-STRUCTURE-ONLY:** the independent baseline is unavailable or contaminated by the audited market. Publish market-implied probabilities only; independent and MCM-adjusted layers are unavailable. Cap value at C and capital intent at CI-1. Candidate capital label must be `unresolved` or `none`.
- **BLOCKED:** event identity, home/away orientation, settlement horizon, result scope, or another prerequisite needed for correct settlement is unverified. Do not give a directional or capital-intent conclusion.

For a batch-wide completeness claim, report the count in each status. Never call the whole batch `FULL-MCM` when any included fixture is materially degraded. Individual full fixtures may retain their own status.

For v1.6.3+evidence1 machine records, a `FULL-MCM` monitoring claim additionally needs a SHA-256-bound monitor configuration and every planned snapshot, with actual collection inside its declared window and before kickoff, verified match identity, complete mapped 1X2 quotes, and fresh quotes from at least two distinct bookmaker IDs at the final checkpoint. Counts or booleans supplied by the caller do not prove any of this. Distinct IDs do not by themselves prove independent bookmaker ownership, feed origin, or meaningful economic independence; investigate those separately and downgrade if doubtful. Historical legacy records remain readable but are not retroactively certified by this new gate.

## 2. Hard downgrade matrix

Apply these rules before subjective weighting:

| Condition | Required action |
|---|---|
| Event identity, home/away order, kickoff, or 90-minute horizon unresolved | `BLOCKED` |
| Independent baseline unavailable or uses audited odds | `MARKET-STRUCTURE-ONLY`; adjusted probabilities unavailable; CI <= 1; value <= C |
| Independent baseline exists but cross-book, lineup/context, late snapshot, or required monitoring checkpoint is materially incomplete | normally `MCM-DEGRADED`; explain the exception if status differs |
| Only one provider supplies 1X2, three-way handicap, exact totals, correct score, and half/full-time | treat those rows as one correlated market family, not independent evidence groups |
| Fewer than two independent evidence groups or red-team not passed | capital candidate label must be `unresolved` or `none` |
| Asian two-way orientation or odds format unverified | exclude Asian evidence from direction and set AH-D |
| Three-way integer handicap line or side unverified | omit that candidate; never infer a default line |
| Readable displayed three-way handicap is absent from the complete candidate pool, or one of its win/draw/loss outcomes is missing | validator error; do not publish a final top two or claim completion |
| Required validator returns any error | repair the record or disclose downgrade; do not claim completion |
| Top-two selections cover every possible 90-minute margin | show `guaranteed_at_least_one`; do not present top-two coverage as a predictive hit rate or two independent picks |
| Market overround or de-vigged price differs from model forecast | report the margin and source; do not claim positive value without a separately validated independent probability and applicable break-even price |

Do not automatically upgrade a status because prices agree. Market agreement can improve market-data quality while the independent layer remains unavailable.

## 3. Per-fixture machine record

Persist one JSON object per fixture conforming to [fixture-analysis.schema.json](fixture-analysis.schema.json). Store it beside the task's snapshots or final report. The minimum sections are:

1. `event`: verified identity, teams, kickoff, timezone, and `90m` horizon;
2. `report_status` and `data_quality`;
3. `probabilities`: separately named market-implied, independent, and MCM-adjusted 1X2 and four-band goal distributions;
4. `ordinary_1x2_coverage`, `candidate_pool_scope`, and `unified_ranking`: use the complete ordinary-plus-handicap pool when ordinary 1X2 is displayed, or the complete three-outcome handicap-only pool when ordinary 1X2 is verified not displayed; all ranked alternatives use the same declared probability source;
   `three_way_handicap_coverage`: explicit observed/not-displayed/unreadable state, source time, exact side/line list, and completeness flag;
5. `asian_handicap`: either absent or explicitly separate from the unified table;
6. `capital_intent`: the complete frozen card;
7. `baseline_provenance`: input mode, market-independence proof, source records,
   and builder sample/shrinkage audit or an explicit preaggregated limitation;
8. `ranking_counterfactual`: complete with/without-capital candidate lists,
   unchanged probabilities, declared near-tie gap, application flag, and reason;
9. `value_grade`, `strongest_falsifier`, and `reorder_condition`.

New-engine records also persist `monitoring_evidence`, recomputed `monitoring_audit`, and `market_quality`. The legacy `value_grade` means evidence-completeness cap only, not expected return, edge, or a betting recommendation. Report overround separately per equivalent market and identify guaranteed top-two settlement coverage. Do not calculate apparent model value by comparing an uncalibrated experimental baseline with odds.

Use probabilities on a 0-to-1 scale in the JSON record. Rounded user-facing percentages may use 0-to-100.

## 4. Unified ranking gate

When an independent or adjusted score matrix exists, derive ordinary 1X2 and every actual integer three-way-handicap candidate from that same matrix. Do not compare one candidate using market-implied odds and another using a model probability.

Before ranks are assigned, declare the market scope. `candidate_pool_scope=unified` requires `ordinary_1x2_coverage.status=observed`, all three ordinary outcomes, and all three outcomes for every observed integer handicap. `candidate_pool_scope=handicap_only` requires ordinary status `not_displayed` and at least one verified handicap whose `side_win`, `handicap_draw`, and `side_loss` each appear exactly once. `three_way_handicap_coverage.status=observed` still requires exact equality between its declared side/line set, the selected probability layer's offer set, and the handicap set represented in the ranking. A displayed ordinary market may never be omitted by choosing handicap-only scope. Any displayed but unreadable/unverified required market blocks the final ranking.

When only market prices exist, the table may show a market-implied alternative-selection ranking, but must declare `probability_source: market_implied`, retain `MARKET-STRUCTURE-ONLY`, and avoid calling it an independent MCM choice.

Each three-way-handicap row must include:

- `market_type: three_way_handicap`;
- the exact integer line and which side carries it;
- settlement paths covered by the selection;
- the common probability source used by the whole ranking.

Asian two-way handicap rows are prohibited from `unified_ranking`. They belong only in the separate Asian panel.

For every batch-wide ranking table, require all of the following before calling the output complete:

- the first and second alternatives from each fixture's unified ranking, each with probability or an explicit unavailable state;
- the exact integer handicap, side, and 90-minute settlement boundary whenever either alternative is a three-way-handicap selection;
- separate `0–1`, `2–3`, `4–6`, and `7+` probability columns for every fixture, plus the within-fixture goal-band order;
- wording that the two ranked alternatives are not independent combination legs;
- preservation of the complete unified ranking in the fixture machine record.

A batch table that shows only the first candidate or only the leading goal interval fails the user-facing output gate even when the underlying fixture JSON is valid.

## 5. Capital-intent gate

Freeze the complete card per match before kickoff. A capital label beyond `unresolved` requires all of the following:

- independent sporting baseline available and frozen before the audited odds;
- CI-2 or CI-3 under `capital-intent.md`;
- at least two genuinely independent evidence groups;
- red-team screen passed;
- a non-intent alternative and strongest falsifier recorded;
- final direction with and without capital recorded.

A `closed` loop additionally requires `leg_independence.attraction`,
`leg_independence.protection`, and `leg_independence.feasibility` all to be
true. `market_price_accessibility` is never an independent attraction leg and
cannot support `inducement_candidate`.

Allowed labels:

- `straight_support_candidate`: independent sporting and broad market-margin paths cohere without a critical contradiction;
- `inducement_candidate`: a narratively attractive path conflicts with a defensible fair baseline and at least one independent resistance or margin-path group;
- `upset_candidate`: the independent baseline assigns materially more probability to a draw or underdog path and independent market structure supports that residual;
- `unresolved`: rival explanations survive;
- `none`: no meaningful capital hypothesis is present.

These are operational hypothesis labels, not causal facts. Never use `confirmed manipulation`, `fixed result`, or an equivalent claim.

## 6. Validation command

Before final delivery, run:

`python scripts/validate_report.py <fixture-record.json> [<fixture-record-2.json> ...]`

The command returns non-zero when any hard rule fails. `--self-test` runs built-in passing and failing regression cases. Preserve validator output in the task directory when practical.

The v1.6.3+evidence1 validator rejects missing baseline provenance, unaudited adjusted
layers, false closed-loop independence, and capital rankings that change
probabilities or jump outside their near-tie band. It also rejects missing
three-way-handicap coverage declarations, partial ordinary 1X2 pools, and any
observed integer-handicap offer whose win/draw/loss candidates are incomplete.
It checks structure and
internal consistency; it does not prove that the independent inputs are
accurate, that the capital hypothesis is causal, or that the prediction will
be correct.

The pipeline writes `freeze-manifest.json` after all other artifacts. Run `python scripts/freeze_manifest.py OUTPUT_DIR` to check its artifact inventory and hashes. It is a local checksum receipt, not a digital signature or trusted timestamp; preserve an external copy if a stronger prospective freeze is needed. A report produced after kickoff cannot enter the prospective cohort merely because its input contains an earlier `analysis_freeze_time`.

## 7. User-facing completion block

End every final report with:

- validator version and pass/fail;
- fixture counts by status;
- last observation time and missed checkpoints;
- independent-baseline coverage count;
- capital labels and whether the capital layer changed any first choice;
- unresolved data gaps.

If validation failed, use `validation failed — report not complete` or state the explicit downgrade. Do not say `task completed` without qualification.

