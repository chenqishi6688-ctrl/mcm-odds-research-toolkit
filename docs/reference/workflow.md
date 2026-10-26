# MCM Workflow v1.0

## 1. Input gate

Record event identity, date, venue, settlement horizon, rules, first-leg state, source/bookmaker, timestamps/timezone, market orientation, team evidence, narrative evidence, and—only for reviews—the outcome. Flag unreadable screenshot cells and missing data.

For decimal odds, compute raw implied probability as `1/odds`. When a complete market exists, remove overround by dividing each raw probability by their sum. Compare normalized probability changes, not price changes alone.

Grade inputs: A = timestamped multi-market sequence and verified context; B = multiple snapshots with minor gaps; C = isolated/incomplete snapshots; D = narrative-only. Cap confidence for low-quality inputs.

## 2. Evidence model

- **Fact:** observed or reliably sourced.
- **Signal:** repeatable transformation of facts.
- **Hypothesis:** interpretation, including attraction, protection, or capital explanations.
- **Unknown:** missing data or unresolved cause.

Outcome agreement does not prove a causal story.

## 3. Full sequence

### Independent baseline

Before considering the user's preferred conclusion or the market being audited, freeze direction, event range, top three paths, confidence, and decisive evidence. Build this from genuinely independent pre-match inputs such as a sporting model, team-strength and availability evidence, or a previously frozen baseline. Do not derive it from the same 1X2, handicap, total-goals, correct-score, or half/full-time prices that will later be tested for distortion. Later report what changed and why.

If no independent baseline can be built without post-result leakage or circular use of the audited prices, record it as unavailable. The task may continue as a `MARKET-STRUCTURE-ONLY` analysis, but it is not a full MCM probability forecast and its market-implied percentages must not be copied into an `MCM final probability` field.

### Three probability layers

Keep these fields separate for direction and event range:

1. **Market-implied probability:** de-vigged from the relevant complete market and timestamped.
2. **Independent baseline probability:** produced without the audited market prices; state model, inputs, and freeze time.
3. **MCM-adjusted probability or probability band:** starts from the independent baseline and changes only for explicitly recorded evidence that survives contradiction testing. Show the adjustment, direction, reason, and uncertainty.

If layer 2 is unavailable, layer 3 is unavailable. Do not manufacture a numerical adjustment merely to differ from the bookmaker, but also do not call layer 1 the final model result. A selection can still be a market-structure observation, with reduced confidence and no claim that MCM independently agrees.

### v1.4.2 execution status and acceptance gate

Assign every fixture exactly one status using `compliance-gates.md`: `FULL-MCM`, `MCM-DEGRADED`, `MARKET-STRUCTURE-ONLY`, or `BLOCKED`. Do this before writing the final recommendation, not as a cosmetic footer.

- No independent baseline forces `MARKET-STRUCTURE-ONLY`; independent and MCM-adjusted probabilities remain unavailable, value grade is at most C, CI is at most CI-1, and candidate motive labels remain `unresolved` or `none`.
- Unverified event identity, settlement horizon, handicap orientation, or material source mapping forces `BLOCKED` for the affected output.
- `FULL-MCM` requires the independent baseline, meaningful cross-book evidence, a valid late observation, all declared monitoring checkpoints, a frozen capital card, and successful machine validation.
- A material but non-blocking coverage gap is `MCM-DEGRADED`; it cannot receive grade A or CI-3.

Persist one record conforming to `fixture-analysis.schema.json` for each fixture and run `scripts/validate_report.py` before claiming completion. Repair validation errors or disclose the resulting downgrade. A prose report cannot override a failed machine check.

### Context and task

Establish rules, incentives, availability, schedule, aggregate state, and what each side needs. Separate motivation from capability.

### Market time series

Order all snapshots and inspect 1X2, handicap line and price, totals and exact totals, correct score, half/full-time paths, and qualification/championship markets. Distinguish line movement, price movement, and margin movement. When the handicap is Asian two-way, apply `asian-handicap.md`: verify orientation and odds format, establish a fair-line band, do not compare raw water across different settlement lines, and grade the Asian evidence AH-A through AH-D.

Check correlated coherence. A shortening favorite alongside drifting clean-win paths is a divergence requiring competing explanations, not proof of inducement.

For Asian handicap, freeze the neutral pattern code before assigning any motive label. Treat high/low water, deep/shallow lines, strengthening/weakening lines, and early/late timing as observable components. “阻上”, “诱上”, “诱下”, and “阻下” remain rival hypotheses whose validity depends on fair-line strength, cross-book breadth, normalized pricing, information timing, 1X2 coherence, and score-margin feasibility.

### Team and event evidence

Assess expected lineup, absences, fatigue, tactical matchup, shot quality rather than raw shots, set pieces, game-state sensitivity, goalkeeper effects, and comparable opponent strength.

### Narrative and positioning

Map likely entry stories such as home rebound, revenge, superstar farewell, must-win, low-scoring final, favorite accumulator, BTTS, or obvious exact score. Separate media consensus, social discussion, and measured money. Without money data, say “narratively attractive,” not “crowded.”

