# Contributing

Contributions are welcome when they preserve the project's evidence boundaries.

## Development setup

Use Python 3.10 or newer. The core has no third-party runtime dependencies.

```bash
python -m unittest discover -s tests -v
```

## Pull-request requirements

- Add or update deterministic tests.
- Keep facts, signals, hypotheses, and unknowns distinct.
- Do not use audited market prices to construct the independent baseline.
- Do not add credentials, personal data, bankroll data, or unlicensed provider dumps.
- Preserve prior artifacts when changing append-only research flows.
- Describe the rollback condition for any methodological change.
- Do not advertise hit rate or profitability without a preregistered, chronological, independently reviewable evaluation.

Bug fixes and documentation improvements may be small. Predictive-method changes require a written hypothesis, a frozen evaluation plan, leakage checks, and protected-segment results.


