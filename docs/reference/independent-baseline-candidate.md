# Independent sporting baseline — v1.5.0 candidate

Status: **experimental candidate, not a validated core MCM predictor**.

v1.6.0 adds an operational input builder, not a predictive-weight promotion.
`scripts/sporting_baseline_builder.py` accepts frozen provider-neutral completed
match rows, prefers xG when complete, otherwise uses 90-minute goals with lower
reliability, enforces minimum league and venue samples, and applies transparent
empirical-Bayes shrinkage toward league home/away rates. It emits both the
candidate input and an audit object containing raw/shrunk rates, samples,
credibility weights, limitations, and anti-circularity status.

Use this module only when the task explicitly builds or tests the v1.5.0 candidate. The accepted v1.4.2 core may consume a properly frozen independent baseline, but it must not pretend this candidate is validated merely because the tool runs.

## Purpose and anti-circularity boundary

Build one pre-market sporting baseline from team and competition information that does not use the audited bookmaker or lottery prices. The audited 1X2, Asian handicap, three-way integer handicap, exact-score, total-goal, and half/full-time markets are excluded from baseline construction.

Allowed baseline inputs include:

- pre-match home/away expected-goal for and against rates;
- competition home/away scoring environment frozen before the market observation being audited;
- verified availability, rest, travel, tactical, venue, and schedule adjustments with source and freeze time;
- explicitly recorded shrinkage or sample-quality controls.

Disallowed baseline inputs include:

- any odds, market-implied probability, bookmaker handicap, lottery line, price move, or closing price from the match being analysed;
- post-result statistics, line-ups learned after the freeze time, or any information that would not have been available at prediction time;
- reverse-engineered expected goals chosen to reproduce the market.

If the allowed inputs are missing, stale, orientation-ambiguous, or too sparse, do not invent lambdas. Mark the independent baseline unavailable and apply the v1.4.2 `MARKET-STRUCTURE-ONLY` downgrade.

## Candidate input contract

The experimental calculator expects a JSON object containing:

- `candidate_version: "1.5.0-candidate"`;
- event identity and `freeze_time`;
- `uses_audited_market: false`;
- at least two source records with source name, observed time, and metric group;
- league home/away goal rates;
- home-team home xGF/xGA and away-team away xGF/xGA;
- optional home and away lambda multipliers, each with a source-backed reason when not equal to 1;
- the actual Chinese lottery integer handicap offers to derive, limited to ±1 or ±2 and an explicit home/away granting side.

Source count alone does not establish independence. Two pages repeating the same feed are one evidence group.

## Candidate derivation

The reference tool uses a transparent league-normalised Poisson candidate:

`lambda_home = home_xgf_home × away_xga_away ÷ league_home_xg`

`lambda_away = away_xgf_away × home_xga_home ÷ league_away_xg`

Documented pre-market multipliers may then adjust each lambda. The tool creates one joint score-probability matrix and derives from that same matrix:

- ordinary 90-minute home/draw/away;
- every supplied Chinese three-way integer handicap outcome;
- total-goal bands `0-1`, `2-3`, `4-6`, and `7+`;
- the highest-probability exact scores.

Do not derive these outputs from separate ad hoc formulas. Their shared matrix is the acceptance condition for cross-market coherence.

## Relationship to market evidence

After freezing this independent output, MCM may compare it with market-implied probabilities and apply an explicitly justified adjustment. The market is evidence about pricing, resistance, consensus, disagreement, and possible selection pressure; it is not the source of the independent lambdas.

Store all three layers separately:

1. market-implied;
2. independent sporting baseline;
3. MCM-adjusted.

Never overwrite one layer with another. A matching market and baseline is agreement, not proof of a bookmaker motive. A disagreement is a hypothesis-generating signal, not automatic evidence that the market is wrong.

## Candidate acceptance gates

The v1.5.0 candidate remains outside the core until it has:

- chronological frozen tests with no result leakage;
- at least one successful control case and one failed/opposite-signal case;
- calibration and log-loss/Brier comparisons against the de-vigged market baseline;
- separate checks for goal bands, 1X2, and actual ±1/±2 three-way handicap outcomes;
- evidence that any MCM adjustment adds value over the independent baseline rather than merely following the market;
- documented failure modes and rollback criteria.

Do not promote the candidate because of a single correct score or a short winning streak.

## Reference tool

Run:

`python scripts/independent_score_matrix.py input.json --output baseline.json`

Run its deterministic tests:

`python scripts/independent_score_matrix.py --self-test`

The output is labelled `experimental: true` and must not be described as a validated v1.5.0 model.

