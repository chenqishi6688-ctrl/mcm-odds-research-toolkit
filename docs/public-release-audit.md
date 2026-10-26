# Public release audit

## Source review

- Current methodology lineage reviewed: MCM v1.10.2, dated 2026-09-27.
- Earlier development artifacts reviewed: v1.4.2 through v1.10.x workspaces and synthetic pipeline examples.
- Public package version: `0.1.0`.

The release uses the current offline analytical core rather than publishing an old snapshot or a real monitoring workspace.

## Included

- Python analytical and validation scripts
- Publicly explainable methodology references
- JSON schemas
- Synthetic end-to-end input and validated output
- Offline tests and continuous integration
- MIT license, contribution guide, and security guidance

## Excluded

- Real match-monitoring logs and screenshots
- API credentials, tokens, encrypted credential stores, and scheduler identities
- Personal account, bankroll, and payment information
- Absolute user paths and device-specific configuration
- Third-party raw data whose redistribution rights are not established
- Cached bytecode and generated dependency folders
- Unsupported hit-rate, profitability, or bookmaker-manipulation claims

## Claim review

This release makes no historical performance claim. Descriptive records from earlier internal batches were not promoted into README metrics because they do not constitute a complete, preregistered, independent evaluation set.

Capital-intent labels are retained only as falsifiable market-behavior hypotheses. The code and documentation preserve non-intent explanations and prevent this layer from directly altering probabilities.

## Verification performed

- Core module self-tests
- End-to-end synthetic pipeline
- Machine-record validation
- Freeze-manifest verification
- Python bytecode compilation
- Pattern-based scan for common secret formats and personal absolute paths

The scan reduces accidental exposure risk but is not a substitute for a repository-host secret scanner.


