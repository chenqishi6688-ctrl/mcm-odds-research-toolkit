# Asian Handicap Evidence Protocol

## Purpose and boundary

Use this reference whenever football analysis contains an Asian two-way handicap (亚盘), handicap-line movement, or “water”/price movement. It converts those observations into testable market signals without treating bookmaker motive, “诱盘”, or “阻盘” as observed fact.

Asian two-way handicap is not the same market as the three-way integer handicap win/draw/loss used by Chinese sports-lottery sources. Do not place Asian two-way selections inside the unified ordinary-1X2/three-way-handicap candidate pool. It may inform that ranking as supporting evidence. If the user explicitly requests an Asian-handicap selection, report it in a separately labelled settlement row.

## 1. Input and notation gate

Record before interpretation:

- event, kickoff, 90-minute settlement scope, home/away order, and the side carrying the handicap;
- bookmaker/source, timestamp/timezone, opening/intermediate/latest/late snapshots, and whether a quote was suspended or reopened;
- exact line at each snapshot, including quarter lines such as `-0.25`, `-0.75`, `+0.25`, or `+0.75`;
- both sides' prices and the odds format: decimal, Hong Kong, Malay, Indonesian, or another explicitly documented format;
- 1X2, totals, team totals, correct-score, lineup/news windows, and cross-book comparators when available.

Never infer orientation or odds format from the numeric range alone. In this protocol, “favorite/让球方” is the side conceding the handicap and “underdog/受让方” is the other side; “上盘/下盘” may be quoted only after the source orientation is verified.

Minimum evidence grades:

- **AH-A:** verified orientation and odds format; opening, intermediate, latest, and late snapshots; both sides; several independent books; correlated markets and news windows.
- **AH-B:** verified orientation/format and at least three useful snapshots with both sides; minor cross-book or context gaps.
- **AH-C:** one or two snapshots, one-sided prices, incomplete timing, or no reliable baseline. Describe only; do not infer inducement/protection.
- **AH-D:** unreadable orientation, unknown odds format, mismatched event, or stale/contradictory mapping. Exclude from direction.

## 2. Odds conversion and settlement

For Hong Kong odds `h`, decimal odds are `1 + h`. For decimal odds `d`, raw implied probability is `1 / d`. When both sides of the same two-way line are quoted, normalize their raw probabilities by their sum before comparing snapshots. Use the documented conversion for Malay or Indonesian odds; if the format is unknown, do not convert or compare numerically.

Do not compare raw “water” across different handicap lines as though it were the same outcome. A move from favorite `-0.5 @ 0.80` to `-0.75 @ 1.00` changes both the settlement set and the price. Decompose line and price first; compare equivalent score-path value only with an explicit score-margin distribution or mark the cross-line price comparison qualitative.

For a selected side with handicap `h`, let `d = selected-side 90-minute goals - opponent goals` and evaluate `d + h`:

- positive: win;
- zero: push;
- negative: loss.

Half lines have no push. Quarter lines split the stake equally across adjacent half-step lines:

- `-0.25` = half at `0`, half at `-0.5`;
- `-0.75` = half at `-0.5`, half at `-1`;
- `+0.25` = half at `0`, half at `+0.5`;
- `+0.75` = half at `+0.5`, half at `+1`.

Report full win, half win, push, half loss, and full loss separately when relevant. A single “win probability” can mislead on whole or quarter lines; use expected return only when the score-margin distribution and actual price support it.

## 3. Establish a fair-line band

“Deep” or “shallow” is relative, not a property of a line in isolation. Freeze a fair-line **band** before reading motive into the offered line. Build it from as many independent inputs as possible:

1. de-vigged 1X2 probability and draw mass;
2. team-strength or expected-goal baseline adjusted for venue;
3. verified lineup, rest, motivation, weather, and tactical matchup;
4. comparable closing markets against similar opponents;
5. totals and likely score-margin distribution.

Record the band and uncertainty. If team reputation is the only reason a line “should” be deeper, mark the baseline weak. An offered line inside a wide uncertainty band is “compatible,” not definitively deep or shallow.

Do not use the document-derived statements “shallow + high water is 90% inducement” or “shallow + low water is 99% inducement.” Those percentages have no frozen sample, denominator, odds-format control, or out-of-sample validation.

## 4. Decompose every move

For each snapshot transition, record five separate components:

1. **Line direction:** favorite line strengthens, weakens, or is unchanged.
2. **Same-line price direction:** favorite normalized price shortens, drifts, or is stable.
3. **Margin change:** whether bookmaker return changed enough to explain part of the raw price move.
4. **Breadth and persistence:** consensus across independent books versus isolated/stale/copying behavior; one-way persistence versus reversal.
5. **Timing and information:** opening discovery, limits/liquidity change, verified news, lineup window, or late market.

Do not hard-code `±0.02`, `±0.03`, or a fixed 1–2 hour cutoff as universal thresholds. Judge movement relative to that book's tick size, recent volatility, liquidity, line boundaries, and cross-book behavior.

## 5. Neutral pattern matrix

Use the following patterns to generate competing explanations, never a single deterministic verdict.

### A. Line compatible/deeper than fair band; favorite price high or drifting

- Candidate source label: “高水阻上” or “深盘阻上”.
- Supportive hypothesis: the line itself protects the favorite outcome while a less attractive price or harder margin discourages entry.
- Alternatives: favorite risk is genuinely higher; margin changed; low liquidity; stale quote; the fair-line band is too optimistic.
- Confirmation: broad/persistent line strength, no material sporting negative, 1X2 and score-margin paths remain supportive, and late market does not release the line.
- Invalidators: shallow-to-baseline line, verified favorite negative, isolated book, repeated line retreat, or correlated markets weakening the favorite.

