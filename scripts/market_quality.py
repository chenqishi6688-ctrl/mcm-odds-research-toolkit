#!/usr/bin/env python3
"""Outcome-independent diagnostics for MCM market offers and candidate coverage.

These calculations describe the offered prices and settlement sets.  They do
not infer true probabilities, expected profit, or bookmaker intent.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def overround(prices: list[float] | tuple[float, ...]) -> dict[str, float]:
    if not prices or any(
        isinstance(price, bool)
        or not isinstance(price, (int, float))
        or not math.isfinite(float(price))
        or float(price) <= 1.0
        for price in prices
    ):
        raise ValueError("prices must be finite decimal odds greater than one")
    inverse_sum = sum(1.0 / float(price) for price in prices)
    return {
        "inverse_price_sum": inverse_sum,
        "overround": inverse_sum - 1.0,
        "market_proxy_return": 1.0 / inverse_sum,
    }


def _wins(candidate: dict[str, Any], home_margin: int) -> bool:
    market_type = candidate.get("market_type")
    if market_type == "1X2":
        selection = candidate.get("selection")
        if selection == "home":
            return home_margin > 0
        if selection == "draw":
            return home_margin == 0
        if selection == "away":
            return home_margin < 0
        raise ValueError("invalid ordinary 1X2 selection")
    if market_type == "three_way_handicap":
        handicap = candidate.get("handicap")
        if not isinstance(handicap, dict):
            raise ValueError("three-way handicap candidate lacks settlement definition")
        side, line, outcome = (
            handicap.get("side"), handicap.get("line"), handicap.get("outcome")
        )
        if side not in {"home", "away"} or isinstance(line, bool) or not isinstance(line, int):
            raise ValueError("three-way handicap side/line is invalid")
        adjusted = (home_margin if side == "home" else -home_margin) + line
        if outcome == "side_win":
            return adjusted > 0
        if outcome == "handicap_draw":
            return adjusted == 0
        if outcome == "side_loss":
            return adjusted < 0
        raise ValueError("invalid three-way handicap outcome")
    raise ValueError("candidate market type is not supported")


def top_two_coverage(ranking: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify whether the leading two alternatives cover every 90m margin.

    Every supported settlement is constant beyond the largest integer
    handicap boundary, so the finite margin sweep also covers both tails.
    """
    if len(ranking) < 2:
        return {"status": "unavailable", "reason": "fewer than two candidates"}
    candidates = sorted(ranking, key=lambda row: row.get("rank", 10**9))[:2]
    lines = [
        abs(candidate["handicap"]["line"])
        for candidate in candidates
        if candidate.get("market_type") == "three_way_handicap"
        and isinstance(candidate.get("handicap"), dict)
        and isinstance(candidate["handicap"].get("line"), int)
    ]
    bound = max([2, *lines]) + 2
    states = [
        (_wins(candidates[0], margin), _wins(candidates[1], margin))
        for margin in range(-bound, bound + 1)
    ]
    return {
        "status": "assessed",
        "guaranteed_at_least_one": all(first or second for first, second in states),
        "identical_settlement": all(first == second for first, second in states),
        "overlap_exists": any(first and second for first, second in states),
        "uncovered_margin_examples": [
            margin - bound
            for margin, (first, second) in enumerate(states)
            if not first and not second
        ][:5],
        "interpretation": "top-two coverage is not an independent prediction hit rate",
    }


