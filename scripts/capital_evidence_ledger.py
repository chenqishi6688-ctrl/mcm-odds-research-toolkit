#!/usr/bin/env python3
"""Freeze licensed measured capital evidence without changing MCM probabilities."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any


VERSION = "1.8.0-shadow"
SCHEMA = "mcm-capital-evidence-freeze/v1"
MEASUREMENT_TYPES = {"bet_share", "turnover", "liability", "exchange_volume"}
FORBIDDEN_KEYS = ("odds", "price", "bookmaker", "sportsbook", "盘口", "赔率", "水位", "api_key", "token", "secret")


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{label} must be a timezone-aware timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return float(value)


def _reject_forbidden(value: Any, path: str = "input") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if any(term in str(key).casefold() for term in FORBIDDEN_KEYS):
                raise ValueError(f"{path}.{key} is forbidden in the capital evidence ledger")
            _reject_forbidden(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden(item, f"{path}[{index}]")


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "mcmcapital_" + hashlib.sha256(body).hexdigest()[:32]


def freeze(data: dict[str, Any]) -> dict[str, Any]:
    _reject_forbidden(data)
    event = data.get("event", {})
    if not isinstance(event.get("id"), str) or not event["id"].strip() or event.get("horizon") != "90m":
        raise ValueError("event identity and 90m horizon are required")
    freeze_time = _time(data.get("freeze_time"), "freeze_time")
    kickoff = _time(event.get("kickoff"), "event.kickoff")
    if freeze_time >= kickoff:
        raise ValueError("capital evidence freeze must precede kickoff")
    positions = data.get("measured_positions")
    if not isinstance(positions, list) or not positions:
        raise ValueError("at least one measured position is required")
    clean: list[dict[str, Any]] = []
    source_groups: set[str] = set()
    directions: set[str] = set()
    for index, row in enumerate(positions):
        if not isinstance(row, dict) or row.get("direction") not in {"home", "draw", "away"}:
            raise ValueError(f"measured_positions[{index}].direction invalid")
        if row.get("measurement_type") not in MEASUREMENT_TYPES:
            raise ValueError(f"measured_positions[{index}].measurement_type invalid")
        required = ("unit", "source_group", "license_basis", "observed_at")
        if not all(isinstance(row.get(key), str) and row[key].strip() for key in required):
            raise ValueError(f"measured_positions[{index}] provenance incomplete")
        observed = _time(row["observed_at"], f"measured_positions[{index}].observed_at")
        if observed > freeze_time:
            raise ValueError(f"measured_positions[{index}] is post-freeze evidence")
        clean_row = {**row, "value": _number(row.get("value"), f"measured_positions[{index}].value")}
        clean.append(clean_row)
        source_groups.add(row["source_group"])
        directions.add(row["direction"])
    independently_measured = bool(clean)
    directional = len(directions) == 1
    return {
        "schema_version": SCHEMA,
        "engine_version": VERSION,
        "mode": "observe_only",
        "event": event,
        "freeze_time": data["freeze_time"],
        "measured_positions": clean,
        "source_groups": sorted(source_groups),
        "directional_summary": next(iter(directions)) if directional else "mixed",
        "independent_attraction_available": independently_measured and directional,
        "capital_loop_eligibility": "measured_attraction_leg_available" if independently_measured and directional else "partial_or_conflicting_measurement",
        "ranking_use": "near_tie_gate_only",
        "automatic_probability_adjustment": False,
        "probability_delta_applied": 0,
        "live_ranking_changed": False,
        "input_digest": _digest(data),
    }


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except FileExistsError:
        raise ValueError(f"output already exists: {path}") from None


def self_test() -> None:
    raw = {
        "event": {"id": "capital-1", "kickoff": "2026-01-02T12:00:00Z", "horizon": "90m"},
        "freeze_time": "2026-01-02T10:00:00Z",
        "measured_positions": [{"direction": "home", "measurement_type": "bet_share", "value": 61,
            "unit": "percent", "source_group": "licensed-position-feed", "license_basis": "contract",
            "observed_at": "2026-01-02T09:59:00Z"}],
    }
    output = freeze(raw)
    if not output["independent_attraction_available"] or output["probability_delta_applied"] != 0:
        raise AssertionError("capital evidence isolation failed")
    contaminated = json.loads(json.dumps(raw)); contaminated["measured_positions"][0]["odds"] = 2.0
    try:
        freeze(contaminated)
    except ValueError:
        pass
    else:
        raise AssertionError("market-contaminated capital evidence was accepted")
    print("SELF-TEST PASS: licensed capital evidence is append-only and probability-isolated")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("input", type=Path)
    freeze_parser.add_argument("--output", required=True, type=Path)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
        else:
            _write_new(args.output, freeze(json.loads(args.input.read_text(encoding="utf-8"))))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

