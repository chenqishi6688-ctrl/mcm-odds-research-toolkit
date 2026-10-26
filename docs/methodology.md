# Public methodology contract

## 1. Claim types

Every analytical statement belongs to one of four classes:

- **Fact**: directly observed or reliably sourced.
- **Signal**: a reproducible transformation of facts.
- **Hypothesis**: an interpretation that can be contradicted or falsified.
- **Unknown**: a missing or unresolved input.

Outcome agreement does not prove a causal hypothesis.

## 2. Input gate

Before analysis, freeze event identity, kickoff, timezone, home/away orientation, 90-minute settlement horizon, source identity, observation time, and input lineage. Unreadable or ambiguous fields remain unknown.

## 3. Three probability layers

### Market-implied

For decimal odds, calculate raw implied probability as `1 / odds`. For a complete mutually exclusive market, remove the overround by dividing each raw probability by their sum. Report the source and observation time.

### Independent baseline

Build this layer without using the audited 1X2, handicap, total-goals, correct-score, or half/full-time prices. The included baseline builder prefers complete xG histories; otherwise it can use completed 90-minute goals with lower reliability. Team rates are estimated by venue and shrunk toward the league environment.

### MCM-adjusted

Start from the independent score matrix. Apply only frozen, non-market sporting evidence that passes provenance and contradiction checks. If nothing qualifies, the adjusted layer equals the independent layer with a recorded zero delta. If no independent baseline exists, the adjusted layer is unavailable.

## 4. Coherent outputs

One score matrix drives:

- ordinary 1X2 probabilities;
- exact scores;
- `0–1`, `2–3`, `4–6`, and `7+` goal bands;
- integer three-way handicap settlement paths;
- optional half/full-time paths.

This prevents incompatible probability sources from being mixed inside one ranking.

## 5. Capital-intent hypothesis

The capital card has equal-status legs:

1. attraction or exposure;
2. protection or resistance;
3. sporting and score-path feasibility.

It must also preserve a non-intent explanation, strongest contradiction, falsifier, reorder condition, evidence grade, and complete rankings with and without the layer. Market accessibility alone is not an independent attraction signal. The capital card may reorder only a qualified near-tie; it never changes candidate probabilities.

## 6. Acceptance status

- `FULL-MCM` requires an independent baseline, meaningful cross-book evidence, a valid late observation, all declared monitoring checkpoints, a frozen capital card, and successful machine validation.
- `MCM-DEGRADED` retains a valid baseline but has a material evidence gap.
- `MARKET-STRUCTURE-ONLY` is mandatory when the independent baseline is unavailable.
- `BLOCKED` is mandatory when identity, orientation, horizon, or another critical field is unresolved.

## 7. Research promotion

Candidate changes remain observe-only until evaluated chronologically on frozen data. Promotion requires calibration improvement, protected-segment checks, multiple competitions or periods, leakage review, and a rollback rule. A single successful event cannot promote a rule.

## 8. Responsible-use boundary

MCM is a research framework, not a claim of match fixing and not a betting recommendation service. Users remain responsible for legal compliance, provider terms, data licenses, and any financial decisions.


