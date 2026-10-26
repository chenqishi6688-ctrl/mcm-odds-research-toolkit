#!/usr/bin/env python3
"""Build a frozen market-free sporting baseline input from completed matches.

The builder accepts provider-neutral completed-match records.  It prefers xG
when every usable record supplies it, otherwise it falls back to goals and
marks the lower-reliability method explicitly.  Team venue rates are shrunk
toward the league environment before they enter the score-matrix model.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


SCHEMA = "mcm-sporting-history/v1"
BASELINE_VERSION = "1.5.0-candidate"
MARKET_TERMS = ("odds", "market", "bookmaker", "sportsbook", "betting", "price", "盘口", "赔率", "水位")


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    if any(term in value.casefold() for term in MARKET_TERMS):
        raise ValueError(f"{label} must not contain market evidence")
    return value.strip()


def _rate(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 15:
        raise ValueError(f"{label} must be between 0 and 15")
    return value


def _mean(values: list[float], label: str) -> float:
    if not values:
        raise ValueError(f"{label} has no usable observations")
    return statistics.fmean(values)


def _shrunk(sample: float, league: float, n: int, prior_matches: float) -> tuple[float, float]:
    weight = n / (n + prior_matches)
    return weight * sample + (1.0 - weight) * league, weight


def build_baseline_input(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if data.get("schema_version") != SCHEMA:
        raise ValueError(f"schema_version must be {SCHEMA}")
    if data.get("uses_audited_market") is not False:
        raise ValueError("uses_audited_market must be false")
    event = data.get("event")
    if not isinstance(event, dict):
        raise ValueError("event is required")
    for key in ("id", "home", "away", "kickoff"):
        _text(event.get(key), f"event.{key}")
    if event.get("horizon") != "90m":
        raise ValueError("event.horizon must be 90m")
    freeze = _time(data.get("freeze_time"), "freeze_time")
    kickoff = _time(event["kickoff"], "event.kickoff")
    if freeze >= kickoff:
        raise ValueError("freeze_time must be before kickoff")
    provider = _text(data.get("provider"), "provider")
    retrieved = _time(data.get("retrieved_at"), "retrieved_at")
    if retrieved > freeze:
        raise ValueError("retrieved_at must not be after freeze_time")
    prior_matches = float(data.get("shrinkage_prior_matches", 6.0))
    if not math.isfinite(prior_matches) or not 2 <= prior_matches <= 20:
        raise ValueError("shrinkage_prior_matches must be between 2 and 20")
    minimum_team = int(data.get("minimum_team_matches", 5))
    minimum_league = int(data.get("minimum_league_matches", 24))
    if minimum_team < 3 or minimum_league < 12:
        raise ValueError("minimum samples are too small")
    rows = data.get("completed_matches")
    if not isinstance(rows, list):
        raise ValueError("completed_matches must be a list")
    parsed: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"completed_matches[{index}] must be an object")
        match_id = _text(row.get("id"), f"completed_matches[{index}].id")
        if match_id in ids:
            raise ValueError("completed match ids must be unique")
        ids.add(match_id)
        played = _time(row.get("kickoff"), f"completed_matches[{index}].kickoff")
        if played >= freeze:
            raise ValueError(f"completed_matches[{index}] is not frozen before analysis")
        if row.get("status") != "FINISHED":
            continue
        item = {
            "id": match_id,
            "kickoff": played,
            "home": _text(row.get("home"), f"completed_matches[{index}].home"),
            "away": _text(row.get("away"), f"completed_matches[{index}].away"),
            "home_goals": _rate(row.get("home_goals"), f"completed_matches[{index}].home_goals"),
            "away_goals": _rate(row.get("away_goals"), f"completed_matches[{index}].away_goals"),
        }
        if "home_xg" in row or "away_xg" in row:
            item["home_xg"] = _rate(row.get("home_xg"), f"completed_matches[{index}].home_xg")
            item["away_xg"] = _rate(row.get("away_xg"), f"completed_matches[{index}].away_xg")
        parsed.append(item)
    if len(parsed) < minimum_league:
        raise ValueError(f"league sample requires at least {minimum_league} finished matches")
    metric = "xg" if all("home_xg" in row and "away_xg" in row for row in parsed) else "goals"
    hkey, akey = ("home_xg", "away_xg") if metric == "xg" else ("home_goals", "away_goals")
    home_rows = [row for row in parsed if row["home"].casefold() == event["home"].casefold()]
    away_rows = [row for row in parsed if row["away"].casefold() == event["away"].casefold()]
    if len(home_rows) < minimum_team or len(away_rows) < minimum_team:
        raise ValueError(
            f"venue samples require {minimum_team} matches; got home={len(home_rows)}, away={len(away_rows)}"
        )
    league_home = _mean([row[hkey] for row in parsed], "league home rate")
    league_away = _mean([row[akey] for row in parsed], "league away rate")
    raw_home_for = _mean([row[hkey] for row in home_rows], "home venue attack")
    raw_home_against = _mean([row[akey] for row in home_rows], "home venue defence")
    raw_away_for = _mean([row[akey] for row in away_rows], "away venue attack")
    raw_away_against = _mean([row[hkey] for row in away_rows], "away venue defence")
    home_for, home_weight = _shrunk(raw_home_for, league_home, len(home_rows), prior_matches)
    home_against, _ = _shrunk(raw_home_against, league_away, len(home_rows), prior_matches)
    away_for, away_weight = _shrunk(raw_away_for, league_away, len(away_rows), prior_matches)
    away_against, _ = _shrunk(raw_away_against, league_home, len(away_rows), prior_matches)
    first_half_share = data.get("first_half_share")
    league = {"home_xg": league_home, "away_xg": league_away}
    if first_half_share is not None:
        share = float(first_half_share)
        if not 0.25 <= share <= 0.60:
            raise ValueError("first_half_share must be between 0.25 and 0.60")
        league["first_half_share"] = share
    source_time = retrieved.isoformat()
    baseline_input = {
        "candidate_version": BASELINE_VERSION,
        "event_id": event["id"],
        "horizon": "90m",
        "freeze_time": data["freeze_time"],
        "kickoff": event["kickoff"],
        "uses_audited_market": False,
        "source_records": [
            {"source": provider, "observed_at": source_time, "ingested_at": source_time, "metric_group": "completed-team-venue-performance"},
            {"source": provider, "observed_at": source_time, "ingested_at": source_time, "metric_group": "competition-home-away-environment"},
        ],
        "league": league,
        "home": {"xgf_home": home_for, "xga_home": home_against},
        "away": {"xgf_away": away_for, "xga_away": away_against},
        "three_way_handicaps": data.get("three_way_handicaps", []),
    }
    audit = {
        "method": f"venue-specific {metric} rates with empirical-Bayes shrinkage",
        "metric": metric,
        "reliability": "medium" if metric == "xg" else "low_to_medium",
        "market_independence": "verified_by_contract",
        "sample_sizes": {"league": len(parsed), "home_at_home": len(home_rows), "away_away": len(away_rows)},
        "shrinkage_prior_matches": prior_matches,
        "credibility_weights": {"home": home_weight, "away": away_weight},
        "raw_rates": {"home_for": raw_home_for, "home_against": raw_home_against, "away_for": raw_away_for, "away_against": raw_away_against},
        "shrunk_rates": {"home_for": home_for, "home_against": home_against, "away_for": away_for, "away_against": away_against},
        "limitations": ["goal-only input is noisier than xG"] if metric == "goals" else [],
    }
    return baseline_input, audit


def self_test() -> None:
    matches = []
    for i in range(30):
        matches.append({"id": f"l{i}", "kickoff": f"2026-08-{(i % 20) + 1:02d}T12:00:00+08:00", "status": "FINISHED", "home": "Home" if i < 6 else f"H{i}", "away": "Away" if 6 <= i < 12 else f"A{i}", "home_goals": 1 if i < 6 else 2, "away_goals": 3 if 6 <= i < 12 else 1})
    sample = {"schema_version": SCHEMA, "uses_audited_market": False, "provider": "licensed sporting results feed", "retrieved_at": "2026-09-01T09:00:00+08:00", "freeze_time": "2026-09-01T10:00:00+08:00", "event": {"id": "x", "home": "Home", "away": "Away", "kickoff": "2026-09-02T20:00:00+08:00", "horizon": "90m"}, "completed_matches": matches}
    baseline, audit = build_baseline_input(sample)
    if not baseline["uses_audited_market"] is False or audit["metric"] != "goals":
        raise AssertionError("market-free goal baseline failed")
    contaminated = dict(sample, provider="bookmaker odds export")
    try:
        build_baseline_input(contaminated)
    except ValueError:
        pass
    else:
        raise AssertionError("market-contaminated source was accepted")
    leaked = json.loads(json.dumps(sample))
    leaked["completed_matches"][0]["kickoff"] = "2026-09-01T10:00:00+08:00"
    try:
        build_baseline_input(leaked)
    except ValueError:
        pass
    else:
        raise AssertionError("post-freeze observation was accepted")
    print("SELF-TEST PASS: sporting baseline acquisition, shrinkage and anti-circularity")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input is None:
        parser.error("input JSON is required unless --self-test is used")
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        baseline, audit = build_baseline_input(data)
        rendered = json.dumps({"independent_baseline_input": baseline, "baseline_audit": audit}, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

