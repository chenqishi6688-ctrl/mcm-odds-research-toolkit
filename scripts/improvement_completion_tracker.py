#!/usr/bin/env python3
"""Track the eight MCM improvements without conflating code completion and evidence maturity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VERSION = "1.8.0-shadow"
SCHEMA = "mcm-eight-improvement-status/v1"


def _flag(engineering: dict[str, Any], key: str) -> bool:
    return engineering.get(key) is True


def assess(program: dict[str, Any], cohort: dict[str, Any] | None = None,
           adjustment: dict[str, Any] | None = None,
           capital_ledgers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    engineering = program.get("engineering", {})
    operations = program.get("operations", {})
    thresholds = program.get("thresholds", {})
    ledgers = capital_ledgers or []
    eligible_independent = int(operations.get("eligible_independent_events", 0))
    min_independent = int(thresholds.get("minimum_independent_events", 1))
    capital_events = {row.get("event", {}).get("id") for row in ledgers
                      if row.get("schema_version") == "mcm-capital-evidence-freeze/v1"
                      and row.get("independent_attraction_available") is True}
    capital_groups = {group for row in ledgers for group in row.get("source_groups", [])}
    min_capital_events = int(thresholds.get("minimum_capital_events", 30))
    min_capital_groups = int(thresholds.get("minimum_capital_source_groups", 2))
    cohort_ready = bool(cohort and cohort.get("promotion_review_ready") is True
                        and cohort.get("automatic_promotion") is False)
    adjustment_ready = bool(adjustment and adjustment.get("status") == "ready_for_promotion_review"
                            and adjustment.get("automatic_promotion") is False)
    no_backfill = int(operations.get("backfilled_predictions", 0)) == 0
    no_chronology_failure = int(operations.get("chronology_gate_failures", 0)) == 0
    definitions = [
        (1, "独立数据采集", ("sporting_history_pipeline", "identity_registry", "provider_preflight"),
         eligible_independent >= min_independent,
         f"合格赛前独立基线 {eligible_independent}/{min_independent}"),
        (2, "资本闭环独立性", ("capital_independence_gate",),
         _flag(engineering, "capital_independence_gate"), "无独立吸引证据时自动降为部分闭环"),
        (3, "资本作用于排序", ("ranking_counterfactual", "near_tie_capital_gate"),
         _flag(engineering, "ranking_counterfactual") and _flag(engineering, "near_tie_capital_gate"),
         "成对保存无资本/有资本排序，概率增量恒为零"),
        (4, "验证器升级", ("validator_hard_gate", "negative_regression_tests"),
         _flag(engineering, "validator_hard_gate") and _flag(engineering, "negative_regression_tests"),
         "强制门禁与反例测试"),
        (5, "独立模型升级", ("shadow_model_lab", "cohort_evaluator"), cohort_ready,
         "须在多联赛时间顺序样本达到晋升评审门槛"),
        (6, "调整幅度校准", ("adjustment_freeze_score_calibrate",), adjustment_ready,
         "须达到冻结非市场证据样本门槛"),
        (7, "扩展资本证据", ("licensed_capital_ledger",),
         len(capital_events) >= min_capital_events and len(capital_groups) >= min_capital_groups,
         f"合格事件 {len(capital_events)}/{min_capital_events}，独立来源组 {len(capital_groups)}/{min_capital_groups}"),
        (8, "时间顺序验证", ("append_only_prediction", "post_result_scoring", "cohort_evaluator"),
         cohort_ready and no_backfill and no_chronology_failure,
         "只计赛前登记并冻结、赛后核验的未来样本"),
    ]
    items = []
    for number, name, required, evidence_complete, note in definitions:
        engineering_complete = all(_flag(engineering, key) for key in required)
        items.append({"number": number, "name": name, "engineering_complete": engineering_complete,
            "evidence_complete": bool(evidence_complete),
            "status": "complete" if engineering_complete and evidence_complete else
                      "automated_collecting_evidence" if engineering_complete else "engineering_incomplete",
            "required_engineering_checks": list(required), "note": note})
    engineering_complete = all(item["engineering_complete"] for item in items)
    evidence_complete = all(item["evidence_complete"] for item in items)
    return {
        "schema_version": SCHEMA,
        "engine_version": VERSION,
        "program_id": program.get("program_id"),
        "items": items,
        "engineering_complete": engineering_complete,
        "all_evidence_gates_complete": evidence_complete,
        "overall_status": "complete_pending_human_promotion_review" if engineering_complete and evidence_complete else
                          "automatic_evidence_collection_active" if engineering_complete else "engineering_incomplete",
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
    flags = {key: True for key in ("sporting_history_pipeline", "identity_registry", "provider_preflight",
        "capital_independence_gate", "ranking_counterfactual", "near_tie_capital_gate", "validator_hard_gate",
        "negative_regression_tests", "shadow_model_lab", "cohort_evaluator", "adjustment_freeze_score_calibrate",
        "licensed_capital_ledger", "append_only_prediction", "post_result_scoring")}
    program = {"program_id": "p", "engineering": flags, "operations": {"eligible_independent_events": 0,
        "backfilled_predictions": 0, "chronology_gate_failures": 0}}
    report = assess(program)
    if not report["engineering_complete"] or report["all_evidence_gates_complete"]:
        raise AssertionError("engineering/evidence separation failed")
    print("SELF-TEST PASS: eight-item engineering and evidence states remain separate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    assess_parser = sub.add_parser("assess")
    assess_parser.add_argument("program", type=Path)
    assess_parser.add_argument("--cohort", type=Path)
    assess_parser.add_argument("--adjustment", type=Path)
    assess_parser.add_argument("--capital-ledger", nargs="*", type=Path, default=[])
    assess_parser.add_argument("--output", required=True, type=Path)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test": self_test()
        else:
            load = lambda path: json.loads(path.read_text(encoding="utf-8")) if path else None
            _write_new(args.output, assess(load(args.program), load(args.cohort), load(args.adjustment), [load(path) for path in args.capital_ledger]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

