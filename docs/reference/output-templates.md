# Output Templates

## Mandatory v1.6.3+evidence1 acceptance header and footer

For structured complete runs, use `scripts/full_mcm_pipeline.py`. Its report and per-fixture machine records retain the market-implied, independent-baseline, and MCM-adjusted layers; baseline provenance and sample audit; zero or applied adjustment deltas; coherent score-matrix outputs; capital counterfactual and hypothesis status; positioning evidence level; and safe historical shadow metadata.

Every final report begins with a per-fixture status summary showing `FULL-MCM`, `MCM-DEGRADED`, `MARKET-STRUCTURE-ONLY`, or `BLOCKED`, together with the reason for every non-full status. Batch wording must not imply that all fixtures are full when any fixture is degraded.

Every fixture, including compact batch rows, must preserve a frozen capital card containing:

- attraction/exposure direction and evidence;
- protection/resistance direction and evidence;
- sporting and score-path feasibility;
- loop status and CI grade;
- direction without capital;
- direction after capital;
- pre-match incremental impact (`changed`, `strengthened`, `weakened`, `none`, or `unavailable`); after settlement, score that frozen change separately as positive, negative, or no realised impact;
- strongest contradiction and reorder condition;
- candidate label and independent evidence-group count.
- inducement hypothesis status and data-dependent diagnostics when auto mode is used.

A batch-level capital paragraph does not replace these cards.

Generate one machine-readable record per fixture conforming to `fixture-analysis.schema.json`, then run `scripts/validate_report.py`. End the report with validator result, checked-record count, independent-baseline coverage count, status counts, omitted/blocked outputs, and unresolved data gaps. If validation fails, do not state that the task is fully complete; repair it or disclose the downgrade.

For new runs, include the number of verified artifact-bound checkpoints, the final valid quote time, distinct bookmaker IDs and any source-independence caveat. Include the local `freeze-manifest.json` verification result and whether its receipt was created before kickoff; never describe a local receipt as a trusted timestamp. Give overround for each complete comparable market, mark expected value unproven without a calibrated independent probability, and state when the first two alternatives' union covers every possible result. Legacy `value_grade` describes evidence completeness, not a positive-return estimate.

## Full pre-event analysis

1. Scope and data quality: event, horizons, sources/timestamps, grade, missing items.
2. Independent baseline: direction, event range, scenarios, confidence.
3. Context/task layer.
4. Normalized market time series.
5. Team/event evidence.
6. Narrative/positioning map.
7. Contradictions and competing explanations.
8. Capital-intent panel: frozen 1X2/handicap direction; attraction evidence; protection evidence; sporting/path feasibility; triangulation status; CI grade; competing explanations; strongest falsifier; conclusion without this layer.
9. Asian-handicap evidence panel when present: exact line/orientation; odds format; opening/intermediate/latest/late sequence; fair-line band; neutral pattern A–G; AH grade; source-derived “诱/阻” hypothesis and non-intent alternative; correlated-market confirmation; conclusion without this layer.
10. Scenario ranking: mainstream, contrarian, tail.
11. Layered conclusion: direction; event band; scores/paths; qualification separately.
12. Red-team result: strongest falsifier and reorder condition.
13. Feedback request.

Before the directional and event-range conclusions, include a probability-separation table with columns for `market-implied`, `independent baseline`, and `MCM-adjusted`. State the input source and freeze time for each numeric column. If the independent baseline is unavailable, show `unavailable` for both it and the adjusted column, label the report `MARKET-STRUCTURE-ONLY`, and do not promote the market-implied number as the model's final probability.

When the independent baseline exists but no frozen non-market adjustment qualifies, the MCM-adjusted column must repeat the independent matrix and show `zero adjustment / no_qualifying_adjustment`; this is a valid audited conclusion, not an unavailable layer. Show the sporting metric, league/team sample sizes, reliability, and shrinkage weight beside the baseline provenance.

Add an inducement/protection screen that lists the mainstream explanation, competing inducement/protection hypothesis, at least one non-intent alternative, evidence-group count, discriminator, and whether the hypothesis is confirmed, rejected, or unresolved. Mechanically related prices from one provider do not count as independent confirmation.

For the directional conclusion, include one unified ranking table containing both ordinary 1X2 and exact three-way-handicap selections. Use only the handicap line actually displayed by the source, dynamically supporting `+1`, `-1`, `+2`, `-2`, or another explicit integer line. Each row states the selection, exact handicap/orientation when applicable, covered 90-minute settlement paths, estimated probability or probability band, evidence grade, strongest contradiction, and rank. The first row is the overall primary selection even when it is a handicap option rather than an ordinary 1X2 result.

