# Capital-Intent Evidence Protocol

## Purpose and boundary

Capital intent is a core MCM differentiator for interpreting how market makers and aggregated betting markets may be managing information, liability, price discovery, and bettor demand. It is not a directly observed mental state and must never be reported as proof of manipulation, a predetermined result, or a guaranteed hidden answer.

The objective is to test whether observable market structure adds incremental predictive information—especially for 90-minute 1X2 and handicap direction—beyond sporting evidence and the latest consensus probability.

## Three-way triangulation

Capital intent is not a fourth opinion layered on top of the match. It is the inference produced when three equal-status layers corroborate one another:

1. **Attraction/exposure:** which result or path is narratively easy to buy, visibly promoted, price-accessible, or—only when measured—receiving concentrated demand.
2. **Protection/resistance:** which result or path the line, normalized price, key-number resistance, cross-book behavior, and correlated markets consistently protect or refuse to release.
3. **Sporting/path feasibility:** whether team strength, availability, incentives, tactics, likely game states, goal band, half/full-time routes, and score paths make the inferred market outcome operationally plausible.

Do not permanently rank one layer above the others. Each must challenge and refine the other two. The capital conclusion is the intersection of the three layers, not whichever layer has the most dramatic observation.

Use these statuses:

- **Closed loop:** all three layers independently point to a compatible direction and the contradictions are explainable.
- **Partial loop:** two layers align while the third is unknown or data-limited. Keep the inference provisional and do not make it the sole primary call.
- **Broken loop:** one layer directly contradicts the other two. Show the conflict, downgrade the CI grade, and retain competing scenarios.
- **No loop:** evidence is too sparse or unrelated to triangulate.

For machine records use `closed`, `partial`, `broken`, or `none`; `none` is the
machine equivalent of no loop.

## Required frozen calls

For every eligible match, record before kickoff:

1. market-only baseline direction;
2. sporting/context baseline direction;
3. attraction/exposure direction and evidence;
4. protection/resistance direction and evidence;
5. sporting/path feasibility direction and evidence;
6. triangulation status and capital-intent direction for 1X2 and, when available, handicap;
7. combined final direction;
8. final direction with the capital-intent layer removed;
9. evidence grade, timestamp, strongest support, strongest contradiction, and falsifier.

Never reconstruct a missing pre-match call after seeing the result.

Use the machine-readable frozen card defined by `fixture-analysis.schema.json` for every fixture. The minimum fields are attraction/exposure, protection/resistance, sporting/path feasibility, loop status, CI grade, direction without capital, direction after capital, incremental impact, strongest contradiction, reorder condition, evidence groups, red-team result, and candidate label. A batch summary cannot substitute for a fixture card.

## Observable evidence groups

Use multiple independent groups and avoid double-counting correlated prices:

- **Probability path:** overround-normalized opening, intermediate, latest, and late probability; velocity, reversal, persistence, and closing position.
- **Line structure:** handicap or total line changes versus price-only changes; resistance at key lines; suspension and reopening.
- **Cross-market coherence:** 1X2, handicap, goal band, correct score, half/full-time, team totals, BTTS, and qualification where relevant.
- **Cross-book structure:** breadth, dispersion, leader/follower behavior, stale quotes, and whether the move is consensus or isolated.
- **Timing and information:** relationship to lineup, injury, weather, schedule, or other verifiable news windows.
- **Positioning evidence:** exchange price/volume, turnover, bet share, or liabilities when directly available. Without these, use “narratively attractive” rather than “crowded money.”

## Evidence grades

- **CI-0 — unavailable:** insufficient timeline, unreadable orientation, or no usable comparative market.
- **CI-1 — suggestive:** one triangulation layer or a single market pattern is present; record it but do not change the primary direction.
- **CI-2 — supported but provisional:** at least two triangulation layers align, the market move survives margin normalization, and the third layer is unknown rather than contradictory. It may promote a scenario to co-primary or act as a tie-breaker, but cannot be the sole reason for the final call.
- **CI-3 — closed-loop support:** attraction, protection, and sporting/path feasibility all independently align; market evidence is broad or persistent across meaningful windows; and no critical contradiction remains. Direct positioning evidence strengthens CI-3 but is not mandatory when cross-book and cross-market confirmation is independently strong. It may become a primary directional input, but remains probabilistic.

If evidence groups or triangulation layers conflict, mark a broken loop and downgrade rather than average away the contradiction.

## Automated hypothesis screen

The v1.6.1 deterministic screen is an admissible way to populate a capital
card when its inputs are frozen. It first de-vigs every 1X2 observation, keeps
each bookmaker's time path separate, and computes cross-book dispersion,
signed movement and market-minus-independent residuals. Protection requires a
persistent same-direction move across at least two books above event-specific
noise, or—when that path is absent—a cross-book residual above a threshold
derived from dispersion and time noise. There is no universal percentage-point
cutoff.