def audit_fixture(fixture: dict[str, Any], ranking: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep price cost separate from any claim of predictive or betting value."""
    ordinary = []
    for row in fixture.get("market_observations", []):
        prices = row.get("prices", {})
        if isinstance(prices, dict) and set(prices) == {"home", "draw", "away"}:
            ordinary.append({
                "bookmaker": row.get("bookmaker"),
                "observed_at": row.get("observed_at"),
                **overround([prices[key] for key in ("home", "draw", "away")]),
            })
    handicaps = []
    for row in fixture.get("three_way_handicap_observations", []):
        prices = row.get("prices", {})
        if isinstance(prices, dict) and set(prices) == {
            "side_win", "handicap_draw", "side_loss"
        }:
            handicaps.append({
                "bookmaker": row.get("bookmaker"),
                "side": row.get("side"),
                "line": row.get("line"),
                "observed_at": row.get("observed_at"),
                **overround([prices[key] for key in (
                    "side_win", "handicap_draw", "side_loss"
                )]),
            })
    exact = fixture.get("exact_total_market")
    totals = None
    if isinstance(exact, dict) and isinstance(exact.get("odds"), dict):
        odds = exact["odds"]
        if set(odds) == {"0", "1", "2", "3", "4", "5", "6", "7+"}:
            totals = {
                "observed_at": exact.get("observed_at"),
                **overround([odds[key] for key in (
                    "0", "1", "2", "3", "4", "5", "6", "7+"
                )]),
            }
    return {
        "ordinary_1x2_offers": ordinary,
        "three_way_handicap_offers": handicaps,
        "exact_total_offer": totals,
        "top_two_settlement": top_two_coverage(ranking),
        "value_status": "unproven_without_independent_calibrated_probability",
        "grade_meaning": "evidence_completeness_only_not_expected_return",
    }


def audit_record(record: dict[str, Any]) -> dict[str, Any]:
    """Audit a preserved legacy record without changing its frozen choices."""
    evidence = record.get("lottery_evidence") or {}
    prices = {}
    for name, key in (("ordinary_1x2", "ordinary"),
                      ("three_way_handicap", "handicap"),
                      ("exact_total", "exact_totals")):
        row = evidence.get(key)
        if isinstance(row, dict):
            offered = row.get("odds") if key == "exact_totals" else row.get("latest")
            if isinstance(offered, list):
                prices[name] = {"published_at": row.get("latest_at"),
                                **overround(offered)}
    return {
        "fixture_id": record.get("event", {}).get("id"),
        "original_status": record.get("report_status"),
        "price_cost": prices,
        "top_two_settlement": top_two_coverage(record.get("unified_ranking") or []),
        "value_status": "unproven_without_independent_calibrated_probability",
        "audit_scope": "retrospective_process_diagnostic_not_a_new_prediction",
    }


def self_test() -> None:
    away = {"rank": 1, "market_type": "1X2", "selection": "away"}
    plus_one = {"rank": 2, "market_type": "three_way_handicap", "handicap": {
        "side": "home", "line": 1, "outcome": "side_win"}}
    assert top_two_coverage([away, plus_one])["guaranteed_at_least_one"]
    home = {"rank": 1, "market_type": "1X2", "selection": "home"}
    minus_one_loss = {"rank": 2, "market_type": "three_way_handicap", "handicap": {
        "side": "home", "line": -1, "outcome": "side_loss"}}
    assert top_two_coverage([home, minus_one_loss])["guaranteed_at_least_one"]
    minus_one_win = {"rank": 2, "market_type": "three_way_handicap", "handicap": {
        "side": "home", "line": -1, "outcome": "side_win"}}
    assert not top_two_coverage([home, minus_one_win])["guaranteed_at_least_one"]
    assert top_two_coverage([home, minus_one_win])["overlap_exists"]
    assert math.isclose(overround([3.90, 3.97, 1.61])["overround"], 0.12941743759835989)
    print("SELF-TEST PASS: market overround and top-two settlement coverage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.records:
        self_test()
    else:
        audits = [audit_record(json.loads(path.read_text(encoding="utf-8")))
                  for path in args.records]
        summary = {
            "schema_version": "mcm-market-quality-audit/v1",
            "audited_records": len(audits),
            "top_two_guaranteed_count": sum(
                row["top_two_settlement"].get("guaranteed_at_least_one") is True
                for row in audits
            ),
            "records": audits,
        }
        rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.exists():
                parser.error("output already exists; preserved audits are append-only")
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered)