### Capital-intent inference

Apply `capital-intent.md` and freeze a separate capital-direction call before combining it with sporting and market baselines. Treat capital intent as a latent market-behavior hypothesis inferred from observable repricing, line structure, cross-book breadth, correlated markets, timing, and—when available—turnover or exchange data. Always retain competing explanations such as new information, risk balancing, model repricing, stale quotes, margin adjustment, and recreational demand.

Capital intent may reorder 1X2 or handicap scenarios only at evidence grade CI-2 or CI-3. It may not override settlement rules, verified lineup evidence, or sporting impossibility. Report its direction, evidence grade, strongest contradiction, and the conclusion with and without this layer.

Asian-handicap structure alone cannot create CI-2 or CI-3. It contributes primarily to protection/resistance and must still be corroborated by attraction/exposure plus sporting/score-path feasibility.

Use three-way triangulation rather than a hierarchy: (A) attraction/exposure, (B) protection/resistance, and (C) sporting and score-path feasibility. A strong capital conclusion requires all three to form a coherent loop. Two aligned layers with the third unknown remain provisional; any direct conflict must be shown and normally downgrades the capital conclusion.

### Contradiction matrix

For each divergence list: observation, mainstream explanation, alternative explanation, and discriminator. Never call a trap from one contradiction.

### Three layers

1. Direction: home/draw/away or equivalent.
2. Event range: low/medium/high; goal bands and BTTS.
3. Exact path or score: conditional on the first two.

Score each layer separately.

### Four-band goal probability calculation

Every final report must quantify the four exclusive 90-minute goal bands `0–1`, `2–3`, `4–6`, and `7+`, then rank them from highest to lowest.

When the latest complete exact-total fixed-odds market contains `0`, `1`, `2`, `3`, `4`, `5`, `6`, and `7+`, calculate raw weights `q_k = 1 / odds_k`. Aggregate `q_0 + q_1`, `q_2 + q_3`, `q_4 + q_5 + q_6`, and `q_7+`, then divide each aggregate by the sum of all eight raw weights. Report the resulting market-implied percentages, source, and timestamp. Do not average odds before inversion and do not normalize each band separately.

These four percentages are the market-implied baseline only. Do not present them as the independent or MCM-adjusted goal forecast unless a separately frozen, non-circular goal model exists and is identified. When both exist, show both distributions and explain every material adjustment rather than silently replacing one with the other.

If a source directly prices the four bands, normalize the four complete band prices directly. If only partial exact-total prices exist, do not silently treat the visible rows as a complete distribution. A separately specified score model may supply estimates when its inputs are adequate, but label them “model-estimated,” name the method, and reduce confidence. If neither a complete market nor an adequate model exists, report all four probabilities as unavailable and explain the gap rather than fabricate numbers. Rounded values should approximately total 100%.

### Unified 1X2 and three-way-handicap candidate pool

After freezing the 90-minute direction distribution, translate both ordinary 1X2 and every usable exact integer three-way handicap actually displayed by the source into settlement-path sets. Do not default to `+1` or `-1`: use the observed line, including `+2`, `-2`, or another explicit integer line. Estimate each candidate's probability by summing the mutually exclusive score or margin paths that settle it as a win, then rank all candidates together. Use evidence quality and cross-market coherence as tie-breakers; do not rank by low odds alone.

This is a hard pre-ranking gate, not an optional reporting preference. Persist `ordinary_1x2_coverage` and the observed handicap line/side/time in `three_way_handicap_coverage`, then choose one scope. If ordinary 1X2 is displayed, build the complete `unified` pool: ordinary home/draw/away plus handicap win/draw/loss for every readable displayed integer line. If ordinary 1X2 is explicitly verified as not displayed but a complete integer three-way handicap exists, build a `handicap_only` pool from its win/draw/loss outcomes and rank those three. Only then take ranks 1 and 2. A report that omits a displayed ordinary or handicap outcome fails validation. An unreadable or unverified displayed market blocks the affected ranking; an unsold ordinary market alone does not block a verified handicap-only ranking.

All rows in one unified ranking must be derived from the same named probability layer and, when numeric, the same 90-minute score/margin probability matrix. Do not mix an ordinary 1X2 market price with an independently modelled handicap probability and call the rows directly comparable. When the independent and MCM-adjusted layers are unavailable, clearly label any ordering as a market-baseline ordering rather than an independent forecast.

Asian two-way handicap prices are a separate evidence family. They may support or contradict the common matrix only after odds format, line, and orientation are validated under `asian-handicap.md`; they never enter the ordinary 1X2/Chinese three-way integer-handicap candidate pool.

For the side carrying handicap `h`, define `d = that side's 90-minute goals - opponent goals`. Settle the three-way handicap from `d + h`: greater than zero = handicap win, equal to zero = handicap draw, less than zero = handicap loss. Apply the same formula whether the displayed handicap belongs to the home or away side.

Examples of settlement-path aggregation:

