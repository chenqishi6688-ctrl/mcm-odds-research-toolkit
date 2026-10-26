#!/usr/bin/env python3
"""Aggregate preregistered MCM shadow scores with protected-segment gates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


VERSION = "1.8.0-shadow"
SCHEMA = "mcm-shadow-cohort-evaluation/v1"
SCORE_SCHEMA = "mcm-shadow-score/v1"
METRICS = ("1x2_log_loss", "1x2_brier", "1x2_rps", "goal_band_log_loss")


def _mean(rows: list[dict[str, Any]], model: str, metric: str) -> float:
    values = [row["model_scores"][model][metric] for row in rows]
    if not values or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise ValueError(f"missing or invalid {model}.{metric}")
    return sum(values) / len(values)


def _segment_values(row: dict[str, Any], protected: str) -> list[str]:
    segments = row.get("segments", {})
    if protected == "low_goal":
        return ["low"] if segments.get("goal_environment") == "low" else []
    if protected == "high_goal":
        return ["high"] if segments.get("goal_environment") == "high" else []
    value = segments.get(protected)
    if value is None:
        return []
    return [str(value).lower() if isinstance(value, bool) else str(value)]


def evaluate(prereg: dict[str, Any], scores: list[dict[str, Any]], minimum_settled_events: int = 100,
             minimum_competitions: int = 3, minimum_events_per_segment: int = 20,
             maximum_segment_regression: float = 0.02) -> dict[str, Any]:
    if prereg.get("schema_version") != "mcm-shadow-cohort-preregistration/v1":
        raise ValueError("invalid cohort preregistration")
    if prereg.get("historical_batch_backfill_allowed") is not False:
        raise ValueError("cohort must forbid historical backfill")
    control = prereg.get("control_model")
    candidates = prereg.get("candidate_models")
    primary = prereg.get("primary_metric")
    if not isinstance(control, str) or not isinstance(candidates, list) or not candidates or primary not in METRICS:
        raise ValueError("cohort model or metric configuration invalid")
    seen_events: set[str] = set()
    seen_predictions: set[str] = set()
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for row in scores:
        event_id = row.get("event_id")
        digest = row.get("prediction_digest")
        if row.get("schema_version") != SCORE_SCHEMA or row.get("stable_weights_changed") is not False:
            raise ValueError("invalid shadow score safety invariant")
        if event_id in seen_events or digest in seen_predictions:
            raise ValueError(f"duplicate score or prediction: {event_id}")
        seen_events.add(event_id); seen_predictions.add(digest)
        if row.get("cohort_eligible") is not True or row.get("experiment_registered") is not True:
            excluded.append({"event_id": str(event_id), "reason": "not_preregistered_before_kickoff"})
            continue
        models = row.get("model_scores", {})
        if control not in models or any(candidate not in models for candidate in candidates):
            raise ValueError(f"score {event_id} lacks configured models")
        eligible.append(row)
    model_names = [control, *candidates]
    aggregates = {
        model: {metric: _mean(eligible, model, metric) for metric in METRICS}
        for model in model_names
    } if eligible else {}
    deltas = {
        candidate: {metric: aggregates[candidate][metric] - aggregates[control][metric] for metric in METRICS}
        for candidate in candidates
    } if eligible else {}
    protected = prereg.get("protected_regression_segments", [])
    segment_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for name in protected:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in eligible:
            for value in _segment_values(row, name):
                buckets.setdefault(value, []).append(row)
        segment_rows[name] = buckets
    segment_audit: dict[str, Any] = {}
    material_regressions: list[dict[str, Any]] = []
    for name, buckets in segment_rows.items():
        segment_audit[name] = {}
        for value, rows in buckets.items():
            qualified = len(rows) >= minimum_events_per_segment
            candidate_deltas = {candidate: _mean(rows, candidate, primary) - _mean(rows, control, primary) for candidate in candidates}
            segment_audit[name][value] = {"event_count": len(rows), "qualified": qualified, "primary_metric_deltas": candidate_deltas}
            if qualified:
                for candidate, delta in candidate_deltas.items():
                    if delta > maximum_segment_regression:
                        material_regressions.append({"segment": name, "value": value, "candidate": candidate, "delta": delta})
    competitions = {str(row.get("segments", {}).get("competition", "unknown")) for row in eligible}
    overall_improvement = bool(eligible) and all(deltas[candidate][primary] < 0 for candidate in candidates)
    ready = (len(eligible) >= minimum_settled_events and len(competitions) >= minimum_competitions
             and overall_improvement and not material_regressions)
    return {
        "schema_version": SCHEMA,
        "engine_version": VERSION,
        "cohort_id": prereg.get("cohort_id"),
        "mode": "observe_only",
        "eligible_event_count": len(eligible),
        "excluded_scores": excluded,
        "competition_count": len(competitions),
        "thresholds": {"minimum_settled_events": minimum_settled_events, "minimum_competitions": minimum_competitions,
            "minimum_events_per_protected_segment": minimum_events_per_segment, "maximum_mean_regression": maximum_segment_regression},
        "aggregates": aggregates,
        "candidate_deltas_vs_control": deltas,
        "protected_segment_audit": segment_audit,
        "material_regressions": material_regressions,
        "overall_primary_metric_improvement": overall_improvement,
        "promotion_review_ready": ready,
        "status": "ready_for_human_promotion_review" if ready else "continue_chronological_collection",
        "automatic_promotion": False,
        "stable_weights_changed": False,
        "probability_delta_applied": 0,
        "live_ranking_changed": False,
    }


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False); handle.write("\n")
    except FileExistsError:
        raise ValueError(f"output already exists: {path}") from None


def self_test() -> None:
    prereg = {"schema_version": "mcm-shadow-cohort-preregistration/v1", "cohort_id": "c", "historical_batch_backfill_allowed": False,
        "control_model": "control", "candidate_models": ["candidate"], "primary_metric": "1x2_log_loss",
        "protected_regression_segments": ["competition", "sparse_history"]}
    def row(event: str, competition: str, eligible: bool = True) -> dict[str, Any]:
        model = lambda loss: {metric: loss for metric in METRICS}
        return {"schema_version": SCORE_SCHEMA, "event_id": event, "prediction_digest": "d" + event,
            "stable_weights_changed": False, "cohort_eligible": eligible, "experiment_registered": eligible,
            "model_scores": {"control": model(.5), "candidate": model(.4)},
            "segments": {"competition": competition, "sparse_history": False}}
    report = evaluate(prereg, [row("1", "a"), row("2", "b"), row("3", "c"), row("x", "a", False)], 3, 3, 1, .02)
    if not report["promotion_review_ready"] or report["eligible_event_count"] != 3 or len(report["excluded_scores"]) != 1:
        raise AssertionError("cohort evaluation gates failed")
    print("SELF-TEST PASS: chronological cohort and protected-regression gates")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("prereg", type=Path)
    evaluate_parser.add_argument("scores", nargs="*", type=Path)
    evaluate_parser.add_argument("--minimum-settled-events", type=int, default=100)
    evaluate_parser.add_argument("--minimum-competitions", type=int, default=3)
    evaluate_parser.add_argument("--minimum-events-per-segment", type=int, default=20)
    evaluate_parser.add_argument("--maximum-segment-regression", type=float, default=.02)
    evaluate_parser.add_argument("--output", required=True, type=Path)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test": self_test()
        else:
            prereg = json.loads(args.prereg.read_text(encoding="utf-8"))
            scores = [json.loads(path.read_text(encoding="utf-8")) for path in args.scores]
            _write_new(args.output, evaluate(prereg, scores, args.minimum_settled_events, args.minimum_competitions,
                args.minimum_events_per_segment, args.maximum_segment_regression))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