Attraction prefers directly measured positioning. Media or public narrative
can infer only the **narratively attractive direction**, not real money flow.
It counts as an independent attraction leg only after
`scripts/media_narrative_evidence.py` verifies a pre-kickoff freeze, full source
provenance, at least two independent non-market publisher/source groups, and at
least two non-syndicated content families. A two-thirds directional consensus
is required; single-source, copied, conflicting, post-freeze, or market-derived
rows remain unavailable. Price accessibility is retained as a fallback
direction but is explicitly non-independent and can never close the loop or
confirm inducement. Feasibility must come from the market-free score matrix.
The screen then records one of:

- `supported`: protection and independent feasibility agree while attraction
  points elsewhere;
- `inducement_rejected_by_current_evidence`: all three point in the same
  direction, supporting a straight-support candidate instead;
- `unresolved_conflict`: protection and feasibility disagree;
- `unresolved_attraction_not_independent`: protection and feasibility align,
  but the attraction leg is derived from the audited market family;
- `unresolved`: evidence does not clear the threshold.

These statuses confirm or reject only the operational hypothesis under the
frozen evidence, never an actor's hidden motive. Automatic cards are capped at
CI-2; CI-3 requires a human-reviewed freeze and every FULL-MCM gate.

Store frozen narrative artifacts separately from licensed measured-positioning
artifacts. They may complete the attraction leg of an operational three-way
capital hypothesis, but `counts_toward_licensed_capital_target` must remain
false and they never satisfy the 30-event measured-capital completion target.

An independent sporting baseline is required for any candidate motive label and for sporting/path feasibility to count as an independent leg of the capital loop. Without it, the report is `MARKET-STRUCTURE-ONLY`, CI is capped at CI-1, and the label must be `unresolved` or `none`; correlated market score paths do not become an independent sporting leg merely because they are plausible.

Permitted candidate labels are:

- `straight_support_candidate`;
- `inducement_candidate`;
- `upset_candidate`;
- `unresolved`;
- `none`.

The first three require CI-2 or CI-3, an available independent baseline, at least two genuinely independent evidence groups, and a passed red-team check. Even then, write them as structural hypotheses and never as a fact about bookmaker intention.

## Competing causal explanations

For every capital-intent inference, compare at least these explanations:

- genuine new information;
- bookmaker risk or liability balancing;
- model-driven probability repricing;
- bettor-demand shading;
- stale or copied prices;
- margin/return-rate adjustment;
- low-liquidity noise;
- data-provider mapping or orientation error.

“Inducement,” “protection,” and “cold storage” are scenario labels, not observed facts. Prefer the explanation that accounts for the most independent evidence with the fewest unobserved assumptions.

For Asian two-way handicap evidence, follow `asian-handicap.md`. Verify odds format and orientation, compare the offered line with a frozen fair-line band, separate line/price/margin movement, and model whole/half/quarter settlement correctly. A descriptive high/low-water label or a single deep/shallow/升降盘 pattern is only one protection-resistance observation; it cannot independently establish capital intent or funded exposure.

## Direction decision rule

Capital intent is most relevant to 90-minute 1X2 and handicap direction. Exact score and half/full-time markets are supporting path evidence and must not dominate direction because their prices are sparse, high-margin, and often mechanically derived.

At CI-2 or CI-3, report:

- inferred narratively attractive direction;
- inferred protected or resisted direction;
- sporting and score-path support or conflict;
- triangulation status;
- which popular settlement paths would lose under the capital scenario;
- how the final ranking changes when the capital layer is removed.

The counterfactual is an ordering audit, not a probability rewrite. Preserve
the complete probability-sorted ranking as `without_capital`. Capital may move
an aligned candidate to first only when CI is at least 2, the red-team screen
passed, and its probability lies within the declared dynamic near-tie gap
(hard ceiling 5 percentage points). Preserve every candidate and probability
unchanged in `with_capital`; otherwise record `applied: false` and the reason.

## Validation and method screening

Maintain an append-only sample. Evaluate the capital layer separately with hit rate only when the sample and metric were frozen in advance; also use log loss, Brier or ranked probability score, calibration, and incremental performance versus opening and closing consensus.

Use chronological walk-forward testing and segment results by competition type, league liquidity, bookmaker coverage, time-to-kickoff, evidence grade, favorite strength, and market type. Include all misses and voids. Do not select thresholds on the test set or promote a rule because it explains one famous match.

Candidate method families include de-vig methods, probability-path and reversal features, line/price decomposition, cross-book dispersion and lead-lag, correlated-market residuals, news-window controls, and calibrated statistical or machine-learning models. A method enters the core workflow only when it improves out-of-sample calibration or directional performance without unacceptable regression in established segments.

User-supplied historical World Cup cases are valuable candidate evidence. Record them faithfully, but classify claimed high hit rate as unverified until the original pre-match calls, full case list, misses, timestamps, and denominator are available for audit.

## Review fields

After resolution, record capital-direction hit/miss/push, each of the three frozen layer calls, triangulation status, CI grade, whether the capital conclusion changed the combined call, whether that change helped, and the main cause. Review which link in the triangle failed instead of rewriting all three after the outcome. Distinguish a correct direction from a correct causal explanation: outcome agreement alone does not validate the inferred motive.

