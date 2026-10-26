#!/usr/bin/env python3
"""Build and score market-free MCM next-phase models in observe-only mode.

The lab never changes live probabilities or rankings. It produces append-only
shadow artifacts for opponent-strength, recency/season, Dixon-Coles low-score,
and uncertainty candidates, then scores them after a verified result exists.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any


VERSION = "1.8.0-shadow"
SCHEMA = "mcm-next-phase-shadow/v1"
SCORE_SCHEMA = "mcm-shadow-score/v1"
MARKET_KEYS = ("odds", "market", "bookmaker", "sportsbook", "betting", "price", "盘口", "赔率", "水位")
ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load required component: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPORTING = _load(ROOT / "sporting_baseline_builder.py", "mcm_shadow_sporting")
BASELINE = _load(ROOT / "independent_score_matrix.py", "mcm_shadow_baseline")


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


def _finite(value: Any, label: str, low: float = 0.0, high: float = 20.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return result


def _reject_market_fields(value: Any, path: str = "input") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).casefold()
            if key != "uses_audited_market" and any(term in lowered for term in MARKET_KEYS):
                raise ValueError(f"{path}.{key} is forbidden market evidence")
            _reject_market_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_market_fields(item, f"{path}[{index}]")


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "mcmshadow_" + hashlib.sha256(body).hexdigest()[:32]


def _weighted_mean(values: list[tuple[float, float]], label: str) -> tuple[float, float]:
    total_weight = sum(weight for _, weight in values)
    if not values or total_weight <= 0:
        raise ValueError(f"{label} has no usable observations")
    return sum(value * weight for value, weight in values) / total_weight, total_weight


def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    freeze = _time(data.get("freeze_time"), "freeze_time")
    result = []
    for index, raw in enumerate(data.get("completed_matches", [])):
        if not isinstance(raw, dict) or raw.get("status") != "FINISHED":
            continue
        kickoff = _time(raw.get("kickoff"), f"completed_matches[{index}].kickoff")
        if kickoff >= freeze:
            raise ValueError(f"completed_matches[{index}] is not frozen before analysis")
        result.append({
            **raw,
            "kickoff_parsed": kickoff,
            "home_goals": _finite(raw.get("home_goals"), f"completed_matches[{index}].home_goals", 0, 15),
            "away_goals": _finite(raw.get("away_goals"), f"completed_matches[{index}].away_goals", 0, 15),
        })
    if not result:
        raise ValueError("completed_matches has no usable frozen results")
    return result


def _team_indices(rows: list[dict[str, Any]], prior: float = 6.0) -> tuple[dict[str, dict[str, float]], float]:
    totals: dict[str, dict[str, float]] = {}
    for row in rows:
        for team, scored, conceded in ((row["home"], row["home_goals"], row["away_goals"]), (row["away"], row["away_goals"], row["home_goals"])):
            slot = totals.setdefault(team.casefold(), {"gf": 0.0, "ga": 0.0, "n": 0.0})
            slot["gf"] += scored
            slot["ga"] += conceded
            slot["n"] += 1
    league = sum(row["home_goals"] + row["away_goals"] for row in rows) / (2 * len(rows))
    indices = {}
    for team, slot in totals.items():
        weight = slot["n"] / (slot["n"] + prior)
        attack = weight * (slot["gf"] / slot["n"] / league) + (1 - weight)
        defence = weight * (slot["ga"] / slot["n"] / league) + (1 - weight)
        indices[team] = {"attack": attack, "defence": defence, "matches": slot["n"]}
    return indices, league


def _row_weight(row: dict[str, Any], freeze: datetime, season_start: datetime | None, half_life_days: float) -> float:
    age_days = max(0.0, (freeze - row["kickoff_parsed"]).total_seconds() / 86400)
    weight = math.exp(-math.log(2) * age_days / half_life_days)
    if season_start is not None and row["kickoff_parsed"] < season_start:
        weight *= 0.5
    return weight


def _candidate_lambdas(data: dict[str, Any], rows: list[dict[str, Any]], base: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    event = data["event"]
    freeze = _time(data["freeze_time"], "freeze_time")
    season_start = None
    if isinstance(event.get("season_start"), str):
        try:
            season_start = _time(event["season_start"] + "T00:00:00+00:00" if "T" not in event["season_start"] else event["season_start"], "event.season_start")
        except ValueError:
            season_start = None
    half_life = _finite(data.get("recency_half_life_days", 90.0), "recency_half_life_days", 30, 365)
    indices, _ = _team_indices(rows)
    home_rows = [row for row in rows if str(row.get("home", "")).casefold() == event["home"].casefold()]
    away_rows = [row for row in rows if str(row.get("away", "")).casefold() == event["away"].casefold()]
    if len(home_rows) < int(data.get("minimum_team_matches", 5)) or len(away_rows) < int(data.get("minimum_team_matches", 5)):
        raise ValueError("shadow opponent-strength model lacks venue samples")

    home_for_values: list[tuple[float, float]] = []
    home_against_values: list[tuple[float, float]] = []
    away_for_values: list[tuple[float, float]] = []
    away_against_values: list[tuple[float, float]] = []
    opponents = {"home": [], "away": []}
    for row in home_rows:
        opponent = indices.get(str(row["away"]).casefold(), {"attack": 1.0, "defence": 1.0})
        weight = _row_weight(row, freeze, season_start, half_life)
        home_for_values.append((row["home_goals"] / max(0.35, opponent["defence"]), weight))
        home_against_values.append((row["away_goals"] / max(0.35, opponent["attack"]), weight))
        opponents["home"].append({"team": row["away"], "attack_index": opponent["attack"], "defence_index": opponent["defence"], "weight": weight})
    for row in away_rows:
        opponent = indices.get(str(row["home"]).casefold(), {"attack": 1.0, "defence": 1.0})
        weight = _row_weight(row, freeze, season_start, half_life)
        away_for_values.append((row["away_goals"] / max(0.35, opponent["defence"]), weight))
        away_against_values.append((row["home_goals"] / max(0.35, opponent["attack"]), weight))
        opponents["away"].append({"team": row["home"], "attack_index": opponent["attack"], "defence_index": opponent["defence"], "weight": weight})

    home_for, home_eff = _weighted_mean(home_for_values, "home adjusted attack")
    home_against, _ = _weighted_mean(home_against_values, "home adjusted defence")
    away_for, away_eff = _weighted_mean(away_for_values, "away adjusted attack")
    away_against, _ = _weighted_mean(away_against_values, "away adjusted defence")
    league_home = sum(row["home_goals"] for row in rows) / len(rows)
    league_away = sum(row["away_goals"] for row in rows) / len(rows)
    prior = _finite(data.get("shrinkage_prior_matches", 6.0), "shrinkage_prior_matches", 2, 20)
    def shrink(value: float, league: float, effective_n: float) -> float:
        weight = effective_n / (effective_n + prior)
        return weight * value + (1 - weight) * league
    home_for = shrink(home_for, league_home, home_eff)
    home_against = shrink(home_against, league_away, home_eff)
    away_for = shrink(away_for, league_away, away_eff)
    away_against = shrink(away_against, league_home, away_eff)
    lambdas = {
        "home": min(6.0, max(0.05, home_for * away_against / league_home)),
        "away": min(6.0, max(0.05, away_for * home_against / league_away)),
    }
    def rest_days(team: str) -> float | None:
        relevant = [row["kickoff_parsed"] for row in rows
                    if team.casefold() in {str(row.get("home", "")).casefold(), str(row.get("away", "")).casefold()}]
        return ((freeze - max(relevant)).total_seconds() / 86400) if relevant else None
    audit = {
        "recency_half_life_days": half_life,
        "season_transition_factor": 0.5 if season_start is not None else None,
        "effective_samples": {"home_at_home": home_eff, "away_away": away_eff},
        "schedule_strength": {
            "home_opponent_attack_mean": sum(item["attack_index"] for item in opponents["home"]) / len(opponents["home"]),
            "home_opponent_defence_mean": sum(item["defence_index"] for item in opponents["home"]) / len(opponents["home"]),
            "away_opponent_attack_mean": sum(item["attack_index"] for item in opponents["away"]) / len(opponents["away"]),
            "away_opponent_defence_mean": sum(item["defence_index"] for item in opponents["away"]) / len(opponents["away"]),
        },
        "rest_days_at_freeze": {"home": rest_days(event["home"]), "away": rest_days(event["away"])},
        "base_lambdas": base["lambdas"], "candidate_lambdas": lambdas,
    }
    return lambdas, audit


def _poisson(lam: float, maximum: int = 12) -> list[float]:
    values = [math.exp(-lam)]
    for goals in range(1, maximum + 1):
        values.append(values[-1] * lam / goals)
    return values


def _matrix(lambdas: dict[str, float], rho: float | None = None, maximum: int = 12) -> list[list[float]]:
    home = _poisson(lambdas["home"], maximum)
    away = _poisson(lambdas["away"], maximum)
    matrix = [[h * a for a in away] for h in home]
    if rho is not None:
        corrections = {
            (0, 0): 1 - lambdas["home"] * lambdas["away"] * rho,
            (0, 1): 1 + lambdas["home"] * rho,
            (1, 0): 1 + lambdas["away"] * rho,
            (1, 1): 1 - rho,
        }
        for (home_goals, away_goals), factor in corrections.items():
            if factor <= 0:
                raise ValueError("Dixon-Coles correction became non-positive")
            matrix[home_goals][away_goals] *= factor
    mass = sum(sum(row) for row in matrix)
    return [[value / mass for value in row] for row in matrix]


def _derive(matrix: list[list[float]]) -> dict[str, Any]:
    one_x_two = {"home": 0.0, "draw": 0.0, "away": 0.0}
    bands = {"0-1": 0.0, "2-3": 0.0, "4-6": 0.0, "7+": 0.0}
    scores = []
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            direction = "home" if home_goals > away_goals else "draw" if home_goals == away_goals else "away"
            one_x_two[direction] += probability
            total = home_goals + away_goals
            band = "0-1" if total <= 1 else "2-3" if total <= 3 else "4-6" if total <= 6 else "7+"
            bands[band] += probability
            scores.append({"score": f"{home_goals}-{away_goals}", "probability": probability})
    scores.sort(key=lambda item: item["probability"], reverse=True)
    return {"one_x_two": one_x_two, "goal_bands": bands, "top_scores": scores[:10]}


def _uncertainty(lambdas: dict[str, float], effective: dict[str, float]) -> dict[str, Any]:
    home_n = max(1.0, effective["home_at_home"])
    away_n = max(1.0, effective["away_away"])
    se = {"home": math.sqrt(lambdas["home"] / home_n), "away": math.sqrt(lambdas["away"] / away_n)}
    bounds = {side: {"low": max(0.05, lambdas[side] - 1.96 * se[side]), "high": min(6.0, lambdas[side] + 1.96 * se[side])} for side in ("home", "away")}
    variants = [_derive(_matrix({"home": h, "away": a})) for h in (bounds["home"]["low"], bounds["home"]["high"]) for a in (bounds["away"]["low"], bounds["away"]["high"])]
    return {
        "method": "deterministic Poisson-rate corner envelope; shadow reliability diagnostic, not a calibrated confidence interval",
        "lambda_bounds": bounds,
        "one_x_two": {key: {"low": min(row["one_x_two"][key] for row in variants), "high": max(row["one_x_two"][key] for row in variants)} for key in ("home", "draw", "away")},
        "goal_bands": {key: {"low": min(row["goal_bands"][key] for row in variants), "high": max(row["goal_bands"][key] for row in variants)} for key in ("0-1", "2-3", "4-6", "7+")},
    }


def _coverage(data: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ("home_provider_id", "away_provider_id", "competition_provider_id", "season_provider_id", "season_start", "stage", "half_time_home_goals", "half_time_away_goals")
    return {
        "event_provider_ids_complete": all(data.get("event", {}).get(key) for key in ("home_provider_id", "away_provider_id", "competition_provider_id")),
        "row_field_coverage": {field: sum(row.get(field) is not None for row in rows) / len(rows) for field in fields},
        "unavailable_optional_fields": [field for field in ("venue", "red_cards", "promoted_relegated_status", "lineups", "injuries", "weather", "travel", "measured_positioning") if not any(row.get(field) is not None for row in rows)],
        "identity_mapping_status": "provider_ids_available" if all(data.get("event", {}).get(key) for key in ("home_provider_id", "away_provider_id", "competition_provider_id")) else "manual_mapping_required",
    }


def _capital_threshold_shadow(data: dict[str, Any]) -> dict[str, Any]:
    """Return research-only threshold candidates; never apply them to live output."""
    event = data["event"]
    freeze = _time(data["freeze_time"], "freeze_time")
    kickoff = _time(event["kickoff"], "event.kickoff")
    hours = (kickoff - freeze).total_seconds() / 3600
    if hours <= 0:
        raise ValueError("freeze_time must precede event.kickoff")
    tier = str(event.get("liquidity_tier", "unknown")).casefold()
    if tier not in {"high", "medium", "low", "unknown"}:
        raise ValueError("event.liquidity_tier must be high, medium, low or unknown")
    liquidity_multiplier = {"high": 1.0, "medium": 1.15, "low": 1.35, "unknown": 1.25}[tier]
    timing_multiplier = 1.0 if hours <= 6 else 1.1 if hours <= 24 else 1.25
    return {
        "mode": "observe_only", "applied": False, "calibration_required": True,
        "liquidity_tier": tier, "time_to_kickoff_hours": hours,
        "candidate_multiplier": liquidity_multiplier * timing_multiplier,
        "components": {"liquidity_multiplier": liquidity_multiplier, "timing_multiplier": timing_multiplier},
        "probability_delta_applied": 0,
        "reason": "candidate capital evidence threshold only; requires chronological calibration and cannot rewrite probabilities",
    }


def _manifest(data: dict[str, Any], rows: list[dict[str, Any]], manifest: dict[str, Any] | None) -> dict[str, Any]:
    event = data["event"]
    kickoff = _time(event["kickoff"], "event.kickoff")
    if manifest is None:
        return {
            "registered": False, "experiment_id": f"auto-shadow-{event['id']}",
            "training_window": {"start": min(row["kickoff_parsed"] for row in rows).isoformat(), "end": max(row["kickoff_parsed"] for row in rows).isoformat()},
            "test_event_id": event["id"], "primary_metrics": ["1x2_log_loss", "1x2_brier", "1x2_rps", "goal_band_log_loss"],
            "promotion_eligible": False, "reason": "no preregistered validation and untouched test windows supplied",
        }
    required = {"experiment_id", "hypothesis", "feature_set", "training_window", "validation_window", "test_window", "test_event_id", "primary_metric", "regression_segments", "rollback_rule"}
    missing = sorted(required - set(manifest))
    if missing:
        raise ValueError("experiment manifest missing fields: " + ", ".join(missing))
    if manifest.get("test_event_id") != event["id"]:
        raise ValueError("experiment test_event_id mismatch")
    train_start = _time(manifest.get("training_window", {}).get("start"), "training_window.start")
    train_end = _time(manifest.get("training_window", {}).get("end"), "training_window.end")
    validation_start = _time(manifest.get("validation_window", {}).get("start"), "validation_window.start")
    validation_end = _time(manifest.get("validation_window", {}).get("end"), "validation_window.end")
    test_start = _time(manifest.get("test_window", {}).get("start"), "test_window.start")
    test_end = _time(manifest.get("test_window", {}).get("end"), "test_window.end")
    if not train_start <= train_end < validation_start <= validation_end < test_start <= test_end <= kickoff:
        raise ValueError("experiment windows must be chronological and pre-kickoff")
    return {**manifest, "registered": True, "promotion_eligible": False, "reason": "requires completed chronological scoring and promotion review"}


def build_shadow(data: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    _reject_market_fields(data)
    baseline_input, baseline_audit = SPORTING.build_baseline_input(data)
    base = BASELINE.build_baseline(baseline_input)
    rows = _rows(data)
    lambdas, model_audit = _candidate_lambdas(data, rows, base)
    strength = _derive(_matrix(lambdas))
    rho = _finite(data.get("dixon_coles_rho", -0.08), "dixon_coles_rho", -0.15, 0.0)
    dixon_coles = _derive(_matrix(lambdas, rho=rho))
    core = {"one_x_two": base["probabilities"]["one_x_two"], "goal_bands": base["probabilities"]["goal_bands"], "top_scores": base["probabilities"]["top_scores"]}
    return {
        "schema_version": SCHEMA, "engine_version": VERSION, "mode": "observe_only",
        "status": "available", "event": data["event"], "freeze_time": data["freeze_time"],
        "input_digest": _digest(data), "uses_audited_market": False,
        "stable_weights_changed": False, "probability_delta_applied": 0,
        "live_probability_source": "mcm-v1.6.1-core-unchanged", "live_ranking_changed": False,
        "experiment_manifest": _manifest(data, rows, manifest),
        "data_contract_coverage": _coverage(data, rows),
        "baseline_audit": baseline_audit,
        "candidate_models": {
            "core_independent_poisson_control": {"method": base["method"], "lambdas": base["lambdas"], "probabilities": core},
            "opponent_strength_recency_poisson": {"method": "opponent-strength normalized venue rates with exponential recency and season-transition control", "lambdas": lambdas, "audit": model_audit, "probabilities": strength},
            "opponent_strength_recency_dixon_coles": {"method": "same shadow rates with fixed unpromoted Dixon-Coles low-score correction", "rho": rho, "lambdas": lambdas, "probabilities": dixon_coles},
        },
        "uncertainty": _uncertainty(lambdas, model_audit["effective_samples"]),
        "capital_threshold_shadow": _capital_threshold_shadow(data),
        "limitations": ["candidate thresholds and rho are uncalibrated", "uncertainty envelope is diagnostic, not a calibrated interval", "missing optional fields remain unavailable rather than imputed"],
    }


def _band(total: int) -> str:
    return "0-1" if total <= 1 else "2-3" if total <= 3 else "4-6" if total <= 6 else "7+"


def _score_probabilities(probabilities: dict[str, Any], home_goals: int, away_goals: int) -> dict[str, Any]:
    actual = "home" if home_goals > away_goals else "draw" if home_goals == away_goals else "away"
    ordered = ("away", "draw", "home")
    one = probabilities["one_x_two"]
    brier = sum((one[key] - (1.0 if key == actual else 0.0)) ** 2 for key in ordered)
    cumulative_prediction = [one[ordered[0]], one[ordered[0]] + one[ordered[1]]]
    actual_index = ordered.index(actual)
    cumulative_actual = [1.0 if actual_index <= boundary else 0.0 for boundary in (0, 1)]
    rps = sum((p - y) ** 2 for p, y in zip(cumulative_prediction, cumulative_actual)) / 2
    actual_band = _band(home_goals + away_goals)
    bands = probabilities["goal_bands"]
    return {
        "actual_1x2": actual, "actual_goal_band": actual_band,
        "1x2_log_loss": -math.log(max(one[actual], 1e-15)), "1x2_brier": brier, "1x2_rps": rps,
        "goal_band_log_loss": -math.log(max(bands[actual_band], 1e-15)),
        "1x2_top_correct": max(one, key=one.get) == actual,
        "goal_band_top_correct": max(bands, key=bands.get) == actual_band,
    }


def _candidate_wins(candidate: dict[str, Any] | None, home_goals: int, away_goals: int) -> bool | None:
    if not isinstance(candidate, dict):
        return None
    if candidate.get("market_type") == "1X2":
        actual = "home" if home_goals > away_goals else "draw" if home_goals == away_goals else "away"
        return candidate.get("selection") == actual
    handicap = candidate.get("handicap")
    if not isinstance(handicap, dict) or handicap.get("side") not in {"home", "away"} or not isinstance(handicap.get("line"), int):
        return None
    margin = home_goals - away_goals if handicap["side"] == "home" else away_goals - home_goals
    outcome = "side_win" if margin + handicap["line"] > 0 else "handicap_draw" if margin + handicap["line"] == 0 else "side_loss"
    return handicap.get("outcome") == outcome


def settle(prediction: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    shadow = prediction.get("next_phase_shadow") if isinstance(prediction.get("next_phase_shadow"), dict) else prediction
    if shadow.get("schema_version") != SCHEMA or shadow.get("mode") != "observe_only":
        raise ValueError("prediction is not an observe-only next-phase shadow artifact")
    event = shadow.get("event", {})
    if result.get("event_id") != event.get("id") or result.get("status") != "FINISHED" or result.get("horizon") != "90m":
        raise ValueError("result identity/status/horizon mismatch")
    observed = _time(result.get("observed_at"), "result.observed_at")
    kickoff = _time(event.get("kickoff"), "event.kickoff")
    if observed <= kickoff:
        raise ValueError("result must be observed after kickoff")
    home_goals = int(_finite(result.get("home_goals"), "result.home_goals", 0, 15))
    away_goals = int(_finite(result.get("away_goals"), "result.away_goals", 0, 15))
    if home_goals != result.get("home_goals") or away_goals != result.get("away_goals"):
        raise ValueError("result goals must be integers")
    scores = {name: _score_probabilities(model["probabilities"], home_goals, away_goals) for name, model in shadow["candidate_models"].items()}
    control = shadow["candidate_models"]["core_independent_poisson_control"]
    control_probs = control["probabilities"]["one_x_two"]
    total_lambda = control["lambdas"]["home"] + control["lambdas"]["away"]
    effective = shadow["candidate_models"]["opponent_strength_recency_poisson"].get("audit", {}).get("effective_samples", {})
    segments = {
        "competition": event.get("competition_code") or event.get("competition") or "unknown",
        "season": event.get("season_provider_id") or event.get("season") or "unknown",
        "liquidity_tier": event.get("liquidity_tier", "unknown"),
        "favorite_strength": "strong" if max(control_probs.values()) >= .60 else "medium" if max(control_probs.values()) >= .45 else "balanced",
        "goal_environment": "low" if total_lambda < 2.2 else "high" if total_lambda > 3.2 else "medium",
        "sparse_history": bool(min(effective.get("home_at_home", 0), effective.get("away_away", 0)) < 5),
        "promoted_team": bool(event.get("home_promoted") or event.get("away_promoted")),
    }
    capital = {"available": False, "effect": "unavailable", "causal_explanation_verified": False}
    counterfactual = prediction.get("ranking_counterfactual")
    if isinstance(counterfactual, dict):
        without = counterfactual.get("without_capital", [])
        with_capital = counterfactual.get("with_capital", [])
        without_win = _candidate_wins(without[0] if without else None, home_goals, away_goals)
        with_win = _candidate_wins(with_capital[0] if with_capital else None, home_goals, away_goals)
        effect = "helped" if with_win is True and without_win is False else "hurt" if with_win is False and without_win is True else "unchanged"
        capital = {"available": without_win is not None and with_win is not None, "without_capital_first_won": without_win, "with_capital_first_won": with_win, "effect": effect, "causal_explanation_verified": False}
    return {
        "schema_version": SCORE_SCHEMA, "engine_version": VERSION, "event_id": event["id"],
        "prediction_digest": _digest(shadow), "result": {"home_goals": home_goals, "away_goals": away_goals, "observed_at": result["observed_at"], "horizon": "90m"},
        "model_scores": scores, "capital_counterfactual_score": capital,
        "segments": segments,
        "experiment_registered": shadow.get("experiment_manifest", {}).get("registered") is True,
        "cohort_eligible": shadow.get("experiment_manifest", {}).get("registered") is True,
        "promotion_decision": "not_eligible_single_event", "stable_weights_changed": False,
    }


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    except FileExistsError:
        raise ValueError(f"output already exists and will not be overwritten: {path}") from None


def self_test() -> None:
    matches = []
    for i in range(36):
        matches.append({"id": f"m{i}", "kickoff": f"2026-0{(i // 20) + 1}-{(i % 20) + 1:02d}T12:00:00+00:00", "status": "FINISHED", "home": "Home" if i < 7 else f"H{i % 8}", "away": "Away" if 7 <= i < 14 else f"A{i % 8}", "home_goals": 2 if i < 7 else 1, "away_goals": 2 if 7 <= i < 14 else 1, "home_provider_id": str(i * 2), "away_provider_id": str(i * 2 + 1), "competition_provider_id": "1", "season_provider_id": "2", "season_start": "2025-08-01", "stage": "REGULAR_SEASON", "half_time_home_goals": 1, "half_time_away_goals": 0})
    sample = {"schema_version": "mcm-sporting-history/v1", "uses_audited_market": False, "provider": "licensed sporting results feed", "retrieved_at": "2026-03-01T09:00:00+00:00", "freeze_time": "2026-03-01T09:00:00+00:00", "event": {"id": "shadow-1", "home": "Home", "away": "Away", "kickoff": "2026-03-02T20:00:00+00:00", "horizon": "90m", "home_provider_id": "10", "away_provider_id": "20", "competition_provider_id": "1", "season_start": "2025-08-01"}, "completed_matches": matches, "first_half_share": 0.45}
    output = build_shadow(sample)
    if output["mode"] != "observe_only" or output["probability_delta_applied"] != 0 or output["live_ranking_changed"]:
        raise AssertionError("shadow safety boundary failed")
    if set(output["candidate_models"]) != {"core_independent_poisson_control", "opponent_strength_recency_poisson", "opponent_strength_recency_dixon_coles"}:
        raise AssertionError("shadow candidates missing")
    result = settle(output, {"event_id": "shadow-1", "status": "FINISHED", "horizon": "90m", "home_goals": 2, "away_goals": 1, "observed_at": "2026-03-03T00:00:00+00:00"})
    if result["promotion_decision"] != "not_eligible_single_event" or not result["model_scores"]:
        raise AssertionError("shadow scoring failed")
    contaminated = json.loads(json.dumps(sample))
    contaminated["completed_matches"][0]["closing_odds"] = 2.0
    try:
        build_shadow(contaminated)
    except ValueError:
        pass
    else:
        raise AssertionError("market leakage was accepted")
    print("SELF-TEST PASS: next-phase shadow models, uncertainty, scoring and leakage gates")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("input", type=Path)
    freeze.add_argument("--manifest", type=Path)
    freeze.add_argument("--output", type=Path, required=True)
    score = sub.add_parser("score")
    score.add_argument("prediction", type=Path)
    score.add_argument("result", type=Path)
    score.add_argument("--output", type=Path, required=True)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
        elif args.command == "freeze":
            data = json.loads(args.input.read_text(encoding="utf-8"))
            manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else None
            _write_exclusive(args.output, build_shadow(data, manifest))
            print(f"PASS: wrote observe-only {VERSION} shadow artifact")
        else:
            prediction = json.loads(args.prediction.read_text(encoding="utf-8"))
            result = json.loads(args.result.read_text(encoding="utf-8"))
            _write_exclusive(args.output, settle(prediction, result))
            print(f"PASS: wrote {VERSION} shadow score")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

