#!/usr/bin/env python3
"""Freeze, score and calibrate sourced non-market sporting adjustments.

All coefficients remain observe-only candidates. No command changes live MCM
probabilities, rankings or stable weights.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any


VERSION = "1.8.0-shadow"
FREEZE_SCHEMA = "mcm-adjustment-freeze/v1"
SCORE_SCHEMA = "mcm-adjustment-score/v1"
CALIBRATION_SCHEMA = "mcm-adjustment-calibration/v1"
EVIDENCE_TYPES = {"lineup", "injury", "suspension", "travel", "weather", "rest", "tactical"}
FORBIDDEN_KEYS = ("odds", "price", "bookmaker", "sportsbook", "betting", "market", "盘口", "赔率", "水位")


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


def _number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite numeric")
    result = float(value)
    if not low <= result <= high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return result


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "mcmadjust_" + hashlib.sha256(body).hexdigest()[:32]


def _reject_market_fields(value: Any, path: str = "input") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if any(term in str(key).casefold() for term in FORBIDDEN_KEYS):
                raise ValueError(f"{path}.{key} is forbidden market evidence")
            _reject_market_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_market_fields(item, f"{path}[{index}]")


def freeze(data: dict[str, Any]) -> dict[str, Any]:
    _reject_market_fields(data)
    event = data.get("event", {})
    if not isinstance(event.get("id"), str) or event.get("horizon") != "90m":
        raise ValueError("event identity and 90m horizon are required")
    freeze_time = _time(data.get("freeze_time"), "freeze_time")
    kickoff = _time(event.get("kickoff"), "event.kickoff")
    if freeze_time >= kickoff:
        raise ValueError("adjustment freeze must precede kickoff")
    baseline = data.get("baseline_lambdas")
    if not isinstance(baseline, dict):
        raise ValueError("baseline_lambdas are required")
    baseline = {side: _number(baseline.get(side), f"baseline_lambdas.{side}", .05, 6) for side in ("home", "away")}
    signals = data.get("signals")
    if not isinstance(signals, list) or not signals:
        raise ValueError("at least one frozen sporting signal is required")
    clean = []
    for index, row in enumerate(signals):
        if not isinstance(row, dict) or row.get("evidence_type") not in EVIDENCE_TYPES:
            raise ValueError(f"signals[{index}].evidence_type invalid")
        if row.get("target") not in {"home_lambda", "away_lambda"} or row.get("expected_direction") not in {"up", "down"}:
            raise ValueError(f"signals[{index}] target/direction invalid")
        if not all(isinstance(row.get(key), str) and row[key].strip() for key in ("source_group", "license_basis", "observed_at")):
            raise ValueError(f"signals[{index}] provenance incomplete")
        if _time(row["observed_at"], f"signals[{index}].observed_at") > freeze_time:
            raise ValueError(f"signals[{index}] post-freeze evidence")
        clean.append({**row, "strength": _number(row.get("strength"), f"signals[{index}].strength", 0, 1)})
    return {
        "schema_version": FREEZE_SCHEMA, "engine_version": VERSION, "mode": "observe_only",
        "event": event, "freeze_time": data["freeze_time"], "baseline_lambdas": baseline,
        "signals": clean, "input_digest": _digest(data), "stable_weights_changed": False,
        "probability_delta_applied": 0, "live_ranking_changed": False,
    }


def score(frozen: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    if frozen.get("schema_version") != FREEZE_SCHEMA or frozen.get("mode") != "observe_only":
        raise ValueError("invalid adjustment freeze")
    event = frozen["event"]
    if result.get("event_id") != event["id"] or result.get("status") != "FINISHED" or result.get("horizon") != "90m":
        raise ValueError("result identity/status/horizon mismatch")
    if _time(result.get("observed_at"), "result.observed_at") <= _time(event["kickoff"], "event.kickoff"):
        raise ValueError("result must be observed after kickoff")
    goals = {side: int(_number(result.get(f"{side}_goals"), f"result.{side}_goals", 0, 15)) for side in ("home", "away")}
    if any(goals[side] != result.get(f"{side}_goals") for side in goals):
        raise ValueError("result goals must be integers")
    residual = {side: goals[side] - frozen["baseline_lambdas"][side] for side in ("home", "away")}
    design_rows = []
    for signal in frozen["signals"]:
        side = signal["target"].split("_")[0]
        x = signal["strength"] * (1 if signal["expected_direction"] == "up" else -1)
        design_rows.append({"feature_key": f"{signal['evidence_type']}:{signal['target']}", "x": x, "y": residual[side]})
    return {
        "schema_version": SCORE_SCHEMA, "engine_version": VERSION, "event_id": event["id"],
        "freeze_digest": _digest(frozen), "result": {"home_goals": goals["home"], "away_goals": goals["away"], "observed_at": result["observed_at"], "horizon": "90m"},
        "design_rows": design_rows, "stable_weights_changed": False, "probability_delta_applied": 0,
    }


def calibrate(scores: list[dict[str, Any]], minimum_events: int = 100, minimum_per_feature: int = 25) -> dict[str, Any]:
    seen = set()
    groups: dict[str, list[tuple[float, float]]] = {}
    for score_row in scores:
        if (score_row.get("schema_version") != SCORE_SCHEMA or score_row.get("probability_delta_applied") != 0
                or score_row.get("stable_weights_changed") is not False):
            raise ValueError("invalid adjustment score")
        event_id = score_row.get("event_id")
        if event_id in seen:
            raise ValueError(f"duplicate adjustment event: {event_id}")
        seen.add(event_id)
        for row in score_row.get("design_rows", []):
            groups.setdefault(row["feature_key"], []).append((_number(row["x"], "design.x", -1, 1), _number(row["y"], "design.y", -15, 15)))
    coefficients = {}
    for key, rows in sorted(groups.items()):
        denominator = sum(x * x for x, _ in rows)
        raw = sum(x * y for x, y in rows) / denominator if denominator else 0.0
        coefficients[key] = {"sample_count": len(rows), "raw_lambda_delta_per_unit": raw, "capped_candidate": max(-.5, min(.5, raw)), "qualified": len(rows) >= minimum_per_feature}
    qualified = [key for key, value in coefficients.items() if value["qualified"]]
    ready = len(seen) >= minimum_events and bool(qualified)
    return {
        "schema_version": CALIBRATION_SCHEMA, "engine_version": VERSION, "mode": "observe_only",
        "event_count": len(seen), "minimum_events": minimum_events, "minimum_per_feature": minimum_per_feature,
        "coefficients": coefficients, "qualified_features": qualified,
        "status": "ready_for_promotion_review" if ready else "insufficient_frozen_sample",
        "automatic_promotion": False, "stable_weights_changed": False, "probability_delta_applied": 0,
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
    raw = {"event": {"id": "a", "kickoff": "2026-01-02T12:00:00Z", "horizon": "90m"}, "freeze_time": "2026-01-02T10:00:00Z", "baseline_lambdas": {"home": 1.2, "away": .8}, "signals": [{"evidence_type": "lineup", "target": "home_lambda", "expected_direction": "up", "strength": .5, "source_group": "licensed-team-feed", "license_basis": "contract", "observed_at": "2026-01-02T09:00:00Z"}]}
    frozen = freeze(raw)
    scored = score(frozen, {"event_id": "a", "status": "FINISHED", "horizon": "90m", "home_goals": 2, "away_goals": 0, "observed_at": "2026-01-02T15:00:00Z"})
    report = calibrate([scored], 2, 1)
    if report["status"] != "insufficient_frozen_sample" or report["probability_delta_applied"] != 0:
        raise AssertionError("adjustment calibration safety failed")
    print("SELF-TEST PASS: frozen adjustment scoring and observe-only calibration")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser("freeze"); freeze_parser.add_argument("input", type=Path); freeze_parser.add_argument("--output", required=True, type=Path)
    score_parser = sub.add_parser("score"); score_parser.add_argument("freeze", type=Path); score_parser.add_argument("result", type=Path); score_parser.add_argument("--output", required=True, type=Path)
    calibrate_parser = sub.add_parser("calibrate"); calibrate_parser.add_argument("scores", nargs="+", type=Path); calibrate_parser.add_argument("--minimum-events", type=int, default=100); calibrate_parser.add_argument("--minimum-per-feature", type=int, default=25); calibrate_parser.add_argument("--output", required=True, type=Path)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test": self_test()
        elif args.command == "freeze": _write_new(args.output, freeze(json.loads(args.input.read_text(encoding="utf-8"))))
        elif args.command == "score": _write_new(args.output, score(json.loads(args.freeze.read_text(encoding="utf-8")), json.loads(args.result.read_text(encoding="utf-8"))))
        else: _write_new(args.output, calibrate([json.loads(path.read_text(encoding="utf-8")) for path in args.scores], args.minimum_events, args.minimum_per_feature))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

