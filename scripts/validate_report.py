#!/usr/bin/env python3
"""Validate machine-readable MCM fixture records.

This enforces v1.6.3 process invariants and accepts legacy v1.6.1/v1.6.2 records.
It checks internal consistency and report-status claims; it does not validate
sporting facts or bookmaker motive.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import math
import sys
from pathlib import Path
from typing import Any

import evidence_integrity
import market_quality


VALID_STATUSES = {
    "FULL-MCM",
    "MCM-DEGRADED",
    "MARKET-STRUCTURE-ONLY",
    "BLOCKED",
}
CAPITAL_LABELS = {
    "straight_support_candidate",
    "inducement_candidate",
    "upset_candidate",
    "unresolved",
    "none",
}
CI_VALUE = {"CI-0": 0, "CI-1": 1, "CI-2": 2, "CI-3": 3}
GRADE_VALUE = {"D": 0, "C": 1, "B": 2, "A": 3}
SCHEMA_VERSIONS = {"1.6.1", "1.6.2", "1.6.3"}
CURRENT_SCHEMA_VERSION = "1.6.3"
HANDICAP_OUTCOMES = {"side_win", "handicap_draw", "side_loss"}
CAPITAL_REQUIRED = {
    "freeze_time",
    "market_only_direction",
    "sporting_baseline_direction",
    "attraction",
    "protection",
    "feasibility",
    "loop_status",
    "ci_grade",
    "capital_direction",
    "combined_direction",
    "without_capital_direction",
    "incremental_effect",
    "independent_evidence_groups",
    "candidate_label",
    "red_team_passed",
    "hypothesis_status",
    "non_intent_alternative",
    "diagnostics",
    "attraction_basis",
    "leg_independence",
    "strongest_support",
    "strongest_contradiction",
    "falsifier",
    "reorder_condition",
}


def _parse_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be an ISO-8601 datetime with timezone")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 datetime with timezone")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed


def _distribution_sum(distribution: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    values: list[float] = []
    for key in keys:
        value = distribution.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        if not 0 <= float(value) <= 1:
            return None
        values.append(float(value))
    return sum(values)


def _same_probabilities(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return math.isclose(float(left), float(right), abs_tol=1e-12)
    if isinstance(left, dict) and isinstance(right, dict) and set(left) == set(right):
        return all(_same_probabilities(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return all(_same_probabilities(a, b) for a, b in zip(left, right))
    return left == right


def _validate_probability_layer(name: str, layer: Any, errors: list[str]) -> None:
    if layer is None:
        return
    if not isinstance(layer, dict):
        errors.append(f"probabilities.{name} must be an object or null")
        return
    one_x_two = layer.get("one_x_two")
    goal_bands = layer.get("goal_bands")
    if not isinstance(one_x_two, dict):
        unavailable = layer.get("unavailable_fields", {})
        if name != "market_implied" or not isinstance(unavailable, dict) or not unavailable.get("one_x_two"):
            errors.append(f"probabilities.{name}.one_x_two is required")
    else:
        total = _distribution_sum(one_x_two, ("home", "draw", "away"))
        if total is None or not math.isclose(total, 1.0, abs_tol=0.015):
            errors.append(f"probabilities.{name}.one_x_two must sum to approximately 1")
    if not isinstance(goal_bands, dict):
        unavailable = layer.get("unavailable_fields", {})
        if name != "market_implied" or not isinstance(unavailable, dict) or not unavailable.get("goal_bands"):
            errors.append(f"probabilities.{name}.goal_bands is required")
    else:
        total = _distribution_sum(goal_bands, ("0-1", "2-3", "4-6", "7+"))
        if total is None or not math.isclose(total, 1.0, abs_tol=0.015):
            errors.append(f"probabilities.{name}.goal_bands must sum to approximately 1")
    if not layer.get("method") or not layer.get("freeze_time"):
        errors.append(f"probabilities.{name} must record method and freeze_time")
    offers = layer.get("three_way_handicaps", [])
    if not isinstance(offers, list):
        errors.append(f"probabilities.{name}.three_way_handicaps must be a list")
    else:
        seen_offers: set[tuple[str, int]] = set()
        for index, offer in enumerate(offers):
            if not isinstance(offer, dict):
                errors.append(
                    f"probabilities.{name}.three_way_handicaps[{index}] must be an object"
                )
                continue
            side = offer.get("side")
            line = offer.get("line")
            if side not in {"home", "away"} or isinstance(line, bool) or not isinstance(line, int):
                errors.append(
                    f"probabilities.{name}.three_way_handicaps[{index}] needs side and integer line"
                )
                continue
            key = (side, line)
            if key in seen_offers:
                errors.append(f"probabilities.{name}.three_way_handicaps has duplicate offers")
            seen_offers.add(key)
            offer_probabilities = offer.get("probabilities")
            if not isinstance(offer_probabilities, dict):
                errors.append(
                    f"probabilities.{name}.three_way_handicaps[{index}].probabilities is required"
                )
                continue
            total = _distribution_sum(
                offer_probabilities, ("side_win", "handicap_draw", "side_loss")
            )
            if total is None or not math.isclose(total, 1.0, abs_tol=0.015):
                errors.append(
                    f"probabilities.{name}.three_way_handicaps[{index}] must sum to approximately 1"
                )


def validate_record(record: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(record, dict):
        return ["record must be a JSON object"], warnings

    schema_version = record.get("schema_version")
    if schema_version not in SCHEMA_VERSIONS:
        errors.append("schema_version must be 1.6.1, 1.6.2 or 1.6.3")
    elif schema_version == "1.6.1":
        warnings.append(
            "legacy schema 1.6.1 does not enforce the v1.6.2 three-way-handicap coverage declaration"
        )

    status = record.get("report_status")
    if status not in VALID_STATUSES:
        errors.append("report_status is missing or invalid")
    elif status == "FULL-MCM" and record.get("engine_version") != "1.6.3+evidence1":
        warnings.append(
            "legacy FULL-MCM status is historical; monitoring artifacts were not reverified by the current gate"
        )

    event = record.get("event")
    kickoff_time: datetime | None = None
    kickoff_unresolved = False
    if not isinstance(event, dict):
        errors.append("event object is required")
    else:
        for field in ("id", "home", "away", "timezone"):
            if not isinstance(event.get(field), str) or not event.get(field).strip():
                errors.append(f"event.{field} is required")
        if event.get("horizon") != "90m":
            errors.append("event.horizon must be 90m")
        if status == "BLOCKED" and "kickoff" in event and event["kickoff"] is None:
            kickoff_unresolved = True
        else:
            kickoff_time = _parse_timestamp(event.get("kickoff"), "event.kickoff", errors)

    data = record.get("data_quality")
    if not isinstance(data, dict):
        errors.append("data_quality object is required")
        data = {}
    independent_available = data.get("independent_baseline_available") is True
    cross_book = data.get("cross_book_available") is True
    late_snapshot = data.get("late_snapshot_available") is True
    blockers = data.get("blockers", [])
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item.strip() for item in blockers
    ):
        errors.append("data_quality.blockers must be a list of non-empty strings")
        blockers = []
    required_checkpoints = data.get("required_checkpoints", 0)
    captured_checkpoints = data.get("captured_checkpoints", 0)
    if not isinstance(required_checkpoints, int) or required_checkpoints < 0:
        errors.append("data_quality.required_checkpoints must be a non-negative integer")
    if not isinstance(captured_checkpoints, int) or captured_checkpoints < 0:
        errors.append("data_quality.captured_checkpoints must be a non-negative integer")
    if isinstance(required_checkpoints, int) and isinstance(captured_checkpoints, int):
        if captured_checkpoints > required_checkpoints and required_checkpoints > 0:
            warnings.append("captured_checkpoints exceeds required_checkpoints")
    if status != "BLOCKED" and blockers:
        errors.append("records with data_quality.blockers must use BLOCKED status")
    if kickoff_unresolved and not any("kickoff" in item.casefold() for item in blockers):
        errors.append("BLOCKED with event.kickoff=null requires an explicit kickoff blocker")

    probabilities = record.get("probabilities")
    if not isinstance(probabilities, dict):
        errors.append("probabilities object is required")
        probabilities = {}
    for layer_name in ("market_implied", "independent_baseline", "mcm_adjusted"):
        _validate_probability_layer(layer_name, probabilities.get(layer_name), errors)

    layer_times: dict[str, datetime] = {}
    for layer_name in ("market_implied", "independent_baseline", "mcm_adjusted"):
        layer = probabilities.get(layer_name)
        if isinstance(layer, dict):
            parsed = _parse_timestamp(
                layer.get("freeze_time"),
                f"probabilities.{layer_name}.freeze_time",
                errors,
            )
            if parsed is not None:
                layer_times[layer_name] = parsed
                if kickoff_time is not None and parsed >= kickoff_time:
                    errors.append(
                        f"probabilities.{layer_name}.freeze_time must be before kickoff"
                    )

    independent_layer = probabilities.get("independent_baseline")
    adjusted_layer = probabilities.get("mcm_adjusted")
    provenance = record.get("baseline_provenance")
    if independent_available:
        if independent_layer is None:
            errors.append("independent baseline is declared available but its probability layer is null")
        elif independent_layer.get("audited_market_used") is not False:
            errors.append("independent baseline must explicitly set audited_market_used to false")
        if not isinstance(provenance, dict):
            errors.append("available independent baseline requires baseline_provenance")
        else:
            if provenance.get("market_independence") not in {"verified_by_contract", "validated_input_contract"}:
                errors.append("baseline_provenance must prove market independence")
            if not isinstance(provenance.get("method"), str) or not provenance["method"].strip():
                errors.append("baseline_provenance.method is required")
            records = provenance.get("source_records")
            if not isinstance(records, list) or not records:
                errors.append("baseline_provenance.source_records is required")
            if provenance.get("input_mode") == "completed_matches_builder":
                sizes = provenance.get("sample_sizes")
                if not isinstance(sizes, dict) or any(not isinstance(sizes.get(key), int) or sizes[key] < 1 for key in ("league", "home_at_home", "away_away")):
                    errors.append("completed-match baseline requires audited sample sizes")
                if not isinstance(provenance.get("shrinkage_prior_matches"), (int, float)):
                    errors.append("completed-match baseline requires shrinkage metadata")
            elif provenance.get("input_mode") == "preaggregated":
                if not isinstance(provenance.get("unavailable_reason"), str) or not provenance["unavailable_reason"].strip():
                    errors.append("preaggregated baseline must disclose missing builder audit")
                else:
                    warnings.append("preaggregated baseline lacks completed-match sample audit")
            else:
                errors.append("baseline_provenance.input_mode is invalid")
    else:
        if independent_layer is not None or adjusted_layer is not None:
            errors.append("without an independent baseline, independent and MCM-adjusted layers must be null")
        if provenance is not None:
            errors.append("baseline_provenance must be null when independent baseline is unavailable")

    if adjusted_layer is not None and independent_layer is None:
        errors.append("MCM-adjusted probabilities require an independent baseline")
    if isinstance(adjusted_layer, dict):
        audit = adjusted_layer.get("adjustment_audit")
        if not isinstance(audit, dict):
            errors.append("MCM-adjusted layer requires adjustment_audit")
        else:
            audit_status = audit.get("status")
            deltas = audit.get("delta_one_x_two")
            if audit_status not in {"applied", "no_qualifying_adjustment"}:
                errors.append("adjustment_audit.status is invalid")
            total = _distribution_sum(deltas, ("home", "draw", "away")) if isinstance(deltas, dict) else None
            if total is None or not math.isclose(total, 0.0, abs_tol=1e-9):
                # Deltas may be negative, so distribution helper cannot validate them.
                if not isinstance(deltas, dict) or set(deltas) != {"home", "draw", "away"} or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in deltas.values()) or not math.isclose(sum(float(v) for v in deltas.values()), 0.0, abs_tol=1e-9):
                    errors.append("adjustment_audit deltas must be finite and sum to zero")
            if not isinstance(audit.get("reason"), str) or not audit["reason"].strip():
                errors.append("adjustment_audit.reason is required")
            if audit_status == "no_qualifying_adjustment":
                if isinstance(deltas, dict) and any(not math.isclose(float(v), 0.0, abs_tol=1e-12) for v in deltas.values() if isinstance(v, (int, float))):
                    errors.append("no_qualifying_adjustment requires zero deltas")
                for field in ("one_x_two", "goal_bands", "three_way_handicaps"):
                    if isinstance(independent_layer, dict) and not _same_probabilities(adjusted_layer.get(field), independent_layer.get(field)):
                        errors.append(f"no_qualifying_adjustment requires adjusted {field} to equal independent baseline")

    grade = record.get("value_grade")
    if grade not in GRADE_VALUE:
        errors.append("value_grade must be A, B, C, or D")

    if status == "MARKET-STRUCTURE-ONLY":
        if independent_available:
            errors.append("MARKET-STRUCTURE-ONLY cannot declare an independent baseline available")
        if grade in {"A", "B"}:
            errors.append("MARKET-STRUCTURE-ONLY caps value grade at C")
    elif status == "MCM-DEGRADED":
        if not independent_available:
            errors.append("MCM-DEGRADED requires an independent baseline; otherwise use MARKET-STRUCTURE-ONLY")
        if grade == "A":
            errors.append("MCM-DEGRADED caps value grade at B")
    elif status == "FULL-MCM":
        if not independent_available:
            errors.append("FULL-MCM requires an independent baseline")
        if not cross_book:
            errors.append("FULL-MCM requires meaningful cross-book comparison")
        if not late_snapshot:
            errors.append("FULL-MCM requires a late observation")
        if isinstance(required_checkpoints, int) and required_checkpoints > 0:
            if captured_checkpoints < required_checkpoints:
                errors.append("FULL-MCM requires all declared monitoring checkpoints")
        if probabilities.get("market_implied") is None:
            errors.append("FULL-MCM requires a market-implied probability layer")
        if adjusted_layer is None:
            errors.append("FULL-MCM requires an MCM-adjusted probability layer")
    elif status == "BLOCKED":
        if not blockers:
            errors.append("BLOCKED requires at least one explicit data_quality.blocker")
        if grade != "D":
            errors.append("BLOCKED requires value grade D")
        if any(
            probabilities.get(name) is not None
            for name in ("market_implied", "independent_baseline", "mcm_adjusted")
        ):
            errors.append("BLOCKED cannot publish probability layers")

    capital = record.get("capital_intent")
    if not isinstance(capital, dict):
        errors.append("capital_intent object is required")
        capital = {}
    missing_capital = sorted(CAPITAL_REQUIRED - set(capital))
    if missing_capital:
        errors.append("capital_intent missing fields: " + ", ".join(missing_capital))
    capital_time = _parse_timestamp(
        capital.get("freeze_time"), "capital_intent.freeze_time", errors
    )
    if capital_time is not None and kickoff_time is not None and capital_time >= kickoff_time:
        errors.append("capital_intent.freeze_time must be before kickoff")

    independent_time = layer_times.get("independent_baseline")
    market_time = layer_times.get("market_implied")
    adjusted_time = layer_times.get("mcm_adjusted")
    if independent_time is not None and market_time is not None:
        if independent_time > market_time:
            errors.append(
                "independent baseline must be frozen no later than the audited market layer"
            )
    if adjusted_time is not None:
        for input_name, input_time in (
            ("independent baseline", independent_time),
            ("market layer", market_time),
        ):
            if input_time is not None and adjusted_time < input_time:
                errors.append(f"MCM-adjusted layer cannot predate the {input_name}")
    if capital_time is not None:
        for input_name, input_time in (
            ("independent baseline", independent_time),
            ("market layer", market_time),
        ):
            if input_time is not None and capital_time < input_time:
                errors.append(f"capital freeze cannot predate the {input_name}")

    ci_grade = capital.get("ci_grade")
    if ci_grade not in CI_VALUE:
        errors.append("capital_intent.ci_grade is invalid")
        ci_numeric = -1
    else:
        ci_numeric = CI_VALUE[ci_grade]
    label = capital.get("candidate_label")
    if label not in CAPITAL_LABELS:
        errors.append("capital_intent.candidate_label is invalid")
    evidence_groups = capital.get("independent_evidence_groups")
    if not isinstance(evidence_groups, list):
        errors.append("capital_intent.independent_evidence_groups must be a list")
        evidence_groups = []
    elif len(set(evidence_groups)) != len(evidence_groups):
        errors.append("capital evidence groups must be unique; correlated duplicates are not independent")
    leg_independence = capital.get("leg_independence")
    if not isinstance(leg_independence, dict) or set(leg_independence) != {"attraction", "protection", "feasibility"} or any(not isinstance(value, bool) for value in leg_independence.values()):
        errors.append("capital_intent.leg_independence must contain three booleans")
        leg_independence = {}
    if capital.get("loop_status") == "closed" and not all(leg_independence.get(key) is True for key in ("attraction", "protection", "feasibility")):
        errors.append("closed capital loop requires three independent legs")
    if capital.get("attraction_basis") == "market_price_accessibility" and leg_independence.get("attraction") is not False:
        errors.append("market-price attraction cannot be marked independent")
    if label == "inducement_candidate" and leg_independence.get("attraction") is not True:
        errors.append("inducement candidate requires an independent attraction leg")

    if not independent_available:
        if ci_numeric > 1:
            errors.append("without an independent baseline, capital intent is capped at CI-1")
        if label not in {"unresolved", "none"}:
            errors.append("without an independent baseline, capital candidate label must be unresolved or none")

    if label in {"straight_support_candidate", "inducement_candidate", "upset_candidate"}:
        if not independent_available:
            errors.append("directional capital candidate labels require an independent baseline")
        if ci_numeric < 2:
            errors.append("directional capital candidate labels require CI-2 or CI-3")
        if len(evidence_groups) < 2:
            errors.append("directional capital candidate labels require at least two independent evidence groups")
        if capital.get("red_team_passed") is not True:
            errors.append("directional capital candidate labels require a passed red-team screen")
        for key in (
            "capital_direction", "combined_direction", "without_capital_direction"
        ):
            if not isinstance(capital.get(key), str) or not capital[key].strip():
                errors.append(f"directional capital labels require capital_intent.{key}")

    if ci_numeric == 3:
        if status != "FULL-MCM":
            errors.append("CI-3 is permitted only for FULL-MCM fixtures")
        if capital.get("loop_status") != "closed":
            errors.append("CI-3 requires a closed capital loop")
        if len(evidence_groups) < 3:
            errors.append("CI-3 requires at least three independent evidence groups")

    if status == "FULL-MCM" and capital.get("red_team_passed") is not True:
        errors.append("FULL-MCM requires a passed capital red-team screen")
    if status == "BLOCKED":
        if ci_numeric != 0:
            errors.append("BLOCKED requires CI-0")
        if label not in {"unresolved", "none"}:
            errors.append("BLOCKED capital label must be unresolved or none")
        for key in ("capital_direction", "combined_direction", "without_capital_direction"):
            if capital.get(key) not in {None, ""}:
                errors.append(f"BLOCKED cannot publish capital_intent.{key}")

    ranking = record.get("unified_ranking")
    if not isinstance(ranking, list):
        errors.append("unified_ranking must be a list")
        ranking = []
    if status != "BLOCKED" and len(ranking) < 2:
        errors.append("non-BLOCKED reports require first and second alternative candidates")
    probability_sources: set[str] = set()
    ranks: list[int] = []
    for index, row in enumerate(ranking):
        if not isinstance(row, dict):
            errors.append(f"unified_ranking[{index}] must be an object")
            continue
        market_type = row.get("market_type")
        if market_type not in {"1X2", "three_way_handicap"}:
            errors.append(f"unified_ranking[{index}] cannot contain Asian or unknown market type")
        probability_source = row.get("probability_source")
        if probability_source not in {
            "market_implied",
            "independent_score_matrix",
            "mcm_adjusted_score_matrix",
        }:
            errors.append(f"unified_ranking[{index}].probability_source is invalid")
        else:
            probability_sources.add(probability_source)
        probability = row.get("probability")
        if not isinstance(probability, (int, float)) or isinstance(probability, bool) or not 0 <= probability <= 1:
            errors.append(f"unified_ranking[{index}].probability must be between 0 and 1")
        rank = row.get("rank")
        if not isinstance(rank, int) or rank < 1:
            errors.append(f"unified_ranking[{index}].rank must be a positive integer")
        else:
            ranks.append(rank)
        paths = row.get("covered_paths")
        if not isinstance(paths, list) or not paths:
            errors.append(f"unified_ranking[{index}].covered_paths is required")
        if market_type == "three_way_handicap":
            handicap = row.get("handicap")
            if not isinstance(handicap, dict):
                errors.append(f"unified_ranking[{index}] three-way handicap requires exact line and side")
            else:
                if handicap.get("side") not in {"home", "away"}:
                    errors.append(f"unified_ranking[{index}].handicap.side is invalid")
                line = handicap.get("line")
                if not isinstance(line, int) or isinstance(line, bool):
                    errors.append(f"unified_ranking[{index}].handicap.line must be an integer")
                if handicap.get("outcome") not in HANDICAP_OUTCOMES:
                    errors.append(
                        f"unified_ranking[{index}].handicap.outcome is invalid"
                    )
    if len(probability_sources) > 1:
        errors.append("all unified-ranking candidates must use the same probability source")
    if len(ranks) != len(set(ranks)):
        errors.append("unified_ranking ranks must be unique")
    if ranks and sorted(ranks) != list(range(1, len(ranks) + 1)):
        errors.append("unified_ranking ranks must be contiguous from 1")
    ranked_probabilities = sorted(
        (
            (row.get("rank"), float(row.get("probability")))
            for row in ranking
            if isinstance(row, dict)
            and isinstance(row.get("rank"), int)
            and not isinstance(row.get("rank"), bool)
            and isinstance(row.get("probability"), (int, float))
            and not isinstance(row.get("probability"), bool)
        ),
        key=lambda item: item[0],
    )
    counterfactual = record.get("ranking_counterfactual")
    counterfactual_applied = isinstance(counterfactual, dict) and counterfactual.get("applied") is True
    if not counterfactual_applied and any(
        earlier[1] < later[1]
        for earlier, later in zip(ranked_probabilities, ranked_probabilities[1:])
    ):
        errors.append("unified_ranking must be ordered by descending probability")
    if status == "MARKET-STRUCTURE-ONLY" and probability_sources - {"market_implied"}:
        errors.append("MARKET-STRUCTURE-ONLY ranking must use market_implied probabilities")
    source_layer = {
        "market_implied": "market_implied",
        "independent_score_matrix": "independent_baseline",
        "mcm_adjusted_score_matrix": "mcm_adjusted",
    }
    for source in probability_sources:
        if probabilities.get(source_layer[source]) is None:
            errors.append(
                f"unified-ranking source {source} requires its corresponding probability layer"
            )

    ordinary_coverage = record.get("ordinary_1x2_coverage")
    pool_scope = record.get("candidate_pool_scope")
    if schema_version == CURRENT_SCHEMA_VERSION and not isinstance(ordinary_coverage, dict):
        errors.append("ordinary_1x2_coverage object is required by schema 1.6.3")
        ordinary_coverage = {}
    if schema_version == CURRENT_SCHEMA_VERSION and pool_scope not in {"unified", "handicap_only"}:
        errors.append("candidate_pool_scope must be unified or handicap_only")
    if isinstance(ordinary_coverage, dict):
        ordinary_status = ordinary_coverage.get("status")
        if ordinary_status not in {"observed", "not_displayed", "unreadable_or_unverified"}:
            errors.append("ordinary_1x2_coverage.status is invalid")
        ranked_one_x_two_preview = {
            row.get("selection") for row in ranking
            if isinstance(row, dict) and row.get("market_type") == "1X2"
        }
        source_name_preview = next(iter(probability_sources), None)
        source_layer_preview = {
            "market_implied": "market_implied",
            "independent_score_matrix": "independent_baseline",
            "mcm_adjusted_score_matrix": "mcm_adjusted",
        }.get(source_name_preview)
        selected_preview = probabilities.get(source_layer_preview) if source_layer_preview else None
        layer_one_x_two = selected_preview.get("one_x_two") if isinstance(selected_preview, dict) else None
        if ordinary_status == "observed":
            if ranked_one_x_two_preview != {"home", "draw", "away"}:
                errors.append("observed ordinary 1X2 requires all three outcomes in the candidate pool")
            if not isinstance(layer_one_x_two, dict):
                errors.append("observed ordinary 1X2 requires a complete probability layer")
            if pool_scope == "handicap_only":
                errors.append("observed ordinary 1X2 cannot use handicap_only scope")
            if not isinstance(ordinary_coverage.get("source_timestamp"), str) or not ordinary_coverage["source_timestamp"].strip():
                errors.append("observed ordinary 1X2 requires source_timestamp")
        elif ordinary_status == "not_displayed":
            if ranked_one_x_two_preview or isinstance(layer_one_x_two, dict):
                errors.append("not_displayed ordinary 1X2 cannot publish ordinary candidates or probabilities")
            if pool_scope != "handicap_only":
                errors.append("not_displayed ordinary 1X2 requires handicap_only scope")
        elif ordinary_status == "unreadable_or_unverified":
            if status != "BLOCKED":
                errors.append("unreadable or unverified ordinary 1X2 blocks a final ranking")
    coverage = record.get("three_way_handicap_coverage")
    if schema_version in {"1.6.2", "1.6.3"} and not isinstance(coverage, dict):
        errors.append(f"three_way_handicap_coverage object is required by schema {schema_version}")
        coverage = {}
    if isinstance(coverage, dict):
        coverage_status = coverage.get("status")
        observed_markets = coverage.get("observed_markets")
        candidate_pool_complete = coverage.get("candidate_pool_complete")
        if coverage_status not in {
            "observed", "not_displayed", "unreadable_or_unverified"
        }:
            errors.append("three_way_handicap_coverage.status is invalid")
        if not isinstance(observed_markets, list):
            errors.append("three_way_handicap_coverage.observed_markets must be a list")
            observed_markets = []
        observed_keys: set[tuple[str, int]] = set()
        for index, offer in enumerate(observed_markets):
            if not isinstance(offer, dict):
                errors.append(
                    f"three_way_handicap_coverage.observed_markets[{index}] must be an object"
                )
                continue
            side = offer.get("side")
            line = offer.get("line")
            if side not in {"home", "away"} or isinstance(line, bool) or not isinstance(line, int):
                errors.append(
                    f"three_way_handicap_coverage.observed_markets[{index}] needs side and integer line"
                )
                continue
            key = (side, line)
            if key in observed_keys:
                errors.append("three_way_handicap_coverage contains duplicate observed markets")
            observed_keys.add(key)
        source_name = next(iter(probability_sources), None)
        selected_layer_name = source_layer.get(source_name) if source_name else None
        selected_layer = probabilities.get(selected_layer_name) if selected_layer_name else None
        layer_keys: set[tuple[str, int]] = set()
        if isinstance(selected_layer, dict):
            for offer in selected_layer.get("three_way_handicaps", []):
                if isinstance(offer, dict) and offer.get("side") in {"home", "away"} and isinstance(offer.get("line"), int) and not isinstance(offer.get("line"), bool):
                    layer_keys.add((offer["side"], offer["line"]))
        ranked_one_x_two = {
            row.get("selection")
            for row in ranking
            if isinstance(row, dict) and row.get("market_type") == "1X2"
        }
        ranked_handicaps: dict[tuple[str, int], list[str]] = {}
        for row in ranking:
            if not isinstance(row, dict) or row.get("market_type") != "three_way_handicap":
                continue
            handicap = row.get("handicap")
            if not isinstance(handicap, dict):
                continue
            side = handicap.get("side")
            line = handicap.get("line")
            outcome = handicap.get("outcome")
            if side in {"home", "away"} and isinstance(line, int) and not isinstance(line, bool) and outcome in HANDICAP_OUTCOMES:
                ranked_handicaps.setdefault((side, line), []).append(outcome)
        if status != "BLOCKED" and schema_version != CURRENT_SCHEMA_VERSION and ranked_one_x_two != {"home", "draw", "away"}:
            errors.append("unified candidate pool must contain all three ordinary 1X2 outcomes")
        if status != "BLOCKED" and schema_version == CURRENT_SCHEMA_VERSION and pool_scope == "handicap_only" and not observed_keys:
            errors.append("handicap_only scope requires at least one verified three-way handicap market")
        if coverage_status == "observed":
            if not observed_keys:
                errors.append("observed three-way handicap coverage requires at least one market")
            if candidate_pool_complete is not True:
                errors.append("observed three-way handicap coverage must declare candidate_pool_complete=true")
            if not isinstance(coverage.get("source_timestamp"), str) or not coverage["source_timestamp"].strip():
                errors.append("observed three-way handicap coverage requires source_timestamp")
            else:
                observed_time = _parse_timestamp(
                    coverage["source_timestamp"],
                    "three_way_handicap_coverage.source_timestamp",
                    errors,
                )
                if observed_time is not None and kickoff_time is not None and observed_time >= kickoff_time:
                    errors.append("three-way handicap source_timestamp must be before kickoff")
            if layer_keys != observed_keys:
                errors.append("declared probability layer must contain every observed three-way handicap market")
            for key in observed_keys:
                outcomes = ranked_handicaps.get(key, [])
                if set(outcomes) != HANDICAP_OUTCOMES or len(outcomes) != 3:
                    errors.append(
                        f"unified candidate pool must contain handicap win/draw/loss exactly once for {key[0]} {key[1]:+d}"
                    )
        elif coverage_status == "not_displayed":
            if observed_keys or layer_keys or ranked_handicaps:
                errors.append("not_displayed handicap status cannot contain handicap offers or candidates")
            if candidate_pool_complete is not True:
                errors.append("not_displayed handicap status must declare candidate_pool_complete=true")
        elif coverage_status == "unreadable_or_unverified":
            if status != "BLOCKED":
                errors.append("unreadable or unverified three-way handicap coverage blocks a final unified ranking")
            if candidate_pool_complete is not False:
                errors.append("unreadable handicap coverage must declare candidate_pool_complete=false")
            if not isinstance(coverage.get("reason"), str) or not coverage["reason"].strip():
                errors.append("unreadable handicap coverage requires an explicit reason")
    for index, row in enumerate(ranking):
        if not isinstance(row, dict):
            continue
        source = row.get("probability_source")
        layer_name = source_layer.get(source)
        layer = probabilities.get(layer_name) if layer_name else None
        probability = row.get("probability")
        if not isinstance(layer, dict) or not isinstance(probability, (int, float)):
            continue
        expected: Any = None
        if row.get("market_type") == "1X2":
            selection = row.get("selection")
            one_x_two = layer.get("one_x_two")
            if selection not in {"home", "draw", "away"}:
                errors.append(
                    f"unified_ranking[{index}].selection must be home, draw or away for 1X2"
                )
            elif isinstance(one_x_two, dict):
                expected = one_x_two.get(selection)
        elif row.get("market_type") == "three_way_handicap":
            handicap = row.get("handicap")
            offers = layer.get("three_way_handicaps", [])
            if isinstance(handicap, dict) and isinstance(offers, list):
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    if (
                        offer.get("side") == handicap.get("side")
                        and offer.get("line") == handicap.get("line")
                    ):
                        offer_probabilities = offer.get("probabilities")
                        if isinstance(offer_probabilities, dict):
                            expected = offer_probabilities.get(handicap.get("outcome"))
                        break
        if not isinstance(expected, (int, float)):
            errors.append(
                f"unified_ranking[{index}] has no matching probability in its declared layer"
            )
        elif not math.isclose(float(probability), float(expected), abs_tol=1e-9):
            errors.append(
                f"unified_ranking[{index}].probability does not match its declared layer"
            )
    if status == "BLOCKED" and ranking:
        errors.append("BLOCKED cannot publish a unified ranking")

    if not isinstance(counterfactual, dict):
        errors.append("ranking_counterfactual object is required")
    else:
        without = counterfactual.get("without_capital")
        with_capital = counterfactual.get("with_capital")
        max_gap = counterfactual.get("max_probability_gap")
        if not isinstance(without, list) or not isinstance(with_capital, list):
            errors.append("ranking_counterfactual requires without_capital and with_capital lists")
        else:
            def signature(rows: list[Any]) -> list[tuple[Any, Any, Any, Any]]:
                return sorted((repr(row.get("market_type")), repr(row.get("selection")), repr(row.get("probability")), repr(row.get("probability_source")))
                              for row in rows if isinstance(row, dict))
            if len(without) != len(with_capital) or signature(without) != signature(with_capital):
                errors.append("capital counterfactual must preserve every candidate and probability")
            if signature(ranking) != signature(with_capital) or [row.get("selection") for row in ranking if isinstance(row, dict)] != [row.get("selection") for row in with_capital if isinstance(row, dict)]:
                errors.append("unified_ranking must equal ranking_counterfactual.with_capital")
            first_changed = bool(without and with_capital and isinstance(without[0], dict) and isinstance(with_capital[0], dict) and without[0].get("selection") != with_capital[0].get("selection"))
            if counterfactual.get("applied") is not first_changed:
                errors.append("ranking_counterfactual.applied must equal a first-choice change")
            ordered = [row.get("probability") for row in without if isinstance(row, dict)]
            if any(not isinstance(v, (int, float)) for v in ordered) or any(a < b for a, b in zip(ordered, ordered[1:])):
                errors.append("without-capital ranking must be ordered by descending probability")
            if first_changed:
                if CI_VALUE.get(ci_grade, -1) < 2 or capital.get("red_team_passed") is not True or capital.get("capital_direction") not in {"home", "draw", "away"}:
                    errors.append("capital reordering requires CI-2+, red-team pass and a direction")
                if not isinstance(max_gap, (int, float)) or isinstance(max_gap, bool) or not 0 <= float(max_gap) <= 0.05:
                    errors.append("capital counterfactual max_probability_gap must be between 0 and 0.05")
                elif without and with_capital and float(without[0]["probability"]) - float(with_capital[0]["probability"]) > float(max_gap) + 1e-12:
                    errors.append("capital reordering exceeded the declared near-tie gap")
                if with_capital and isinstance(with_capital[0], dict):
                    winner = with_capital[0]
                    winner_direction = winner.get("selection") if winner.get("market_type") == "1X2" else None
                    handicap = winner.get("handicap")
                    if isinstance(handicap, dict) and handicap.get("side") in {"home", "away"}:
                        if handicap.get("outcome") == "side_win":
                            winner_direction = handicap["side"]
                        elif handicap.get("outcome") == "side_loss":
                            winner_direction = "away" if handicap["side"] == "home" else "home"
                    if winner_direction != capital.get("capital_direction"):
                        errors.append("capital-reordered first choice must align with capital_direction")
        if counterfactual.get("probabilities_changed") is not False:
            errors.append("capital counterfactual cannot change probabilities")
        if (capital.get("incremental_effect") == "changed") is not (counterfactual.get("applied") is True):
            errors.append("capital incremental_effect must close against the ranking counterfactual")

    shadow = record.get("next_phase_shadow")
    if shadow is not None:
        if not isinstance(shadow, dict):
            errors.append("next_phase_shadow must be an object when present")
        else:
            if shadow.get("schema_version") != "mcm-next-phase-shadow/v1" or shadow.get("mode") != "observe_only":
                errors.append("next_phase_shadow must use the observe-only v1 schema")
            if shadow.get("stable_weights_changed") is not False or shadow.get("probability_delta_applied") != 0 or shadow.get("live_ranking_changed") is not False:
                errors.append("next_phase_shadow cannot alter live weights, probabilities, or ranking")
            if shadow.get("status") == "available":
                if shadow.get("uses_audited_market") is not False:
                    errors.append("available next_phase_shadow must be market-free")
                if not isinstance(shadow.get("candidate_models"), dict) or len(shadow["candidate_models"]) < 3:
                    errors.append("available next_phase_shadow requires control and candidate models")
                manifest = shadow.get("experiment_manifest")
                if not isinstance(manifest, dict) or manifest.get("promotion_eligible") is not False:
                    errors.append("next_phase_shadow must remain ineligible for automatic promotion")
                threshold = shadow.get("capital_threshold_shadow")
                if (not isinstance(threshold, dict) or threshold.get("mode") != "observe_only"
                        or threshold.get("applied") is not False or threshold.get("calibration_required") is not True
                        or threshold.get("probability_delta_applied") != 0):
                    errors.append("capital threshold shadow must remain unapplied and calibration-required")
            elif shadow.get("status") != "unavailable":
                errors.append("next_phase_shadow.status is invalid")

    asian = record.get("asian_handicap")
    if not isinstance(asian, dict):
        errors.append("asian_handicap object is required")
    else:
        if asian.get("kept_separate") is not True:
            errors.append("Asian two-way handicap must be kept separate from unified ranking")
        if asian.get("present") is True:
            if asian.get("orientation_verified") is not True or not asian.get("odds_format"):
                if asian.get("ah_grade") != "AH-D":
                    errors.append("unverified Asian orientation/format must be graded AH-D")

    for field in ("strongest_falsifier", "reorder_condition"):
        if not isinstance(record.get(field), str) or not record.get(field).strip():
            errors.append(f"{field} is required")

    if record.get("engine_version") == "1.6.3+evidence1":
        quality = record.get("market_quality")
        if not isinstance(quality, dict):
            errors.append("new-engine records require a market_quality audit")
        else:
            try:
                expected_top_two = market_quality.top_two_coverage(
                    ranking if isinstance(ranking, list) else []
                )
                if quality.get("top_two_settlement") != expected_top_two:
                    errors.append("market_quality top-two coverage disagrees with settlement paths")
            except (TypeError, ValueError, KeyError) as exc:
                errors.append(f"market_quality settlement audit failed: {exc}")
            if quality.get("value_status") != "unproven_without_independent_calibrated_probability":
                errors.append("market price diagnostics cannot claim a proven value edge")
        if record.get("value_grade_meaning") != "legacy_evidence_completeness_cap_not_expected_return":
            errors.append("legacy value_grade must be identified as evidence quality, not return")
        event_id = event.get("id") if isinstance(event, dict) else None
        kickoff = event.get("kickoff") if isinstance(event, dict) else None
        if isinstance(event_id, str) and isinstance(kickoff, str):
            computed = evidence_integrity.audit(
                event_id, kickoff, record.get("monitoring_evidence")
            )
            if record.get("monitoring_audit") != computed:
                errors.append("monitoring_audit does not match artifact-bound checkpoint evidence")
            if data.get("required_checkpoints") != computed["required_checkpoints"]:
                errors.append("required_checkpoints must be derived from the bound monitor config")
            if data.get("captured_checkpoints") != computed["captured_checkpoints"]:
                errors.append("captured_checkpoints must be derived from valid snapshots")
            if data.get("late_snapshot_available") is not computed["late_snapshot_available"]:
                errors.append("late_snapshot_available must be derived from the final valid snapshot")
            if data.get("cross_book_available") is True and not computed["cross_book_available"]:
                errors.append("cross-book claim lacks two bound, current bookmaker offers")
            if status == "FULL-MCM" and (
                computed["status"] != "verified"
                or not computed["late_snapshot_available"]
                or not computed["cross_book_available"]
            ):
                errors.append("FULL-MCM requires verified configuration and every planned odds snapshot")

    return errors, warnings


def _probability_layer() -> dict[str, Any]:
    return {
        "one_x_two": {"home": 0.50, "draw": 0.28, "away": 0.22},
        "goal_bands": {"0-1": 0.20, "2-3": 0.50, "4-6": 0.28, "7+": 0.02},
        "method": "self-test independent Poisson",
        "freeze_time": "2026-08-28T12:00:00+08:00",
        "audited_market_used": False,
        "three_way_handicaps": [
            {
                "side": "home",
                "line": -1,
                "probabilities": {
                    "side_win": 0.30,
                    "handicap_draw": 0.22,
                    "side_loss": 0.48,
                },
            }
        ],
        "adjustment_audit": {
            "status": "no_qualifying_adjustment",
            "delta_one_x_two": {"home": 0.0, "draw": 0.0, "away": 0.0},
            "reason": "self-test no qualifying adjustment",
        },
    }


def _base_record() -> dict[str, Any]:
    record = {
        "schema_version": "1.6.3",
        "event": {
            "id": "self-test-1",
            "home": "Home",
            "away": "Away",
            "kickoff": "2026-08-29T02:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "horizon": "90m",
        },
        "report_status": "FULL-MCM",
        "data_quality": {
            "grade": "A",
            "independent_baseline_available": True,
            "cross_book_available": True,
            "late_snapshot_available": True,
            "required_checkpoints": 4,
            "captured_checkpoints": 4,
            "blockers": [],
            "sources": ["independent-team-data", "book-a", "book-b"],
        },
        "probabilities": {
            "market_implied": _probability_layer(),
            "independent_baseline": _probability_layer(),
            "mcm_adjusted": _probability_layer(),
        },
        "baseline_provenance": {
            "input_mode": "completed_matches_builder",
            "method": "self-test independent sporting results",
            "market_independence": "verified_by_contract",
            "source_records": [{"source": "self-test", "observed_at": "2026-08-28T12:00:00+08:00"}],
            "sample_sizes": {"league": 100, "home_at_home": 10, "away_away": 10},
            "shrinkage_prior_matches": 6,
        },
        "ordinary_1x2_coverage": {
            "status": "observed",
            "candidate_pool_complete": True,
            "source_timestamp": "2026-08-28T12:00:00+08:00",
            "reason": "source displays all three ordinary outcomes",
        },
        "three_way_handicap_coverage": {
            "status": "observed",
            "observed_markets": [{"side": "home", "line": -1}],
            "candidate_pool_complete": True,
            "source_timestamp": "2026-08-28T12:00:00+08:00",
            "reason": "source displays a verified home -1 three-way handicap",
        },
        "candidate_pool_scope": "unified",
        "unified_ranking": [
            {
                "rank": 1,
                "market_type": "1X2",
                "selection": "home",
                "probability": 0.50,
                "probability_source": "mcm_adjusted_score_matrix",
                "covered_paths": ["home_win"],
                "evidence_grade": "A",
                "strongest_contradiction": "draw mass",
            },
            {
                "rank": 2,
                "market_type": "three_way_handicap",
                "selection": "home_-1_side_loss",
                "probability": 0.48,
                "probability_source": "mcm_adjusted_score_matrix",
                "covered_paths": ["draw_or_away_win"],
                "evidence_grade": "B",
                "strongest_contradiction": "home-win mass",
                "handicap": {"side": "home", "line": -1, "outcome": "side_loss"},
            },
            {
                "rank": 3,
                "market_type": "three_way_handicap",
                "selection": "home_-1_side_win",
                "probability": 0.30,
                "probability_source": "mcm_adjusted_score_matrix",
                "covered_paths": ["home_by_2_plus"],
                "evidence_grade": "B",
                "strongest_contradiction": "one-goal home-win mass",
                "handicap": {"side": "home", "line": -1, "outcome": "side_win"},
            },
            {
                "rank": 4,
                "market_type": "1X2",
                "selection": "draw",
                "probability": 0.28,
                "probability_source": "mcm_adjusted_score_matrix",
                "covered_paths": ["draw"],
                "evidence_grade": "A",
                "strongest_contradiction": "home mass",
            },
            {
                "rank": 5,
                "market_type": "three_way_handicap",
                "selection": "home_-1_draw",
                "probability": 0.22,
                "probability_source": "mcm_adjusted_score_matrix",
                "covered_paths": ["home_by_exactly_1"],
                "evidence_grade": "B",
                "strongest_contradiction": "two-goal tail",
                "handicap": {
                    "side": "home",
                    "line": -1,
                    "outcome": "handicap_draw",
                },
            },
            {
                "rank": 6,
                "market_type": "1X2",
                "selection": "away",
                "probability": 0.22,
                "probability_source": "mcm_adjusted_score_matrix",
                "covered_paths": ["away_win"],
                "evidence_grade": "A",
                "strongest_contradiction": "home mass",
            },
        ],
        "asian_handicap": {
            "present": False,
            "kept_separate": True,
            "orientation_verified": None,
            "odds_format": None,
            "ah_grade": "N/A",
        },
        "capital_intent": {
            "freeze_time": "2026-08-28T20:00:00+08:00",
            "market_only_direction": "home",
            "sporting_baseline_direction": "home",
            "attraction": {"direction": "home", "evidence": ["brand narrative"]},
            "protection": {"direction": "home", "evidence": ["cross-book key-line resistance"]},
            "feasibility": {"direction": "home", "evidence": ["independent score matrix"]},
            "loop_status": "closed",
            "ci_grade": "CI-3",
            "capital_direction": "home",
            "combined_direction": "home",
            "without_capital_direction": "home",
            "incremental_effect": "strengthened",
            "independent_evidence_groups": [
                "independent sporting baseline",
                "cross-book line structure",
                "verified late information window",
            ],
            "candidate_label": "straight_support_candidate",
            "red_team_passed": True,
            "hypothesis_status": "inducement_rejected_by_current_evidence",
            "non_intent_alternative": "ordinary information repricing",
            "attraction_basis": "measured_positioning",
            "leg_independence": {"attraction": True, "protection": True, "feasibility": True},
            "diagnostics": {"mode": "self-test"},
            "strongest_support": "three independent layers align",
            "strongest_contradiction": "draw remains material",
            "falsifier": "late line release",
            "reorder_condition": "verified lineup reversal",
        },
        "value_grade": "A",
        "strongest_falsifier": "late line release",
        "reorder_condition": "verified lineup reversal",
    }
    record["ranking_counterfactual"] = {
        "without_capital": copy.deepcopy(record["unified_ranking"]),
        "with_capital": copy.deepcopy(record["unified_ranking"]),
        "applied": False,
        "max_probability_gap": 0.02,
        "probabilities_changed": False,
        "reason": "capital direction already leads",
    }
    return record


def run_self_test() -> int:
    valid_full = _base_record()
    valid_market_only = _base_record()
    valid_market_only["report_status"] = "MARKET-STRUCTURE-ONLY"
    valid_market_only["data_quality"]["grade"] = "C"
    valid_market_only["data_quality"]["independent_baseline_available"] = False
    valid_market_only["probabilities"]["independent_baseline"] = None
    valid_market_only["probabilities"]["mcm_adjusted"] = None
    valid_market_only["baseline_provenance"] = None
    valid_market_only["unified_ranking"] = copy.deepcopy(valid_market_only["unified_ranking"])
    for candidate in valid_market_only["unified_ranking"]:
        candidate["probability_source"] = "market_implied"
    valid_market_only["ranking_counterfactual"]["without_capital"] = copy.deepcopy(valid_market_only["unified_ranking"])
    valid_market_only["ranking_counterfactual"]["with_capital"] = copy.deepcopy(valid_market_only["unified_ranking"])
    valid_market_only["capital_intent"]["sporting_baseline_direction"] = None
    valid_market_only["capital_intent"]["feasibility"] = {"direction": None, "evidence": []}
    valid_market_only["capital_intent"]["loop_status"] = "none"
    valid_market_only["capital_intent"]["ci_grade"] = "CI-1"
    valid_market_only["capital_intent"]["candidate_label"] = "unresolved"
    valid_market_only["capital_intent"]["incremental_effect"] = "unavailable"
    valid_market_only["capital_intent"]["independent_evidence_groups"] = ["single market family"]
    valid_market_only["capital_intent"]["leg_independence"] = {"attraction": False, "protection": False, "feasibility": False}
    valid_market_only["capital_intent"]["attraction_basis"] = "market_price_accessibility"
    valid_market_only["value_grade"] = "C"

    invalid_circular = copy.deepcopy(valid_market_only)
    invalid_circular["probabilities"]["mcm_adjusted"] = _probability_layer()
    invalid_circular["capital_intent"]["ci_grade"] = "CI-2"
    invalid_circular["capital_intent"]["candidate_label"] = "inducement_candidate"

    invalid_asian_mix = copy.deepcopy(valid_full)
    invalid_asian_mix["unified_ranking"][0]["market_type"] = "asian_handicap"

    invalid_missing_handicap_outcome = copy.deepcopy(valid_full)
    invalid_missing_handicap_outcome["unified_ranking"] = [
        row for row in invalid_missing_handicap_outcome["unified_ranking"]
        if not (
            row.get("market_type") == "three_way_handicap"
            and row.get("handicap", {}).get("outcome") == "handicap_draw"
        )
    ]
    for rank, row in enumerate(invalid_missing_handicap_outcome["unified_ranking"], 1):
        row["rank"] = rank
    invalid_missing_handicap_outcome["ranking_counterfactual"]["without_capital"] = copy.deepcopy(invalid_missing_handicap_outcome["unified_ranking"])
    invalid_missing_handicap_outcome["ranking_counterfactual"]["with_capital"] = copy.deepcopy(invalid_missing_handicap_outcome["unified_ranking"])

    invalid_missing_one_x_two = copy.deepcopy(valid_full)
    invalid_missing_one_x_two["unified_ranking"] = [
        row for row in invalid_missing_one_x_two["unified_ranking"]
        if not (row.get("market_type") == "1X2" and row.get("selection") == "away")
    ]
    for rank, row in enumerate(invalid_missing_one_x_two["unified_ranking"], 1):
        row["rank"] = rank
    invalid_missing_one_x_two["ranking_counterfactual"]["without_capital"] = copy.deepcopy(invalid_missing_one_x_two["unified_ranking"])
    invalid_missing_one_x_two["ranking_counterfactual"]["with_capital"] = copy.deepcopy(invalid_missing_one_x_two["unified_ranking"])

    invalid_missing_coverage = copy.deepcopy(valid_full)
    del invalid_missing_coverage["three_way_handicap_coverage"]

    valid_handicap_only = copy.deepcopy(valid_market_only)
    valid_handicap_only["ordinary_1x2_coverage"] = {
        "status": "not_displayed",
        "candidate_pool_complete": True,
        "source_timestamp": None,
        "reason": "source explicitly shows no ordinary 1X2",
    }
    valid_handicap_only["candidate_pool_scope"] = "handicap_only"
    valid_handicap_only["probabilities"]["market_implied"]["one_x_two"] = None
    valid_handicap_only["probabilities"]["market_implied"].setdefault("unavailable_fields", {})["one_x_two"] = "verified not displayed"
    valid_handicap_only["unified_ranking"] = [
        row for row in valid_handicap_only["unified_ranking"]
        if row.get("market_type") == "three_way_handicap"
    ]
    for rank, row in enumerate(valid_handicap_only["unified_ranking"], 1):
        row["rank"] = rank
    valid_handicap_only["ranking_counterfactual"]["without_capital"] = copy.deepcopy(valid_handicap_only["unified_ranking"])
    valid_handicap_only["ranking_counterfactual"]["with_capital"] = copy.deepcopy(valid_handicap_only["unified_ranking"])
    valid_handicap_only["capital_intent"]["market_only_direction"] = None
    valid_handicap_only["capital_intent"]["combined_direction"] = None
    valid_handicap_only["capital_intent"]["without_capital_direction"] = None

    invalid_handicap_only_missing_outcome = copy.deepcopy(valid_handicap_only)
    invalid_handicap_only_missing_outcome["unified_ranking"] = invalid_handicap_only_missing_outcome["unified_ranking"][:-1]
    for rank, row in enumerate(invalid_handicap_only_missing_outcome["unified_ranking"], 1):
        row["rank"] = rank
    invalid_handicap_only_missing_outcome["ranking_counterfactual"]["without_capital"] = copy.deepcopy(invalid_handicap_only_missing_outcome["unified_ranking"])
    invalid_handicap_only_missing_outcome["ranking_counterfactual"]["with_capital"] = copy.deepcopy(invalid_handicap_only_missing_outcome["unified_ranking"])

    valid_not_displayed = copy.deepcopy(valid_full)
    valid_not_displayed["three_way_handicap_coverage"] = {
        "status": "not_displayed",
        "observed_markets": [],
        "candidate_pool_complete": True,
        "source_timestamp": None,
        "reason": "source does not display a three-way handicap market",
    }
    for layer in valid_not_displayed["probabilities"].values():
        if isinstance(layer, dict):
            layer["three_way_handicaps"] = []
    valid_not_displayed["unified_ranking"] = [
        row for row in valid_not_displayed["unified_ranking"]
        if row.get("market_type") == "1X2"
    ]
    for rank, row in enumerate(valid_not_displayed["unified_ranking"], 1):
        row["rank"] = rank
    valid_not_displayed["ranking_counterfactual"]["without_capital"] = copy.deepcopy(valid_not_displayed["unified_ranking"])
    valid_not_displayed["ranking_counterfactual"]["with_capital"] = copy.deepcopy(valid_not_displayed["unified_ranking"])

    valid_blocked = copy.deepcopy(valid_market_only)
    valid_blocked["report_status"] = "BLOCKED"
    valid_blocked["data_quality"]["blockers"] = ["home/away orientation unresolved"]
    valid_blocked["probabilities"] = {
        "market_implied": None,
        "independent_baseline": None,
        "mcm_adjusted": None,
    }
    valid_blocked["ordinary_1x2_coverage"] = {
        "status": "unreadable_or_unverified",
        "candidate_pool_complete": False,
        "source_timestamp": None,
        "reason": "home/away orientation unresolved",
    }
    valid_blocked["three_way_handicap_coverage"] = {
        "status": "unreadable_or_unverified",
        "observed_markets": [],
        "candidate_pool_complete": False,
        "source_timestamp": None,
        "reason": "home/away orientation unresolved",
    }
    valid_blocked["unified_ranking"] = []
    valid_blocked["ranking_counterfactual"] = {"without_capital": [], "with_capital": [], "applied": False, "max_probability_gap": 0.02, "probabilities_changed": False, "reason": "blocked"}
    valid_blocked["value_grade"] = "D"
    valid_blocked["capital_intent"]["ci_grade"] = "CI-0"
    valid_blocked["capital_intent"]["capital_direction"] = None
    valid_blocked["capital_intent"]["combined_direction"] = None
    valid_blocked["capital_intent"]["without_capital_direction"] = None

    invalid_missing_source_layer = copy.deepcopy(valid_full)
    invalid_missing_source_layer["probabilities"]["mcm_adjusted"] = None

    invalid_ranking_probability = copy.deepcopy(valid_full)
    invalid_ranking_probability["unified_ranking"][0]["probability"] = 0.999

    invalid_ranking_order = copy.deepcopy(valid_full)
    invalid_ranking_order["unified_ranking"][0]["rank"] = 2
    invalid_ranking_order["unified_ranking"][1]["rank"] = 1

    invalid_directionless_capital = copy.deepcopy(valid_full)
    invalid_directionless_capital["capital_intent"]["capital_direction"] = None
    invalid_directionless_capital["capital_intent"]["combined_direction"] = None
    invalid_directionless_capital["capital_intent"]["without_capital_direction"] = None

    valid_blocked_unknown_kickoff = copy.deepcopy(valid_blocked)
    valid_blocked_unknown_kickoff["event"]["kickoff"] = None
    valid_blocked_unknown_kickoff["data_quality"]["blockers"] = [
        "kickoff time unresolved"
    ]

    invalid_blocked_missing_kickoff = copy.deepcopy(valid_blocked_unknown_kickoff)
    del invalid_blocked_missing_kickoff["event"]["kickoff"]

    invalid_full_with_blocker = copy.deepcopy(valid_full)
    invalid_full_with_blocker["data_quality"]["blockers"] = [
        "home/away orientation unresolved"
    ]

    invalid_bad_kickoff = copy.deepcopy(valid_full)
    invalid_bad_kickoff["event"]["kickoff"] = "not-a-time"

    invalid_post_kickoff_freeze = copy.deepcopy(valid_full)
    invalid_post_kickoff_freeze["probabilities"]["market_implied"][
        "freeze_time"
    ] = "2026-08-29T03:00:00+08:00"

    invalid_baseline_after_market = copy.deepcopy(valid_full)
    invalid_baseline_after_market["probabilities"]["independent_baseline"][
        "freeze_time"
    ] = "2026-08-28T13:00:00+08:00"

    valid_shadow = copy.deepcopy(valid_full)
    valid_shadow["next_phase_shadow"] = {
        "schema_version": "mcm-next-phase-shadow/v1", "mode": "observe_only", "status": "available",
        "stable_weights_changed": False, "probability_delta_applied": 0, "live_ranking_changed": False,
        "uses_audited_market": False, "candidate_models": {"control": {}, "poisson": {}, "dc": {}},
        "experiment_manifest": {"promotion_eligible": False},
        "capital_threshold_shadow": {"mode": "observe_only", "applied": False, "calibration_required": True, "probability_delta_applied": 0},
    }
    invalid_shadow_delta = copy.deepcopy(valid_shadow)
    invalid_shadow_delta["next_phase_shadow"]["probability_delta_applied"] = 0.01
    invalid_threshold_application = copy.deepcopy(valid_shadow)
    invalid_threshold_application["next_phase_shadow"]["capital_threshold_shadow"]["applied"] = True

    cases = [
        ("valid FULL-MCM", valid_full, True),
        ("valid MARKET-STRUCTURE-ONLY", valid_market_only, True),
        ("reject circular/high-CI market-only", invalid_circular, False),
        ("reject Asian in unified ranking", invalid_asian_mix, False),
        ("reject omitted handicap outcome", invalid_missing_handicap_outcome, False),
        ("reject omitted ordinary 1X2 outcome", invalid_missing_one_x_two, False),
        ("reject missing handicap coverage declaration", invalid_missing_coverage, False),
        ("valid handicap-only three-way candidate pool", valid_handicap_only, True),
        ("reject incomplete handicap-only candidate pool", invalid_handicap_only_missing_outcome, False),
        ("valid source with no displayed handicap", valid_not_displayed, True),
        ("valid BLOCKED", valid_blocked, True),
        ("reject ranking without its probability layer", invalid_missing_source_layer, False),
        ("reject ranking probability mismatch", invalid_ranking_probability, False),
        ("reject inverted ranking order", invalid_ranking_order, False),
        ("reject directionless capital label", invalid_directionless_capital, False),
        ("allow BLOCKED unresolved kickoff", valid_blocked_unknown_kickoff, True),
        ("reject BLOCKED missing kickoff field", invalid_blocked_missing_kickoff, False),
        ("reject FULL-MCM with blockers", invalid_full_with_blocker, False),
        ("reject unparseable kickoff", invalid_bad_kickoff, False),
        ("reject post-kickoff freeze", invalid_post_kickoff_freeze, False),
        ("reject baseline frozen after market", invalid_baseline_after_market, False),
        ("valid observe-only next-phase shadow", valid_shadow, True),
        ("reject next-phase probability mutation", invalid_shadow_delta, False),
        ("reject applied capital threshold candidate", invalid_threshold_application, False),
    ]
    failed = False
    for name, record, should_pass in cases:
        errors, _ = validate_record(record)
        passed = not errors
        if passed != should_pass:
            failed = True
            print(f"SELF-TEST FAIL: {name}: {errors}")
        else:
            print(f"SELF-TEST PASS: {name}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", nargs="*", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if not args.records:
        parser.error("provide at least one fixture JSON record or use --self-test")

    failed = False
    for path in args.records:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL {path}: cannot read JSON: {exc}")
            failed = True
            continue
        errors, warnings = validate_record(record)
        for warning in warnings:
            print(f"WARN {path}: {warning}")
        if errors:
            failed = True
            for error in errors:
                print(f"ERROR {path}: {error}")
        else:
            print(f"PASS {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