### B. Line shallow versus a reliable fair band; favorite price high/rising

- Candidate source label: “高水诱上” or weak favorite.
- Main signal: market is charging a higher return without supplying the expected handicap protection.
- Alternatives: fair-line estimate is wrong; draw probability is unusually high; limits or team news are unresolved.
- Confirmation: multi-book shallow line, persistent favorite drift after normalization, and 1X2/score paths fail to support margin victory.
- Invalidators: later consensus line strengthening, verified positive information, or strong correlated-margin support.

### C. Line compatible/deeper than fair band; favorite price low and stable

- Candidate source label: “低水阻上” or genuine favorite support.
- Main signal: bookmaker maintains a demanding line while keeping the favorite price compressed.
- Alternatives: ordinary consensus repricing, lopsided demand, reduced margin, or copied prices; low return is not proof of deliberate deterrence.
- Confirmation: cross-book stability, strong margin paths, no adverse news, and no late line release.
- Invalidators: shallow baseline, continuous price collapse without line response, or totals/score markets inconsistent with covering.

### D. Line shallow versus a reliable fair band; favorite price low/falling

- Candidate source label: “低水诱上” or cheap favorite.
- Main signal: price advertises safety while the line withholds the expected margin requirement.
- Alternatives: draw protection is being priced correctly; the side may win narrowly; fair-line or orientation error.
- Confirmation: line refuses to strengthen across books despite sustained price shortening and favorable public narrative; margin-score paths remain weak.
- Invalidators: line subsequently strengthens coherently, the fair-line band moves shallower on verified news, or score paths support a narrow but still covering outcome.

### E. Favorite line strengthens

Treat “升盘阻上” and “升盘诱上” as rival hypotheses.

- Stronger protection hypothesis gains weight when the move is broad, persistent, late or post-information, and supported by 1X2 plus margin-score paths.
- Attraction/rebalancing hypothesis gains weight when the new line is paired with unusually generous favorite pricing, the move is early/low-limit or isolated, and 1X2 fails to strengthen.
- A stronger line with lower favorite price can reflect genuine probability change, public demand, or model repricing; it is not automatically either support or inducement.

### F. Favorite line weakens

Treat “降盘诱下” and genuine favorite weakening as rivals. Also test whether the new line reduces the underdog's settlement cushion, as described by the source's “降盘阻下” hypothesis.

- Favorite-support hypothesis after a line drop requires continued 1X2/margin-path support, high or unattractive favorite pricing, and evidence that the underdog's safer settlement set has actually narrowed.
- Genuine weakening gains weight when the move is broad, persistent, tied to verified adverse information, and confirmed by 1X2 and score paths.
- Early versus late timing is evidence, not a verdict. Early moves may reflect low-limit discovery; late moves may reflect news, liquidity, or liability.

### G. Reverse favorite

When the nominally weaker or less famous side gives the handicap, first test whether the label “weaker” survives venue, lineup, rest, tactical, and de-vigged 1X2 evidence. If it does, record the reverse line as a contradiction requiring explanation. Do not automatically oppose the famous side or call the line a trap.

## 6. Attraction–protection–feasibility integration

Map Asian-handicap evidence into the existing capital-intent triangle:

- **Attraction/exposure:** brand favorite, accessible shallow line, visually high payout, visually low “safe” price, recent streak, public narrative. Without bet-share or turnover data, call this “narratively attractive,” not funded exposure.
- **Protection/resistance:** fair-line deviation, line-boundary resistance, cross-book breadth, price after de-vigging, suspension/reopen behavior, and whether correlated margin paths are released or protected.
- **Sporting/path feasibility:** score-margin distribution, totals, lineups, tactics, fatigue, likely game state, and whether the side can cover the actual line rather than merely win the match.

An Asian-handicap pattern may raise capital-intent evidence above CI-1 only when it survives the input gate, fair-line test, cross-book/timing controls, and correlated-market check. It cannot create CI-2/CI-3 by itself.

## 7. Required analysis record

When usable Asian-handicap data exist, freeze:

1. exact line/orientation and settlement map;
2. odds format and de-vig method;
3. fair-line band and uncertainty;
4. opening/intermediate/latest/late line-price sequence;
5. pattern code A–G and the source-derived label, if used;
6. primary non-intent explanation;
7. inducement/protection hypothesis;
8. cross-book, 1X2, totals, and score-path confirmation or conflict;
9. data grade AH-A through AH-D;
10. conclusion with and without Asian-handicap evidence;
11. strongest falsifier and what change would reorder the call.

If the user-facing report recommends an Asian two-way selection, state the side, exact line, price, odds format, timestamp, full settlement outcomes, estimated full/half win-push-loss distribution when available, evidence grade, and strongest contradiction. Do not promise a return or translate it into a three-way handicap outcome.

## 8. Post-result review and controlled learning

Freeze the pre-match pattern and rival explanations. Score settlement, expected-value calibration, whether the Asian layer changed the final direction, and whether that change helped. A matching result validates only the result path, not the claimed bookmaker motive.

Track pattern A–G by data grade, competition liquidity, time window, odds format, line band, cross-book breadth, and news status. Promote a predictive heuristic only after chronological testing against independent frozen cases and appropriate controls. The source document's final single-match example is anecdotal candidate evidence only; it cannot establish a rule or performance claim.

## Source integration status

This protocol was distilled from the user-supplied `亚盘拆解.docx` on 2026-08-27. Accepted as core: terminology checks, line/price separation, fair-line comparison, timing, cross-book confirmation, correlated-market comparison, and explicit invalidators. Retained only as hypotheses: “阻上/诱上/诱下/阻下” motive labels. Rejected as core evidence: fixed 90%/99% claims, universal water cutoffs, and single-case causal proof.

