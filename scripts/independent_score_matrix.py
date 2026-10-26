#!/usr/bin/env python3
"""Experimental v1.5.0-candidate independent score-matrix calculator.

This tool deliberately rejects audited-market inputs. It is a transparent,
testable baseline component, not a claim that v1.5.0 has been promoted.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


VERSION = "1.5.0-candidate"
GOAL_BANDS = ("0-1", "2-3", "4-6", "7+")
TOP_LEVEL_FIELDS = {
    "candidate_version", "event_id", "horizon", "freeze_time", "kickoff",
    "uses_audited_market", "source_records", "league", "home", "away",
    "adjustments", "three_way_handicaps",
}
SOURCE_FIELDS = {"source", "observed_at", "ingested_at", "metric_group"}
MAX_JSON_NESTING = 256
LEAGUE_FIELDS = {"home_xg", "away_xg", "first_half_share"}
HOME_FIELDS = {"xgf_home", "xga_home"}
AWAY_FIELDS = {"xgf_away", "xga_away"}
ADJUSTMENT_FIELDS = {"multiplier", "reason", "evidence_group"}
HANDICAP_FIELDS = {"side", "line"}
MARKET_TERMS = (
    "odds", "market", "bookmaker", "sportsbook", "betting", "wager",
    "price", "implied", "closing",
)
RFC3339_TIMESTAMP = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])[Tt]"
    r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?"
    r"(?:[Zz]|[+-](?:0\d|1\d|2[0-3]):[0-5]\d)$"
)


def _number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_TIMESTAMP.fullmatch(value):
        raise ValueError(f"{label} must be an ISO-8601 datetime with timezone")
    if value.endswith("-00:00"):
        raise ValueError(f"{label} must not use an unknown UTC offset")
    try:
        normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 datetime with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _require_text(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    return _nonempty_text(value, key)


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must contain only Unicode scalar values") from exc
    return value


def _allowed_keys(obj: Any, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{label} must be an object")
    unexpected = set(obj) - allowed
    if unexpected:
        raise ValueError(f"{label} contains unsupported fields: {sorted(unexpected)}")
    return obj


def _reject_market_label(value: str, label: str) -> None:
    lowered = value.casefold()
    compact = re.sub(r"[\W_]+", "", lowered)
    if any(term in lowered or term in compact for term in MARKET_TERMS):
        raise ValueError(f"{label} must not identify market or price evidence")


def _ensure_json_nesting_limit(payload: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in payload:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING:
                raise ValueError("JSON nesting exceeds the supported depth")
        elif character in "]}":
            depth -= 1


def parse_input_document(payload: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    try:
        _ensure_json_nesting_limit(payload)
        value = json.loads(payload, object_pairs_hook=unique_object)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the supported depth") from exc
    if not isinstance(value, dict):
        raise ValueError("baseline input must be an object")
    return value


def canonical_input_digest(data: dict[str, Any], max_goals: int) -> str:
    encoded = json.dumps(
        {"input": data, "max_goals_each_team": max_goals},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"mcmbase_{hashlib.sha256(encoded).hexdigest()[:32]}"


def _poisson_probs(lam: float, maximum: int) -> list[float]:
    probs = [math.exp(-lam)]
    for goals in range(1, maximum + 1):
        probs.append(probs[-1] * lam / goals)
    return probs


def validate_input(data: dict[str, Any]) -> None:
    _allowed_keys(data, TOP_LEVEL_FIELDS, "baseline input")
    if data.get("candidate_version") != VERSION:
        raise ValueError(f"candidate_version must equal {VERSION}")
    _require_text(data, "event_id")
    if data.get("horizon") != "90m":
        raise ValueError("horizon must be 90m")
    freeze_time = _timestamp(data.get("freeze_time"), "freeze_time")
    kickoff = _timestamp(data.get("kickoff"), "kickoff")
    if freeze_time >= kickoff:
        raise ValueError("freeze_time must be before kickoff")
    if data.get("uses_audited_market") is not False:
        raise ValueError("uses_audited_market must be false")

    sources = data.get("source_records")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError("at least two frozen source_records are required")
    groups: set[str] = set()
    for index, source in enumerate(sources):
        _allowed_keys(source, SOURCE_FIELDS, f"source_records[{index}]")
        for key in ("source", "observed_at", "ingested_at", "metric_group"):
            _nonempty_text(source.get(key), f"source_records[{index}].{key}")
        observed_at = _timestamp(
            source["observed_at"], f"source_records[{index}].observed_at"
        )
        ingested_at = _timestamp(
            source["ingested_at"], f"source_records[{index}].ingested_at"
        )
        if observed_at > freeze_time:
            raise ValueError(
                f"source_records[{index}].observed_at must not be after freeze_time"
            )
        if ingested_at > freeze_time:
            raise ValueError(
                f"source_records[{index}].ingested_at must not be after freeze_time"
            )
        if observed_at > ingested_at:
            raise ValueError(
                f"source_records[{index}].observed_at must not be after ingested_at"
            )
        _reject_market_label(source["source"], f"source_records[{index}].source")
        _reject_market_label(source["metric_group"], f"source_records[{index}].metric_group")
        groups.add(source["metric_group"])
    if len(groups) < 2:
        raise ValueError("source_records require at least two distinct metric groups")

    league = data.get("league")
    home = data.get("home")
    away = data.get("away")
    _allowed_keys(league, LEAGUE_FIELDS, "league")
    _allowed_keys(home, HOME_FIELDS, "home")
    _allowed_keys(away, AWAY_FIELDS, "away")
    _number(league.get("home_xg"), "league.home_xg", 0.2, 5.0)
    _number(league.get("away_xg"), "league.away_xg", 0.2, 5.0)
    if "first_half_share" in league:
        _number(
            league.get("first_half_share"),
            "league.first_half_share",
            0.25,
            0.60,
        )
    _number(home.get("xgf_home"), "home.xgf_home", 0.0, 6.0)
    _number(home.get("xga_home"), "home.xga_home", 0.0, 6.0)
    _number(away.get("xgf_away"), "away.xgf_away", 0.0, 6.0)
    _number(away.get("xga_away"), "away.xga_away", 0.0, 6.0)

    adjustments = data.get("adjustments", {})
    _allowed_keys(adjustments, {"home", "away"}, "adjustments")
    for side in ("home", "away"):
        entry = adjustments.get(side, {"multiplier": 1.0})
        _allowed_keys(entry, ADJUSTMENT_FIELDS, f"adjustments.{side}")
        multiplier = _number(
            entry.get("multiplier", 1.0), f"adjustments.{side}.multiplier", 0.70, 1.30
        )
        if "reason" in entry:
            reason = _nonempty_text(entry["reason"], f"adjustments.{side}.reason")
            _reject_market_label(reason, f"adjustments.{side}.reason")
        if "evidence_group" in entry:
            evidence_group = _nonempty_text(
                entry["evidence_group"], f"adjustments.{side}.evidence_group"
            )
            _reject_market_label(evidence_group, f"adjustments.{side}.evidence_group")
            if evidence_group not in groups:
                raise ValueError(
                    f"adjustments.{side}.evidence_group must match a frozen metric group"
                )
        if not math.isclose(multiplier, 1.0):
            if "reason" not in entry:
                raise ValueError(f"adjustments.{side}.reason required for non-1 multiplier")
            if "evidence_group" not in entry:
                raise ValueError(
                    f"adjustments.{side}.evidence_group must match a frozen metric group"
                )

    offers = data.get("three_way_handicaps", [])
    if not isinstance(offers, list):
        raise ValueError("three_way_handicaps must be a list")
    seen_handicaps: set[tuple[str, int]] = set()
    for index, offer in enumerate(offers):
        _allowed_keys(offer, HANDICAP_FIELDS, f"three_way_handicaps[{index}]")
        if offer.get("side") not in {"home", "away"}:
            raise ValueError(f"three_way_handicaps[{index}].side must be home or away")
        line = offer.get("line")
        if isinstance(line, bool) or not isinstance(line, int) or line not in {-2, -1, 1, 2}:
            raise ValueError(f"three_way_handicaps[{index}].line must be an integer ±1 or ±2")
        key = (offer["side"], line)
        if key in seen_handicaps:
            raise ValueError("three_way_handicaps must not repeat a side and line pair")
        seen_handicaps.add(key)


def build_baseline(data: dict[str, Any], max_goals: int = 12) -> dict[str, Any]:
    validate_input(data)
    if max_goals < 8 or max_goals > 20:
        raise ValueError("max_goals must be between 8 and 20")

    league = data["league"]
    home = data["home"]
    away = data["away"]
    adjustments = data.get("adjustments", {})
    home_multiplier = float(adjustments.get("home", {}).get("multiplier", 1.0))
    away_multiplier = float(adjustments.get("away", {}).get("multiplier", 1.0))

    home_lambda = (
        float(home["xgf_home"]) * float(away["xga_away"]) / float(league["home_xg"])
    ) * home_multiplier
    away_lambda = (
        float(away["xgf_away"]) * float(home["xga_home"]) / float(league["away_xg"])
    ) * away_multiplier
    if not 0.05 <= home_lambda <= 6.0 or not 0.05 <= away_lambda <= 6.0:
        raise ValueError("derived lambdas fall outside the supported 0.05..6.0 range")

    hp = _poisson_probs(home_lambda, max_goals)
    ap = _poisson_probs(away_lambda, max_goals)
    matrix = [[h * a for a in ap] for h in hp]
    retained_mass = sum(sum(row) for row in matrix)
    matrix = [[value / retained_mass for value in row] for row in matrix]

    one_x_two = {"home": 0.0, "draw": 0.0, "away": 0.0}
    goal_bands = {key: 0.0 for key in GOAL_BANDS}
    scores: list[dict[str, Any]] = []
    for hg, row in enumerate(matrix):
        for ag, probability in enumerate(row):
            if hg > ag:
                one_x_two["home"] += probability
            elif hg == ag:
                one_x_two["draw"] += probability
            else:
                one_x_two["away"] += probability
            total = hg + ag
            band = "0-1" if total <= 1 else "2-3" if total <= 3 else "4-6" if total <= 6 else "7+"
            goal_bands[band] += probability
            scores.append({"score": f"{hg}-{ag}", "probability": probability})

    handicap_outputs = []
    for offer in data.get("three_way_handicaps", []):
        outcomes = {"side_win": 0.0, "handicap_draw": 0.0, "side_loss": 0.0}
        side = offer["side"]
        line = offer["line"]
        for hg, row in enumerate(matrix):
            for ag, probability in enumerate(row):
                adjusted = (hg - ag + line) if side == "home" else (ag - hg + line)
                key = "side_win" if adjusted > 0 else "handicap_draw" if adjusted == 0 else "side_loss"
                outcomes[key] += probability
        handicap_outputs.append({"side": side, "line": line, "probabilities": outcomes})

    scores.sort(key=lambda item: item["probability"], reverse=True)
    half_full: dict[str, float] | None = None
    first_half_share = league.get("first_half_share")
    if first_half_share is not None:
        share = float(first_half_share)
        first_home = _poisson_probs(home_lambda * share, max_goals)
        first_away = _poisson_probs(away_lambda * share, max_goals)
        second_home = _poisson_probs(home_lambda * (1.0 - share), max_goals)
        second_away = _poisson_probs(away_lambda * (1.0 - share), max_goals)
        half_full = {
            f"{half}/{full}": 0.0
            for half in ("home", "draw", "away")
            for full in ("home", "draw", "away")
        }
        for hh, hh_probability in enumerate(first_home):
            for ah, ah_probability in enumerate(first_away):
                half_direction = "home" if hh > ah else "draw" if hh == ah else "away"
                for hs, hs_probability in enumerate(second_home):
                    for ass, as_probability in enumerate(second_away):
                        home_goals = hh + hs
                        away_goals = ah + ass
                        full_direction = (
                            "home"
                            if home_goals > away_goals
                            else "draw"
                            if home_goals == away_goals
                            else "away"
                        )
                        half_full[f"{half_direction}/{full_direction}"] += (
                            hh_probability
                            * ah_probability
                            * hs_probability
                            * as_probability
                        )
        half_full_mass = sum(half_full.values())
        half_full = {
            key: value / half_full_mass for key, value in half_full.items()
        }
    return {
        "candidate_version": VERSION,
        "experimental": True,
        "validated_core_model": False,
        "event_id": data["event_id"],
        "horizon": "90m",
        "kickoff": data["kickoff"],
        "freeze_time": data["freeze_time"],
        "uses_audited_market": False,
        "input_digest": canonical_input_digest(data, max_goals),
        "market_access": "forbidden",
        "source_records": copy.deepcopy(data["source_records"]),
        "method": "league-normalised independent Poisson score matrix",
        "lambdas": {"home": home_lambda, "away": away_lambda},
        "truncation": {"max_goals_each_team": max_goals, "retained_mass": retained_mass},
        "probabilities": {
            "one_x_two": one_x_two,
            "goal_bands": goal_bands,
            "three_way_handicaps": handicap_outputs,
            "top_scores": scores[:10],
            "half_full": half_full,
            "score_matrix": matrix,
        },
        "unavailable_fields": (
            {}
            if half_full is not None
            else {
                "half_full": "league.first_half_share was not supplied from a frozen independent source"
            }
        ),
    }


def _assert_sum(values: dict[str, float]) -> None:
    if not math.isclose(sum(values.values()), 1.0, rel_tol=0, abs_tol=1e-10):
        raise AssertionError(f"probabilities do not sum to one: {values}")


def self_test() -> None:
    sample = {
        "candidate_version": VERSION,
        "event_id": "test-001",
        "horizon": "90m",
        "kickoff": "2026-08-29T02:00:00+08:00",
        "freeze_time": "2026-08-28T12:00:00+08:00",
        "uses_audited_market": False,
        "source_records": [
            {"source": "team feed", "observed_at": "2026-08-28T11:00:00+08:00", "ingested_at": "2026-08-28T11:01:00+08:00", "metric_group": "team-form"},
            {"source": "league table", "observed_at": "2026-08-28T11:05:00+08:00", "ingested_at": "2026-08-28T11:06:00+08:00", "metric_group": "league-environment"},
        ],
        "league": {"home_xg": 1.45, "away_xg": 1.18},
        "home": {"xgf_home": 1.70, "xga_home": 1.05},
        "away": {"xgf_away": 1.10, "xga_away": 1.55},
        "three_way_handicaps": [
            {"side": "home", "line": -1},
            {"side": "home", "line": 1},
            {"side": "away", "line": -2},
        ],
    }
    output = build_baseline(sample)
    _assert_sum(output["probabilities"]["one_x_two"])
    _assert_sum(output["probabilities"]["goal_bands"])
    for offer in output["probabilities"]["three_way_handicaps"]:
        _assert_sum(offer["probabilities"])
    if output["probabilities"]["half_full"] is not None:
        raise AssertionError("half/full distribution must remain unavailable without a sourced share")
    with_half = copy.deepcopy(sample)
    with_half["league"]["first_half_share"] = 0.45
    half_output = build_baseline(with_half)
    half_full = half_output["probabilities"]["half_full"]
    if not isinstance(half_full, dict) or not math.isclose(
        sum(half_full.values()), 1.0, rel_tol=0, abs_tol=1e-10
    ):
        raise AssertionError("half/full distribution must be complete and normalized")
    minus_one = output["probabilities"]["three_way_handicaps"][0]["probabilities"]
    plus_one = output["probabilities"]["three_way_handicaps"][1]["probabilities"]
    if plus_one["side_win"] <= minus_one["side_win"]:
        raise AssertionError("home +1 should be easier to win than home -1")
    rejected = copy.deepcopy(sample)
    rejected["uses_audited_market"] = True
    try:
        build_baseline(rejected)
    except ValueError:
        pass
    else:
        raise AssertionError("audited-market input was not rejected")
    post_freeze = copy.deepcopy(sample)
    post_freeze["source_records"][0]["observed_at"] = "2026-08-28T12:01:00+08:00"
    try:
        build_baseline(post_freeze)
    except ValueError:
        pass
    else:
        raise AssertionError("post-freeze source was not rejected")
    post_kickoff_freeze = copy.deepcopy(sample)
    post_kickoff_freeze["freeze_time"] = "2026-08-29T02:00:00+08:00"
    try:
        build_baseline(post_kickoff_freeze)
    except ValueError:
        pass
    else:
        raise AssertionError("non-pre-match freeze was not rejected")
    print("SELF-TEST PASS: independent score matrix and anti-circularity gates")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-goals", type=int, default=12)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input is None:
        parser.error("input JSON is required unless --self-test is used")
    try:
        data = parse_input_document(args.input.read_text(encoding="utf-8"))
        output = build_baseline(data, max_goals=args.max_goals)
        rendered = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