- home `+1 handicap win` = actual home win or draw;
- home `+1 handicap draw` = actual away win by exactly one goal;
- home `+1 handicap loss` = actual away win by two or more goals;
- home `-1 handicap win` = actual home win by two or more goals;
- home `-1 handicap draw` = actual home win by exactly one goal;
- home `-1 handicap loss` = actual draw or away win.
- home `+2 handicap win` = actual home win, draw, or a one-goal home loss;
- home `+2 handicap draw` = actual home loss by exactly two goals;
- home `+2 handicap loss` = actual home loss by three or more goals;
- home `-2 handicap win` = actual home win by three or more goals;
- home `-2 handicap draw` = actual home win by exactly two goals;
- home `-2 handicap loss` = actual home win by exactly one goal, an actual draw, or an away win.

Always verify the displayed handicap orientation and integer line from the source. If the line or orientation is unreadable, label it unknown and omit that handicap candidate rather than infer it. These candidates overlap with ordinary 1X2 outcomes, so present them as alternative selections, not independent evidence or independent combination legs. If a handicap candidate covers multiple leading 1X2 paths and has the highest supported settlement probability, it may be the overall first choice.

### Scenarios

Build 3–5 candidates: coherent mainstream, contradiction-explaining alternative, genuine tail risk, and when relevant a 90-minute/qualification split. For each list support, contradiction, explained markets, narrative exposure, confidence, and falsifier.

### Maximum-market-win test

Use only to generate hypotheses. Ask what popular positions a scenario defeats, then require sporting/operational plausibility and cross-market coherence. Reject explanations requiring unobserved coordination.

### Inducement/protection exclusion screen

Before writing that an `诱导`, `保护`, `阻力`, or `反诱导` hypothesis has been excluded, test at least two genuinely distinct evidence groups rather than several mechanically derived prices from the same source. Eligible groups include: independent sporting baseline versus market; normalized 1X2 versus handicap-margin residual; total-goals versus score-path residual; late reversal or key-line resistance; independent cross-book breadth; verified news timing; and direct positioning data. Correct-score and half/full-time prices from the same provider normally count as correlated path evidence, not additional independent groups.

For each surviving hypothesis state the observation, mainstream explanation, inducement/protection explanation, non-intent alternative, discriminator, and strongest falsifier. If the evidence is insufficient, write `未能排除诱导，也未能确认诱导`; do not default to the lowest-priced outcome and call the screen complete.

The only permitted machine labels are `straight_support_candidate`, `inducement_candidate`, `upset_candidate`, `unresolved`, and `none`. The first three require a frozen independent baseline, CI-2 or CI-3, at least two genuinely independent evidence groups, and a passed red-team check. They describe candidates, never proven bookmaker intent.

### Red team

Confirm all timestamps were used; margin and line moves were separated; facts were separated from positioning assumptions; the user did not anchor the baseline; correlated markets were not double-counted; the strongest falsifier was named; and mainstream plus tail alternatives remain.

For capital intent, additionally confirm that the call was frozen before the result, did not rely on a single price move, did not treat public narrative as measured money, included all three triangulation layers, and would have produced the same market-structure label if the teams' names were hidden. Then restore team identity and confirm sporting/path feasibility independently.

For Asian handicap, additionally confirm the odds format and orientation, the fair-line uncertainty band, the exact whole/half/quarter settlement, the distinction between line and price movement, equivalent-line comparability, cross-book independence, and at least one non-intent causal alternative.

## 4. Football rules carried forward

- Separate 0-0 (extreme low event), 1-1 (central/obvious draw), and 2-2+ (high event).
- Rising odds never eliminate a score by themselves. “Cold storage” remains only a hypothesis and needs independent coherence.
- Low odds indicate protection and/or demand, not certainty.
- Preserve strong-win tails when direction is robust and goal distributions protect upper tails.
- In second legs, branch on leader scoring first, trailer scoring first, and a scoreless late phase.
- Keep 90-minute and qualification predictions in different rows.

Historical hypotheses:

- France 0-2 Spain: drifting two-goal and clean-win prices can remain viable.
- Häcken 0-0: correct draw direction can coexist with a failed event-range model.
- Rosenborg 4-0: correct direction can understate the strong-win tail.

## 5. User-thesis comparison

Compare independent baseline and user thesis for direction, event range, and exact path. Change only for new evidence, naming that evidence.

## 6. Post-result review

Freeze the original call. Grade direction, event range, exact path, qualification, capital-direction call, calibration, and process compliance. Compare the final conclusion with and without the capital-intent layer so its incremental value is measurable. Classify errors as data, interpretation, weighting, coverage, calibration, or communication. Propose the smallest change and test it on at least two prior cases before promotion.

A result screenshot for previously analyzed fixtures automatically triggers this full review unless the user explicitly opts out. Reuse existing task artifacts and screenshots; do not ask the user to repeat the review instructions or resend available material.

When Asian handicap affected the frozen call, also grade the actual full/half win-push-loss settlement, expected-value calibration when available, the frozen neutral pattern code, and whether the Asian layer improved or worsened the conclusion. Outcome agreement does not validate an “诱/阻” motive.