Before rendering that table, show or persist the coverage audit: `ordinary_1x2_coverage`, source timestamp, every observed integer line and side, `candidate_pool_scope`, and `candidate_pool_complete=true`. With `unified` scope, require all three ordinary outcomes and all three handicap outcomes for each line. With `handicap_only` scope, require ordinary status `not_displayed` and rank all three handicap outcomes. The top two must be sliced from the completed scope. A template or builder that omits any displayed market family fails the gate. If a displayed market is unreadable or unverified, do not issue a final top two for that scope.

For a multi-fixture final report, the batch-wide ranking table must show the first and second unified-pool alternatives for every fixture, with probability and settlement boundary for both. The two columns are alternative choices, not combination legs. The same row must also contain the four goal-band probabilities (`0–1`, `2–3`, `4–6`, `7+`) and their within-fixture order. Keep all columns present when data is unavailable and state the reason explicitly. The per-fixture machine record continues to preserve the full unified ranking.

Do not put Asian two-way handicap outcomes into that unified table. When the user requests an Asian-handicap recommendation, add a separate row stating side, exact line, price and odds format, timestamp, full/half win-push-loss settlement, estimated outcome distribution or expected value when supported, AH evidence grade, and strongest contradiction. If the Asian market is only being used as supporting evidence, keep it in the Asian-handicap panel and do not present it as an extra independent selection.

For the event-range conclusion, always show all four 90-minute goal intervals—`0–1`, `2–3`, `4–6`, and `7+`—with a percentage for each and a highest-to-lowest ranking. Label the de-vigged exact-total distribution as `market-implied`, give the source timestamp, and state the calculation method briefly. If a separately frozen non-circular model exists, show its four probabilities and the MCM-adjusted distribution in separate columns. If it does not exist, mark those columns unavailable rather than copying the market distribution. Do not output only a main and secondary interval. If the required inputs are incomplete, show the four entries as unavailable with the reason instead of manufacturing percentages.

## Compact update

State new timestamped data, changed assumption, revised ranks, unchanged conclusions, current falsifier, and feedback request.

## Post-result review

Use a table with rows for Direction, Capital direction, Direction without capital layer, Asian handicap when used, Direction without Asian layer, Event range, Exact path, Qualification, and Confidence; columns for Original call, Outcome, Grade, and Cause. State whether the capital and Asian layers separately improved, worsened, or did not change the direction call. For Asian handicap, preserve the frozen pattern code and settle full/half win-push-loss correctly; do not backfill a motive after the result. Then give process violations, surviving rules, candidate learning, regression cases, version decision, and feedback request.

Add a mandatory actual-result trajectory audit for every resolved fixture. Freeze and display the observed timestamps; then substitute the actual 90-minute score back into the pre-match timeline and record:

- the direct correct-score price at opening, every available intermediate observation, latest, and late/cutoff observation;
- the actual exact-total price and its four-band membership, including whether the related goal band strengthened, weakened, stayed neutral, or was unavailable;
- the ordinary 1X2 path, the exact Chinese three-way integer-handicap settlement boundary, and the actual half/full-time path across the same available timeline;
- whether the direct score and related markets supplied direct support, correlated-only support, a stable/hidden tail, or a contradiction;
- the strongest non-intent explanation and the strongest counterexample to any capital-intent interpretation.

Do not infer that an outcome was deliberately hidden merely because its exact-score price stayed flat or drifted while a related goal band shortened. Likewise, do not treat a shortened losing score as proof of inducement. Without independent turnover/positioning or cross-provider evidence, describe these only as market-structure or capital-intent candidate explanations. If a market or timestamp is missing, mark that cell unassessable; never interpolate or reconstruct a trajectory after seeing the result.

When the result arrives as a screenshot for fixtures previously handled, run this template automatically without requiring the user to paste a separate review command. Also audit the frozen unified 1X2/three-way-handicap ranking: identify the highest-ranked winning selection, whether the overall first choice won, and whether a broader handicap alternative would have ranked above separate 1X2 paths under the frozen evidence. Never optimize or reorder the pre-match list after seeing the result.

## Non-football translation

Map odds timeline to price/probability/sentiment timeline; direction to primary outcome; goal range to event magnitude; correct score to exact scenario; qualification to terminal outcome; crowd narrative to consensus story. Retain the evidence labels, contradiction matrix, scenario ranking, red team, and review.

## Required closing prompt

“这次分析中，哪部分最有用、哪项证据或情景被遗漏、你希望下版具体改什么？如果赛果已出，也请给我结果与关键过程，我会按方向、事件区间、比分路径和置信度分别复盘；反馈会先验证，再决定是否升级 Skill。”

