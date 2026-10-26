# Examples

`synthetic-full-mcm-batch.json` contains one fictional fixture and no real account, provider, or personal data.

Generate the result:

```bash
python scripts/full_mcm_pipeline.py examples/synthetic-full-mcm-batch.json --output demo-run
python scripts/freeze_manifest.py demo-run
```

`demo-output/` is the committed result from the same input. Its `MCM-DEGRADED` status is intentional: synthetic caller-supplied checkpoint counts do not satisfy the artifact-bound monitoring gate.


