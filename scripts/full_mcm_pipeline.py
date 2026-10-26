#!/usr/bin/env python3
"""Build validated fixture records and a Chinese report for the full MCM workflow.

The pipeline is deliberately input-driven.  It can build a market-free baseline
from frozen completed-match data, but never invents missing observations or
promotes historical rules.  In auto mode the capital card is inferred from
independent sporting, cross-book and positioning evidence.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import importlib.util
import json
import math
import statistics
from pathlib import Path
import sys
from typing import Any


VERSION = "1.6.3+evidence1"
SCHEMA = "mcm-full-batch/v1"
DIRECTIONS = ("home", "draw", "away")
GOAL_BANDS = ("0-1", "2-3", "4-6", "7+")
CI_VALUE = {"CI-0": 0, "CI-1": 1, "CI-2": 2, "CI-3": 3}
CAPITAL_LABELS = {
    "straight_support_candidate",
    "inducement_candidate",
    "upset_candidate",
    "unresolved",
    "none",
}
ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load required component: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = _load(ROOT / "independent_score_matrix.py", "mcm_full_baseline")
SPORTING = _load(ROOT / "sporting_baseline_builder.py", "mcm_sporting_builder")
CAPITAL = _load(ROOT / "capital_intent_engine.py", "mcm_capital_engine")
SHADOW = _load(ROOT / "shadow_model_lab.py", "mcm_shadow_lab")
VALIDATOR = _load(ROOT / "validate_report.py", "mcm_full_validator")
MARKET_QUALITY = _load(ROOT / "market_quality.py", "mcm_market_quality")
INTEGRITY = _load(ROOT / "evidence_integrity.py", "mcm_evidence_integrity")
FREEZE = _load(ROOT / "freeze_manifest.py", "mcm_freeze_manifest")


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{label} must be between zero and one")
    return result


def _prices(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(DIRECTIONS):
        raise ValueError(f"{label} must contain exactly home, draw and away")
    result: dict[str, float] = {}
    for direction in DIRECTIONS:
        number = value[direction]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f"{label}.{direction} must be decimal odds")
        number = float(number)
        if not math.isfinite(number) or number <= 1:
            raise ValueError(f"{label}.{direction} must be decimal odds greater than one")
        result[direction] = number
    return result


def _devig(prices: dict[str, float]) -> dict[str, float]:
    raw = {key: 1.0 / value for key, value in prices.items()}
    total = sum(raw.values())
    return {key: value / total for key, value in raw.items()}


def _handicap_prices(value: Any, label: str) -> dict[str, float]:
    outcomes = ("side_win", "handicap_draw", "side_loss")
    if not isinstance(value, dict) or set(value) != set(outcomes):
        raise ValueError(
            f"{label} must contain exactly side_win, handicap_draw and side_loss"
        )
    return _prices(
        {
            "home": value["side_win"],
            "draw": value["handicap_draw"],
            "away": value["side_loss"],
        },
        label,
    ) | {}


def _market_layer(fixture: dict[str, Any], kickoff: datetime) -> tuple[dict[str, Any] | None, int]:
    observations = fixture.get("market_observations", [])
    if not isinstance(observations, list):
        raise ValueError("market_observations must be a list")
    latest: dict[str, tuple[datetime, dict[str, float], dict[str, Any]]] = {}
    for index, row in enumerate(observations):
        if not isinstance(row, dict):
            raise ValueError(f"market_observations[{index}] must be an object")
        book = row.get("bookmaker")
        if not isinstance(book, str) or not book.strip():
            raise ValueError(f"market_observations[{index}].bookmaker is required")
        observed = _time(row.get("observed_at"), f"market_observations[{index}].observed_at")
        if observed >= kickoff:
            raise ValueError(f"market_observations[{index}] must be pre-kickoff")
        fair = _devig(_prices(row.get("prices"), f"market_observations[{index}].prices"))
        current = latest.get(book)
        if current is None or observed > current[0]:
            latest[book] = (observed, fair, row)
    selected = list(latest.values())
    one_x_two = ({
        direction: sum(row[1][direction] for row in selected) / len(selected)
        for direction in DIRECTIONS
    } if selected else None)
    latest_time = max((row[0] for row in selected), default=None)
    goal_bands = None
    unavailable: dict[str, str] = {}
    if one_x_two is None:
        unavailable["one_x_two"] = "ordinary 1X2 verified as not displayed"
    exact = fixture.get("exact_total_market")
    if exact is not None:
        if not isinstance(exact, dict):
            raise ValueError("exact_total_market must be an object")
        exact_time = _time(exact.get("observed_at"), "exact_total_market.observed_at")
        if exact_time >= kickoff:
            raise ValueError("exact_total_market must be pre-kickoff")
        odds = exact.get("odds")
        keys = {"0", "1", "2", "3", "4", "5", "6", "7+"}
        if not isinstance(odds, dict) or set(odds) != keys:
            raise ValueError("exact_total_market.odds must contain 0..6 and 7+")
        raw: dict[str, float] = {}
        for key in keys:
            number = odds[key]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or float(number) <= 1:
                raise ValueError(f"exact_total_market.odds.{key} must be decimal odds greater than one")
            raw[key] = 1.0 / float(number)
        total = sum(raw.values())
        goal_bands = {
            "0-1": (raw["0"] + raw["1"]) / total,
            "2-3": (raw["2"] + raw["3"]) / total,
            "4-6": (raw["4"] + raw["5"] + raw["6"]) / total,
            "7+": raw["7+"] / total,
        }
        latest_time = max(latest_time, exact_time) if latest_time is not None else exact_time
    else:
        unavailable["goal_bands"] = "complete exact-total 0..6 and 7+ market unavailable"
    handicap_observations = fixture.get("three_way_handicap_observations", [])
    if not isinstance(handicap_observations, list):
        raise ValueError("three_way_handicap_observations must be a list")
    latest_handicaps: dict[tuple[str, int, str], tuple[datetime, dict[str, float]]] = {}
    for index, row in enumerate(handicap_observations):
        if not isinstance(row, dict):
            raise ValueError(f"three_way_handicap_observations[{index}] must be an object")
        side = row.get("side")
        line = row.get("line")
        book = row.get("bookmaker")
        if side not in {"home", "away"} or isinstance(line, bool) or not isinstance(line, int):
            raise ValueError(f"three_way_handicap_observations[{index}] needs side and integer line")
        if not isinstance(book, str) or not book.strip():
            raise ValueError(f"three_way_handicap_observations[{index}].bookmaker is required")
        observed = _time(row.get("observed_at"), f"three_way_handicap_observations[{index}].observed_at")
        if observed >= kickoff:
            raise ValueError(f"three_way_handicap_observations[{index}] must be pre-kickoff")
        prices = _handicap_prices(row.get("prices"), f"three_way_handicap_observations[{index}].prices")
        fair_1x2 = _devig(prices)
        fair = {
            "side_win": fair_1x2["home"],
            "handicap_draw": fair_1x2["draw"],
            "side_loss": fair_1x2["away"],
        }
        key = (side, line, book)
        current = latest_handicaps.get(key)
        if current is None or observed > current[0]:
            latest_handicaps[key] = (observed, fair)
    handicap_groups: dict[tuple[str, int], list[tuple[datetime, dict[str, float]]]] = {}
    for (side, line, _book), value in latest_handicaps.items():
        handicap_groups.setdefault((side, line), []).append(value)
    three_way_handicaps = []
    for (side, line), rows in sorted(handicap_groups.items()):
        three_way_handicaps.append({
            "side": side,
            "line": line,
            "probabilities": {
                outcome: sum(row[1][outcome] for row in rows) / len(rows)
                for outcome in ("side_win", "handicap_draw", "side_loss")
            },
        })
        offer_time = max(row[0] for row in rows)
        latest_time = max(latest_time, offer_time) if latest_time is not None else offer_time
    if latest_time is None:
        return None, 0
    return {
        "one_x_two": one_x_two,
        "goal_bands": goal_bands,
        "three_way_handicaps": three_way_handicaps,
        "method": "equal-weight latest-per-book proportional de-vig for 1X2 and observed three-way handicap; exact-total aggregation when available",
        "freeze_time": latest_time.isoformat(),
        "audited_market_used": True,
        "book_count": len(selected),
        "unavailable_fields": unavailable,
        "market_structure": [row[2] for row in selected],
    }, len(selected)


def _direction(matrix: list[list[float]], home_goals: int, away_goals: int) -> str:
    return "home" if home_goals > away_goals else "draw" if home_goals == away_goals else "away"


def _derive(matrix: list[list[float]], offers: list[dict[str, Any]]) -> dict[str, Any]:
    one_x_two = {key: 0.0 for key in DIRECTIONS}
    goal_bands = {key: 0.0 for key in GOAL_BANDS}
    scores: list[dict[str, Any]] = []
    handicaps = [
        {"side": item["side"], "line": item["line"], "probabilities": {"side_win": 0.0, "handicap_draw": 0.0, "side_loss": 0.0}}
        for item in offers
    ]
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            one_x_two[_direction(matrix, home_goals, away_goals)] += probability
            total = home_goals + away_goals
            band = "0-1" if total <= 1 else "2-3" if total <= 3 else "4-6" if total <= 6 else "7+"
            goal_bands[band] += probability
            scores.append({"score": f"{home_goals}-{away_goals}", "probability": probability})
            for offer in handicaps:
                margin = home_goals - away_goals if offer["side"] == "home" else away_goals - home_goals
                adjusted = margin + offer["line"]
                outcome = "side_win" if adjusted > 0 else "handicap_draw" if adjusted == 0 else "side_loss"
                offer["probabilities"][outcome] += probability
    scores.sort(key=lambda item: item["probability"], reverse=True)
    return {"one_x_two": one_x_two, "goal_bands": goal_bands, "three_way_handicaps": handicaps, "top_scores": scores[:10]}


def _adjusted_layer(baseline: dict[str, Any], fixture: dict[str, Any], freeze_time: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    adjustments = fixture.get("sporting_adjustments", [])
    if not isinstance(adjustments, list):
        raise ValueError("sporting_adjustments must be a list")
    deltas = {key: 0.0 for key in DIRECTIONS}
    frozen: list[dict[str, Any]] = []
    cutoff = _time(freeze_time, "adjustment freeze_time")
    for index, item in enumerate(adjustments):
        if not isinstance(item, dict) or item.get("direction") not in DIRECTIONS:
            raise ValueError(f"sporting_adjustments[{index}] requires a valid direction")
        delta = float(item.get("delta", 0.0))
        if not math.isfinite(delta) or abs(delta) > 0.08:
            raise ValueError(f"sporting_adjustments[{index}].delta exceeds ±0.08")
        observed = _time(item.get("observed_at"), f"sporting_adjustments[{index}].observed_at")
        if observed > cutoff:
            raise ValueError(f"sporting_adjustments[{index}] is after the adjustment freeze")
        source = str(item.get("source", "")).strip()
        group = str(item.get("evidence_group", "")).strip()
        reason = str(item.get("reason", "")).strip()
        market_terms = ("odds", "market", "bookmaker", "price", "盘口", "赔率", "水位")
        if not source or not group or not reason or any(term in (source + group + reason).casefold() for term in market_terms):
            raise ValueError(f"sporting_adjustments[{index}] must be frozen non-market evidence")
        deltas[item["direction"]] += delta
        frozen.append(dict(item))
    if not math.isclose(sum(deltas.values()), 0.0, abs_tol=1e-10):
        raise ValueError("sporting adjustment deltas must sum to zero")
    if any(abs(value) > 0.08 + 1e-12 for value in deltas.values()):
        raise ValueError("cumulative sporting adjustments exceed ±0.08")
    original = baseline["probabilities"]["one_x_two"]
    target = {key: original[key] + deltas[key] for key in DIRECTIONS}
    if any(value <= 0 or value >= 1 for value in target.values()):
        raise ValueError("sporting adjustments produce an invalid probability")
    matrix = baseline["probabilities"]["score_matrix"]
    adjusted_matrix: list[list[float]] = []
    for home_goals, row in enumerate(matrix):
        adjusted_row = []
        for away_goals, probability in enumerate(row):
            outcome = _direction(matrix, home_goals, away_goals)
            adjusted_row.append(probability * target[outcome] / original[outcome])
        adjusted_matrix.append(adjusted_row)
    mass = sum(sum(row) for row in adjusted_matrix)
    adjusted_matrix = [[value / mass for value in row] for row in adjusted_matrix]
    derived = _derive(adjusted_matrix, baseline["probabilities"]["three_way_handicaps"])
    half_full = baseline["probabilities"].get("half_full")
    if isinstance(half_full, dict):
        adjusted_half_full = {}
        for path, probability in half_full.items():
            full_direction = path.split("/", 1)[1]
            adjusted_half_full[path] = probability * target[full_direction] / original[full_direction]
        half_mass = sum(adjusted_half_full.values())
        derived["half_full"] = {key: value / half_mass for key, value in adjusted_half_full.items()}
    else:
        derived["half_full"] = None
    derived.update({
        "score_matrix": adjusted_matrix,
        "method": "independent score matrix reweighted only by frozen non-market sporting adjustments",
        "freeze_time": freeze_time,
        "audited_market_used": False,
        "adjustments": frozen,
        "adjustment_audit": {
            "status": "applied" if frozen else "no_qualifying_adjustment",
            "delta_one_x_two": deltas,
            "reason": "frozen non-market sporting evidence" if frozen else "no qualifying frozen non-market update; adjusted layer equals independent baseline",
        },
    })
    return derived, frozen


def _ranking(
    layer: dict[str, Any],
    probability_source: str = "mcm_adjusted_score_matrix",
    evidence_grade: str = "B",
    strongest_contradiction: str = "model uncertainty and unobserved late information",
    include_ordinary: bool = True,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if include_ordinary:
        one_x_two = layer.get("one_x_two")
        if not isinstance(one_x_two, dict):
            raise ValueError("ordinary 1X2 is declared observed but its three outcomes are unavailable")
        for direction, probability in one_x_two.items():
            candidates.append({"market_type": "1X2", "selection": direction, "probability": probability, "covered_paths": [f"90m_{direction}"]})
    for offer in layer.get("three_way_handicaps", []):
        for outcome, probability in offer["probabilities"].items():
            operator = {"side_win": "> 0", "handicap_draw": "= 0", "side_loss": "< 0"}[outcome]
            side_label = "主队" if offer["side"] == "home" else "客队"
            candidates.append({
                "market_type": "three_way_handicap",
                "selection": f"{offer['side']}_{offer['line']:+d}_{outcome}",
                "probability": probability,
                "covered_paths": [f"{side_label}90分钟净胜球 {offer['line']:+d} {operator}"],
                "handicap": {"side": offer["side"], "line": offer["line"], "outcome": outcome},
            })
    candidates.sort(key=lambda item: item["probability"], reverse=True)
    for rank, item in enumerate(candidates, 1):
        item.update({"rank": rank, "model_probability_rank": rank, "probability_source": probability_source, "evidence_grade": evidence_grade, "strongest_contradiction": strongest_contradiction})
    return candidates


def _candidate_direction(candidate: dict[str, Any] | None) -> str | None:
    if not isinstance(candidate, dict):
        return None
    if candidate.get("market_type") == "1X2":
        return candidate.get("selection") if candidate.get("selection") in DIRECTIONS else None
    handicap = candidate.get("handicap")
    if not isinstance(handicap, dict) or handicap.get("side") not in {"home", "away"}:
        return None
    if handicap.get("outcome") == "side_win":
        return handicap["side"]
    if handicap.get("outcome") == "side_loss":
        return "away" if handicap["side"] == "home" else "home"
    return None


def _capital_counterfactual(ranking: list[dict[str, Any]], capital: dict[str, Any]) -> dict[str, Any]:
    without = copy.deepcopy(ranking)
    for index, item in enumerate(without, 1):
        item.setdefault("model_probability_rank", index)
        item["rank"] = index
        item["capital_tiebreak"] = False
    diagnostics = capital.get("diagnostics", {})
    thresholds = diagnostics.get("dynamic_thresholds", {}) if isinstance(diagnostics, dict) else {}
    threshold_values = [float(value) for value in thresholds.values()
                        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))]
    max_gap = min(0.05, max(0.015, statistics.median(threshold_values) / 2)) if threshold_values else 0.02
    with_capital = copy.deepcopy(without)
    reason = "capital evidence did not satisfy CI-2/red-team/directional gates"
    applied = False
    ci = CI_VALUE.get(capital.get("ci_grade"), 0)
    direction = capital.get("capital_direction")
    if with_capital and ci >= 2 and capital.get("red_team_passed") is True and direction in DIRECTIONS:
        top_probability = float(with_capital[0]["probability"])
        eligible = next((item for item in with_capital
                         if _candidate_direction(item) == direction
                         and top_probability - float(item["probability"]) <= max_gap + 1e-12), None)
        if eligible is None:
            reason = "capital-aligned candidate lies outside the predeclared near-tie band"
        elif eligible is with_capital[0]:
            reason = "capital direction already leads the probability ranking"
        else:
            with_capital.remove(eligible)
            with_capital.insert(0, eligible)
            eligible["capital_tiebreak"] = True
            applied = True
            reason = "CI-2+ red-team-passed capital evidence resolved a probability near-tie"
    for index, item in enumerate(with_capital, 1):
        item["rank"] = index
    return {
        "without_capital": without, "with_capital": with_capital, "applied": applied,
        "max_probability_gap": max_gap, "probabilities_changed": False, "reason": reason,
    }


def _capital_card(fixture: dict[str, Any], market: dict[str, Any] | None, baseline: dict[str, Any] | None, adjusted: dict[str, Any] | None, freeze_time: str) -> dict[str, Any]:
    raw = fixture.get("capital_intent", {"mode": "auto"})
    if not isinstance(raw, dict):
        raise ValueError("capital_intent must be an object")
    if raw.get("mode", "explicit") == "auto":
        return CAPITAL.infer(fixture, market, baseline, adjusted, freeze_time)
    market_one_x_two = market.get("one_x_two") if isinstance(market, dict) else None
    market_direction = max(market_one_x_two, key=market_one_x_two.get) if isinstance(market_one_x_two, dict) else None
    sporting_direction = max(baseline["probabilities"]["one_x_two"], key=baseline["probabilities"]["one_x_two"].get) if baseline else None
    combined_direction = max(adjusted["one_x_two"], key=adjusted["one_x_two"].get) if adjusted else market_direction
    ci_grade = raw.get("ci_grade", "CI-1" if market else "CI-0")
    label = raw.get("candidate_label", "unresolved" if market else "none")
    groups = raw.get("independent_evidence_groups", [])
    red_team = raw.get("red_team_passed", False)
    if ci_grade not in CI_VALUE or label not in CAPITAL_LABELS or not isinstance(groups, list):
        raise ValueError("capital_intent grade, label or evidence groups are invalid")
    if baseline is None and (CI_VALUE[ci_grade] > 1 or label not in {"unresolved", "none"}):
        raise ValueError("capital intent without an independent baseline is capped at CI-1/unresolved")
    if label not in {"unresolved", "none"} and (CI_VALUE[ci_grade] < 2 or len(set(groups)) < 2 or red_team is not True):
        raise ValueError("directional capital labels require CI-2+, two independent groups and red-team pass")
    def leg(name: str, fallback_direction: str | None) -> dict[str, Any]:
        value = raw.get(name, {})
        if not isinstance(value, dict):
            raise ValueError(f"capital_intent.{name} must be an object")
        evidence = value.get("evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(item, str) or not item.strip() for item in evidence):
            raise ValueError(f"capital_intent.{name}.evidence must be a list of text")
        return {"direction": value.get("direction", fallback_direction), "evidence": evidence}
    capital_direction = raw.get("capital_direction")
    without = raw.get("without_capital_direction", sporting_direction or market_direction)
    leg_independence = raw.get("leg_independence", {"attraction": False, "protection": False, "feasibility": baseline is not None})
    loop_status = "none" if raw.get("loop_status") == "no_loop" else raw.get("loop_status", "none")
    if loop_status == "closed" and (not isinstance(leg_independence, dict) or not all(leg_independence.get(name) is True for name in ("attraction", "protection", "feasibility"))):
        loop_status = "partial"
    if ci_grade == "CI-3" and loop_status != "closed":
        ci_grade = "CI-2"
    return {
        "freeze_time": freeze_time,
        "market_only_direction": market_direction,
        "sporting_baseline_direction": sporting_direction,
        "attraction": leg("attraction", None),
        "protection": leg("protection", None),
        "feasibility": leg("feasibility", sporting_direction),
        "attraction_basis": raw.get("attraction_basis", "explicit"),
        "leg_independence": leg_independence,
        "loop_status": loop_status,
        "ci_grade": ci_grade,
        "capital_direction": capital_direction,
        "combined_direction": raw.get("combined_direction", combined_direction),
        "without_capital_direction": without,
        "incremental_effect": raw.get("incremental_effect", "none" if baseline else "unavailable"),
        "independent_evidence_groups": list(dict.fromkeys(groups)),
        "candidate_label": label,
        "red_team_passed": red_team,
        "hypothesis_status": raw.get("hypothesis_status", "explicit_card_unscored"),
        "non_intent_alternative": raw.get("non_intent_alternative", "ordinary repricing, model disagreement, liquidity or stale quotes"),
        "strongest_support": raw.get("strongest_support", "no capital conclusion beyond frozen evidence"),
        "strongest_contradiction": raw.get("strongest_contradiction", "competing non-intent explanations remain"),
        "falsifier": raw.get("falsifier", "verified late evidence reverses the protected direction"),
        "reorder_condition": raw.get("reorder_condition", "two independent evidence groups reverse before kickoff"),
        "diagnostics": raw.get("diagnostics", {"mode": "explicit"}),
    }


def _history_shadow(batch: dict[str, Any]) -> dict[str, Any]:
    value = batch.get("historical_shadow", {"mode": "off", "stable_weights_changed": False, "rules": []})
    if not isinstance(value, dict):
        raise ValueError("historical_shadow must be an object")
    if value.get("mode") not in {"off", "observe_only"} or value.get("stable_weights_changed") is not False:
        raise ValueError("historical rules may only run off/observe_only and cannot change stable weights")
    rules = value.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("historical_shadow.rules must be a list")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or rule.get("status") != "observe_only" or rule.get("probability_delta", 0) != 0:
            raise ValueError(f"historical_shadow.rules[{index}] is not a safe observe-only rule")
    return value


def _record(fixture: dict[str, Any], batch: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    event = fixture.get("event")
    if not isinstance(event, dict):
        raise ValueError("fixture.event is required")
    for field in ("id", "home", "away", "kickoff", "timezone"):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise ValueError(f"event.{field} is required")
    if event.get("horizon") != "90m":
        raise ValueError("event.horizon must be 90m")
    kickoff = _time(event["kickoff"], "event.kickoff")
    market, book_count = _market_layer(fixture, kickoff)
    baseline_audit = None
    sporting_data = None
    baseline_input = fixture.get("independent_baseline_input")
    if baseline_input is None and isinstance(fixture.get("independent_sporting_data_path"), str):
        sporting_path = Path(fixture["independent_sporting_data_path"]).expanduser()
        try:
            sporting_data = json.loads(sporting_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"independent_sporting_data_path could not be read: {exc}") from None
        baseline_input, baseline_audit = SPORTING.build_baseline_input(sporting_data)
    if baseline_input is None and isinstance(fixture.get("independent_sporting_data"), dict):
        sporting_data = fixture["independent_sporting_data"]
        baseline_input, baseline_audit = SPORTING.build_baseline_input(sporting_data)
    market_handicap_offers = [
        {"side": offer["side"], "line": offer["line"]}
        for offer in (market or {}).get("three_way_handicaps", [])
    ]
    declared_coverage = fixture.get("three_way_handicap_coverage")
    if declared_coverage is not None and not isinstance(declared_coverage, dict):
        raise ValueError("three_way_handicap_coverage must be an object")
    declared_status = declared_coverage.get("status") if isinstance(declared_coverage, dict) else None
    declared_offers = declared_coverage.get("observed_markets", []) if isinstance(declared_coverage, dict) else []
    if declared_status is not None and declared_status not in {"observed", "not_displayed", "unreadable_or_unverified"}:
        raise ValueError("three_way_handicap_coverage.status is invalid")
    if not isinstance(declared_offers, list):
        raise ValueError("three_way_handicap_coverage.observed_markets must be a list")
    if declared_status == "unreadable_or_unverified":
        raise ValueError("unreadable or unverified three-way handicap blocks a final unified ranking")
    observed_offers = declared_offers if declared_status == "observed" else market_handicap_offers
    ordinary_coverage = fixture.get("ordinary_1x2_coverage")
    if ordinary_coverage is not None and not isinstance(ordinary_coverage, dict):
        raise ValueError("ordinary_1x2_coverage must be an object")
    ordinary_status = ordinary_coverage.get("status") if isinstance(ordinary_coverage, dict) else ("observed" if market and isinstance(market.get("one_x_two"), dict) else "not_displayed")
    if ordinary_status not in {"observed", "not_displayed", "unreadable_or_unverified"}:
        raise ValueError("ordinary_1x2_coverage.status is invalid")
    if ordinary_status == "unreadable_or_unverified":
        raise ValueError("unreadable or unverified ordinary 1X2 blocks a final ranking")
    if ordinary_status == "observed" and (market is None or not isinstance(market.get("one_x_two"), dict)):
        raise ValueError("ordinary 1X2 is declared observed but its three outcomes are unavailable")
    if ordinary_status == "not_displayed" and market is not None and isinstance(market.get("one_x_two"), dict):
        raise ValueError("not_displayed ordinary 1X2 status conflicts with supplied ordinary prices")
    if isinstance(baseline_input, dict) and observed_offers:
        normalized_offers = []
        for index, offer in enumerate(observed_offers):
            if not isinstance(offer, dict) or offer.get("side") not in {"home", "away"} or isinstance(offer.get("line"), bool) or not isinstance(offer.get("line"), int):
                raise ValueError(f"three_way_handicap_coverage.observed_markets[{index}] needs side and integer line")
            normalized_offers.append({"side": offer["side"], "line": offer["line"]})
        existing = baseline_input.get("three_way_handicaps", [])
        existing_keys = {(offer.get("side"), offer.get("line")) for offer in existing if isinstance(offer, dict)}
        observed_keys = {(offer["side"], offer["line"]) for offer in normalized_offers}
        if existing_keys and existing_keys != observed_keys:
            raise ValueError("independent baseline handicap offers must match observed three-way handicap markets")
        baseline_input = copy.deepcopy(baseline_input)
        baseline_input["three_way_handicaps"] = normalized_offers
    baseline = BASELINE.build_baseline(baseline_input) if isinstance(baseline_input, dict) else None
    if baseline_audit is not None and baseline is not None:
        baseline_audit = {**baseline_audit, "input_mode": "completed_matches_builder", "source_records": baseline["source_records"]}
    next_phase_shadow = (SHADOW.build_shadow(sporting_data) if isinstance(sporting_data, dict) else {
        "schema_version": SHADOW.SCHEMA, "engine_version": SHADOW.VERSION, "mode": "observe_only",
        "status": "unavailable", "stable_weights_changed": False, "probability_delta_applied": 0,
        "live_ranking_changed": False, "reason": "provider-neutral completed-match history unavailable",
    })
    if baseline and baseline["event_id"] != event["id"]:
        raise ValueError("independent baseline event_id mismatch")
    if baseline and _time(baseline["freeze_time"], "baseline.freeze_time") >= kickoff:
        raise ValueError("independent baseline must be pre-kickoff")
    if baseline and market and _time(baseline["freeze_time"], "baseline.freeze_time") > _time(market["freeze_time"], "market.freeze_time"):
        raise ValueError("independent baseline must freeze no later than the audited market")
    freeze_time = fixture.get("analysis_freeze_time") or (market["freeze_time"] if market else baseline["freeze_time"] if baseline else None)
    if freeze_time is None or _time(freeze_time, "analysis_freeze_time") >= kickoff:
        raise ValueError("analysis_freeze_time must be pre-kickoff")
    adjusted = None
    if baseline:
        adjusted, _ = _adjusted_layer(baseline, fixture, freeze_time)
    capital = _capital_card(fixture, market, baseline, adjusted, freeze_time)
    monitoring_evidence = fixture.get("monitoring_evidence")
    monitoring_audit = INTEGRITY.audit(event["id"], event["kickoff"], monitoring_evidence)
    required = monitoring_audit["required_checkpoints"]
    captured = monitoring_audit["captured_checkpoints"]
    late = monitoring_audit["late_snapshot_available"]
    cross_book = book_count >= 2 and monitoring_audit["cross_book_available"]
    complete_monitoring = required > 0 and captured >= required
    half_full_available = bool(baseline and isinstance(baseline["probabilities"].get("half_full"), dict))
    if baseline is None:
        status = "MARKET-STRUCTURE-ONLY"
        reasons = ["independent sporting baseline unavailable"]
    elif market is None:
        status = "MCM-DEGRADED"
        reasons = ["audited market layer unavailable"]
    elif cross_book and late and complete_monitoring and capital["red_team_passed"] and half_full_available:
        status = "FULL-MCM"
        reasons = []
    else:
        status = "MCM-DEGRADED"
        reasons = []
        if not cross_book: reasons.append("meaningful cross-book coverage incomplete")
        if not late: reasons.append("late observation missing")
        if not complete_monitoring: reasons.append("declared monitoring checkpoints incomplete")
        if not capital["red_team_passed"]: reasons.append("capital red-team screen not passed")
        if not half_full_available: reasons.append("independent first-half share unavailable")
        if monitoring_audit["reasons"]: reasons.extend(monitoring_audit["reasons"])
    if status != "FULL-MCM" and capital["ci_grade"] == "CI-3":
        raise ValueError("CI-3 is available only to FULL-MCM fixtures")
    source_layer = adjusted if adjusted is not None else market
    if source_layer is None:
        raise ValueError("at least an independent or market layer is required")
    include_ordinary = ordinary_status == "observed"
    if adjusted is not None:
        ranking = _ranking(source_layer, include_ordinary=include_ordinary)
    else:
        ranking = _ranking(
            source_layer,
            probability_source="market_implied",
            evidence_grade="C",
            strongest_contradiction="independent sporting baseline unavailable",
            include_ordinary=include_ordinary,
        )
    counterfactual = _capital_counterfactual(ranking, capital)
    ranking = counterfactual["with_capital"]
    without_direction = _candidate_direction(counterfactual["without_capital"][0]) if counterfactual["without_capital"] else None
    combined_direction = _candidate_direction(ranking[0]) if ranking else None
    capital["without_capital_direction"] = without_direction
    capital["combined_direction"] = combined_direction
    capital["incremental_effect"] = ("changed" if counterfactual["applied"] else
                                     "strengthened" if capital.get("capital_direction") == combined_direction and CI_VALUE.get(capital.get("ci_grade"), 0) >= 2 else
                                     "unavailable" if baseline is None else "none")
    base_layer = None
    if baseline:
        base_probabilities = baseline["probabilities"]
        base_layer = {
            "one_x_two": base_probabilities["one_x_two"],
            "goal_bands": base_probabilities["goal_bands"],
            "three_way_handicaps": base_probabilities["three_way_handicaps"],
            "method": baseline["method"],
            "freeze_time": baseline["freeze_time"],
            "audited_market_used": False,
        }
    adjusted_layer = None
    if adjusted:
        adjusted_layer = {key: adjusted[key] for key in ("one_x_two", "goal_bands", "three_way_handicaps", "method", "freeze_time", "audited_market_used", "adjustment_audit")}
    positioning = fixture.get("positioning", {"narrative_signals": [], "measured_positions": []})
    if not isinstance(positioning, dict) or not isinstance(positioning.get("narrative_signals", []), list) or not isinstance(positioning.get("measured_positions", []), list):
        raise ValueError("positioning must separate narrative_signals and measured_positions")
    measured = positioning.get("measured_positions", [])
    positioning["evidence_level"] = "measured" if measured else "narrative_only_or_unavailable"
    source_offers = [
        {"side": offer["side"], "line": offer["line"]}
        for offer in source_layer.get("three_way_handicaps", [])
    ]
    if declared_status == "not_displayed" and source_offers:
        raise ValueError("not_displayed handicap status conflicts with supplied handicap offers")
    if declared_status == "observed":
        coverage_offers = [
            {"side": offer["side"], "line": offer["line"]}
            for offer in declared_offers
        ]
    else:
        coverage_offers = source_offers
    if not include_ordinary and not coverage_offers:
        raise ValueError("no complete ordinary 1X2 or three-way handicap candidate pool is available")
    handicap_coverage = {
        "status": "observed" if coverage_offers else "not_displayed",
        "observed_markets": coverage_offers,
        "candidate_pool_complete": True,
        "source_timestamp": (
            declared_coverage.get("source_timestamp")
            if isinstance(declared_coverage, dict) and declared_coverage.get("source_timestamp")
            else source_layer.get("freeze_time") if coverage_offers else None
        ),
        "reason": (
            declared_coverage.get("reason", "")
            if isinstance(declared_coverage, dict)
            else "verified offers are fully represented" if coverage_offers else "no three-way handicap offer supplied"
        ),
    }
    ordinary_coverage_record = {
        "status": ordinary_status,
        "candidate_pool_complete": ordinary_status != "unreadable_or_unverified",
        "source_timestamp": (
            ordinary_coverage.get("source_timestamp")
            if isinstance(ordinary_coverage, dict) and ordinary_coverage.get("source_timestamp")
            else source_layer.get("freeze_time") if include_ordinary else None
        ),
        "reason": (
            ordinary_coverage.get("reason", "")
            if isinstance(ordinary_coverage, dict)
            else "verified ordinary 1X2 is fully represented" if include_ordinary else "ordinary 1X2 was verified as not displayed"
        ),
    }
    scenarios = {
        "mainstream": ranking[0] if ranking else None,
        "contrarian": next((item for item in ranking[1:] if item["market_type"] == "1X2"), ranking[1] if len(ranking) > 1 else None),
        "tail_risk": ({"market_type": "goal_band", "selection": "7+", "probability": source_layer.get("goal_bands", {}).get("7+")}
                      if isinstance(source_layer.get("goal_bands"), dict) else None),
    }
    record = {
        "schema_version": "1.6.3",
        "engine_version": VERSION,
        "event": event,
        "report_status": status,
        "status_reasons": reasons,
        "data_quality": {"grade": "A" if status == "FULL-MCM" else "B" if status == "MCM-DEGRADED" else "C", "independent_baseline_available": baseline is not None, "cross_book_available": cross_book, "late_snapshot_available": late, "required_checkpoints": required, "captured_checkpoints": captured, "blockers": [], "sources": fixture.get("sources", [])},
        "monitoring_evidence": monitoring_evidence,
        "monitoring_audit": monitoring_audit,
        "probabilities": {"market_implied": market, "independent_baseline": base_layer, "mcm_adjusted": adjusted_layer},
        "baseline_provenance": baseline_audit or ({"input_mode": "preaggregated", "method": baseline["method"], "market_independence": "validated_input_contract", "source_records": baseline["source_records"], "sample_sizes": None, "unavailable_reason": "preaggregated input did not disclose builder sample audit"} if baseline else None),
        "ordinary_1x2_coverage": ordinary_coverage_record,
        "three_way_handicap_coverage": handicap_coverage,
        "candidate_pool_scope": "unified" if include_ordinary else "handicap_only",
        "unified_ranking": ranking,
        "market_quality": MARKET_QUALITY.audit_fixture(fixture, ranking),
        "ranking_counterfactual": counterfactual,
        "candidate_relationship": "alternative_paths_not_combination",
        "scenarios": scenarios,
        "asian_handicap": fixture.get("asian_handicap", {"present": False, "kept_separate": True, "orientation_verified": None, "odds_format": None, "ah_grade": "N/A"}),
        "capital_intent": capital,
        "positioning": positioning,
        "historical_shadow": history,
        "next_phase_shadow": next_phase_shadow,
        "top_scores": adjusted.get("top_scores", [])[:3] if adjusted else [],
        "half_full": sorted((adjusted.get("half_full") or {}).items(), key=lambda item: item[1], reverse=True)[:2] if adjusted else [],
        "value_grade": "A" if status == "FULL-MCM" else "B" if status == "MCM-DEGRADED" else "C",
        "value_grade_meaning": "legacy_evidence_completeness_cap_not_expected_return",
        "strongest_falsifier": capital["falsifier"],
        "reorder_condition": capital["reorder_condition"],
    }
    errors, warnings = VALIDATOR.validate_record(record)
    if errors:
        raise ValueError("validator rejected fixture record: " + "; ".join(errors))
    record["validation_warnings"] = warnings
    return record


def _percent(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.1%}"


def _candidate_text(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return "unavailable"
    boundary = "；".join(candidate.get("covered_paths", []))
    suffix = f"（{boundary}）" if boundary else ""
    return f"{candidate['selection']} {_percent(candidate.get('probability'))}{suffix}"


def _report(records: list[dict[str, Any]], history: dict[str, Any]) -> str:
    counts = {status: sum(row["report_status"] == status for row in records) for status in ("FULL-MCM", "MCM-DEGRADED", "MARKET-STRUCTURE-ONLY", "BLOCKED")}
    lines = [
        "# MCM v1.6.3+evidence1 完整能力报告",
        "",
        "> 能力完整版不等于强制满级结论。每场仍按证据自动分为 FULL-MCM、MCM-DEGRADED、MARKET-STRUCTURE-ONLY 或 BLOCKED。",
        "",
        "## 接受状态",
        "",
        f"- FULL-MCM：{counts['FULL-MCM']}；MCM-DEGRADED：{counts['MCM-DEGRADED']}；MARKET-STRUCTURE-ONLY：{counts['MARKET-STRUCTURE-ONLY']}；BLOCKED：{counts['BLOCKED']}。",
        f"- 历史规则：{history.get('mode')}；稳定权重已改变：{history.get('stable_weights_changed')}。观察规则不得改变概率。",
        "",
        "## 批次总表",
        "",
        "> 硬门禁：体彩已展示的每条整数让球，其让胜、让平、让负必须与普通胜、平、负六项（或多让球时更多项）进入同一完整候选池后，才能截取前两项。",
        "",
        "| 赛事 | 状态 | 第一候选 | 第二候选 | 0–1 | 2–3 | 4–6 | 7+ | 比分前三 | 半全场前二 | CI/资本标签 |",
        "|---|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for row in records:
        ranking = row["unified_ranking"]
        layer = row["probabilities"]["mcm_adjusted"] or row["probabilities"]["market_implied"]
        bands = layer.get("goal_bands") if layer else None
        band_values = [_percent(bands.get(key) if isinstance(bands, dict) else None) for key in GOAL_BANDS]
        first = _candidate_text(ranking[0] if ranking else None)
        second = _candidate_text(ranking[1] if len(ranking) > 1 else None)
        scores = "；".join(f"{item['score']} {_percent(item['probability'])}" for item in row["top_scores"]) or "unavailable"
        half = "；".join(f"{path} {_percent(probability)}" for path, probability in row["half_full"]) or "unavailable"
        cap = row["capital_intent"]
        lines.append(f"| {row['event']['home']} vs {row['event']['away']} | {row['report_status']} | {first} | {second} | {' | '.join(band_values)} | {scores} | {half} | {cap['ci_grade']} / {cap['candidate_label']} |")
    for row in records:
        cap = row["capital_intent"]
        positioning = row["positioning"]
        quality = row["market_quality"]
        ordinary_margins = [offer["overround"] * 100 for offer in quality["ordinary_1x2_offers"]]
        margin_text = (f"普通胜平负 {min(ordinary_margins):.1f}%–{max(ordinary_margins):.1f}%"
                       if ordinary_margins else "普通胜平负 unavailable")
        handicap_margins = [offer["overround"] * 100 for offer in quality["three_way_handicap_offers"]]
        if handicap_margins:
            margin_text += f"；整数三项让球 {min(handicap_margins):.1f}%–{max(handicap_margins):.1f}%"
        if quality["exact_total_offer"]:
            margin_text += f"；精确总进球 {quality['exact_total_offer']['overround'] * 100:.1f}%"
        monitor = row["monitoring_audit"]
        lines += [
            "",
            f"## {row['event']['home']} vs {row['event']['away']}",
            "",
            f"- 状态：**{row['report_status']}**" + (f"；原因：{'；'.join(row['status_reasons'])}" if row["status_reasons"] else "。"),
            f"- 三层概率：市场={'available' if row['probabilities']['market_implied'] else 'unavailable'}；独立基线={'available' if row['probabilities']['independent_baseline'] else 'unavailable'}；MCM调整={'available' if row['probabilities']['mcm_adjusted'] else 'unavailable'}。" + (f" 调整状态={row['probabilities']['mcm_adjusted']['adjustment_audit']['status']}。" if row['probabilities']['mcm_adjusted'] else ""),
            f"- 前二结算覆盖：{'无论赛果均至少命中一项，不能作为预测命中率' if row['market_quality']['top_two_settlement'].get('guaranteed_at_least_one') else '非必然覆盖；仍不是独立两次预测'}。旧版value_grade仅表示证据完整度，不表示正向投注价值。",
            f"- 报价成本（各市场分开计算）：{margin_text}。赔率价值未证实；不把去水后的市场概率当作独立预测。",
            f"- 监测凭证：{monitor['status']}；有效检查点 {monitor['captured_checkpoints']}/{monitor['required_checkpoints']}；末次不同bookmaker ID {monitor['last_valid_bookmaker_count']}。不同ID本身不证明来源经济独立。",
            f"- 资本卡：吸引={cap['attraction']}；保护={cap['protection']}；可行性={cap['feasibility']}；闭环={cap['loop_status']}；{cap['ci_grade']}；标签={cap['candidate_label']}；含/不含资本={cap['combined_direction']}/{cap['without_capital_direction']}；增量={cap['incremental_effect']}。",
            f"- 排序反事实：不含资本第一={_candidate_text(row['ranking_counterfactual']['without_capital'][0] if row['ranking_counterfactual']['without_capital'] else None)}；含资本第一={_candidate_text(row['ranking_counterfactual']['with_capital'][0] if row['ranking_counterfactual']['with_capital'] else None)}；近同概率决胜={'已应用' if row['ranking_counterfactual']['applied'] else '未应用'}；概率未改写={not row['ranking_counterfactual']['probabilities_changed']}。",
            f"- 诱导假设状态：{cap.get('hypothesis_status', 'explicit_card_unscored')}。这是一项可证伪假设，不是对操纵行为的事实认定。",
            f"- 非意图替代解释：{cap['non_intent_alternative']}。",
            f"- 反大众证据：{positioning['evidence_level']}。没有直接投注占比或成交量时，只能称为叙事吸引，不能称为大众资金拥挤。",
            f"- 情景排序：主流={_candidate_text(row['scenarios']['mainstream'])}；逆向={_candidate_text(row['scenarios']['contrarian'])}；尾部={_candidate_text(row['scenarios']['tail_risk'])}。",
            f"- 最强反证：{cap['strongest_contradiction']}。重排条件：{cap['reorder_condition']}。",
            f"- 历史影子层：{history.get('mode')}；只显示触发与反例，不改变本场概率。",
            f"- v1.8研究影子层：{row['next_phase_shadow']['status']}；稳定权重已改变={row['next_phase_shadow']['stable_weights_changed']}；正式概率增量={row['next_phase_shadow']['probability_delta_applied']}。",
        ]
    lines += [
        "",
        "## 验证与边界",
        "",
        f"- 验证器：MCM fixture validator v1.6.3+evidence1；通过 {len(records)}/{len(records)} 份机器记录。",
        f"- 独立基线覆盖：{sum(row['probabilities']['independent_baseline'] is not None for row in records)}/{len(records)}。",
        f"- 资本层改变第一方向：{sum(row['capital_intent']['incremental_effect'] == 'changed' for row in records)} 场。",
        "- 历史研究仅以 observe-only 影子层接入，未通过新冻结留出验证前不改变稳定权重。",
        "- 本报告用于结构化研究，不保证赛果或收益。",
    ]
    return "\n".join(lines) + "\n"


def build(batch: dict[str, Any], output: Path) -> list[dict[str, Any]]:
    if batch.get("schema_version") != SCHEMA:
        raise ValueError(f"schema_version must be {SCHEMA}")
    history = _history_shadow(batch)
    fixtures = batch.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("fixtures must be a non-empty list")
    records = [_record(fixture, batch, history) for fixture in fixtures]
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    machine = output / "machine-records"
    machine.mkdir()
    for record in records:
        (machine / f"{record['event']['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "report.zh-CN.md").write_text(_report(records, history), encoding="utf-8")
    (output / "validation.json").write_text(json.dumps({"engine_version": VERSION, "success": True, "validated_fixtures": len(records)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    FREEZE.create(batch, output, records, VERSION)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        batch = json.loads(args.input.read_text(encoding="utf-8"))
        records = build(batch, args.output)
        print(f"PASS: MCM {VERSION}; {len(records)} fixture records")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

