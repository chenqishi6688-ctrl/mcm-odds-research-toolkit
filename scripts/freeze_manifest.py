#!/usr/bin/env python3
"""Create and verify a checksum receipt for one immutable-by-convention run.

This detects changed artifacts relative to the receipt.  It is not a digital
signature, trusted timestamp, or proof that the receipt itself was not replaced.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA = "mcm-freeze-manifest/v1"
MANIFEST = "freeze-manifest.json"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("kickoff must be timezone aware")
    return result


def create(batch: dict[str, Any], output: Path, records: list[dict[str, Any]],
           engine_version: str) -> dict[str, Any]:
    """Write the receipt last; caller must have made a new output directory."""
    created = datetime.now(timezone.utc)
    artifacts: dict[str, str] = {}
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(output).as_posix()
        if relative == MANIFEST:
            raise ValueError("freeze manifest already exists")
        artifacts[relative] = _sha(path.read_bytes())
    fixtures = []
    for record in records:
        kickoff = _time(record["event"]["kickoff"])
        fixtures.append({
            "fixture_id": record["event"]["id"],
            "kickoff": kickoff.isoformat(),
            "receipt_created_before_kickoff": created < kickoff,
            "monitoring_status": record.get("monitoring_audit", {}).get("status", "unverified"),
            "independent_baseline_available": record.get("probabilities", {}).get(
                "independent_baseline") is not None,
        })
    manifest = {
        "schema_version": SCHEMA,
        "engine_version": engine_version,
        "created_at_utc": created.isoformat(),
        "source_batch_canonical_sha256": _sha(_canonical(batch)),
        "artifacts": artifacts,
        "fixtures": fixtures,
        "limitation": "Local checksum receipt only; not a trusted timestamp or tamper-proof storage.",
    }
    with (output / MANIFEST).open("x", encoding="utf-8") as target:
        json.dump(manifest, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write("\n")
    return manifest


def verify(output: Path) -> list[str]:
    """Return reasons the receipt or its referenced artifacts fail verification."""
    errors: list[str] = []
    try:
        manifest = json.loads((output / MANIFEST).read_text(encoding="utf-8"))
        if manifest.get("schema_version") != SCHEMA:
            return ["unsupported freeze manifest schema"]
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict) or not artifacts:
            return ["freeze manifest has no artifacts"]
        actual_paths = {path.relative_to(output).as_posix() for path in output.rglob("*")
                        if path.is_file() and path.name != MANIFEST}
        if actual_paths != set(artifacts):
            errors.append("artifact inventory differs from freeze manifest")
        for name, expected in artifacts.items():
            path = output / name
            if (Path(name).is_absolute() or ".." in Path(name).parts
                    or not path.is_file() or _sha(path.read_bytes()) != expected):
                errors.append(f"artifact missing, unsafe or changed: {name}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return errors


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: freeze_manifest.py OUTPUT_DIR")
    failures = verify(Path(sys.argv[1]))
    print("PASS: checksum receipt and artifacts match" if not failures
          else "FAIL: " + "; ".join(failures))
    raise SystemExit(1 if failures else 0)

