#!/usr/bin/env python3
"""Infer a falsifiable capital-intent card from independent evidence layers.

This is a hypothesis screen, not a manipulation detector.  It separates
narrative/measured attraction, cross-book protection and sporting feasibility,
then records whether the inducement hypothesis is supported, rejected or still
unresolved.  No capital label directly changes numerical probabilities.
"""

from __future__ import annotations

from datetime import datetime
import math
import statistics
from typing import Any


DIRECTIONS = ("home", "draw", "away")
NARRATIVE_ORIGINS = {
    "editorial_media",
    "official_team_news",
    "official_league_news",
    "independent_public_discussion",
}
NARRATIVE_BASES = {"editorial_content", "team_news", "league_news", "public_discussion"}


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("capital observation requires a timezone-aware timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("capital observation timestamp must include a timezone")
    return parsed


def _devig(prices: Any) -> dict[str, float]:
    if not isinstance(prices, dict) or set(prices) != set(DIRECTIONS):
        raise ValueError("capital market prices must contain home, draw and away")
    raw = {}
    for direction in DIRECTIONS:
        value = prices[direction]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 1:
            raise ValueError("capital market prices must be valid decimal odds")
        raw[direction] = 1.0 / float(value)
    total = sum(raw.values())
    return {key: value / total for key, value in raw.items()}


def _directions(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [item["direction"] for item in items if isinstance(item, dict) and item.get("direction") in DIRECTIONS]


def _audited_measured_rows(items: Any, freeze_time: str) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(items, list):
        return [], 0
    freeze = _time(freeze_time)
    allowed_metrics = {"bet_share", "turnover", "liability", "exchange_volume"}
    valid = []
    for item in items:
        if not isinstance(item, dict) or item.get("direction") not in DIRECTIONS:
            continue
        if item.get("measurement_type") not in allowed_metrics:
            continue
        if not all(isinstance(item.get(key), str) and item[key].strip() for key in ("source_group", "license_basis", "observed_at")):
            continue
        try:
            observed = _time(item["observed_at"])
        except ValueError:
            continue
        if observed <= freeze:
            valid.append(item)
    return valid, len(items) - len(valid)


def _audited_narrative_rows(items: Any, freeze_time: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep only frozen, attributable and genuinely non-market narrative rows.

    One publisher group receives at most one vote and syndicated copies receive
    at most one vote across all publishers.  Conflicting rows inside one source
    group are excluded instead of averaged.
    """
    if not isinstance(items, list):
        return [], {"input_rows": 0, "accepted_rows": 0, "rejected_rows": 0,
                    "accepted_source_groups": [], "reasons": {}}
    freeze = _time(freeze_time)
    reasons: dict[str, int] = {}

    def reject(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    candidates: list[dict[str, Any]] = []
    required = ("source_group", "source_name", "source_ref", "published_at", "observed_at",
                "origin_type", "derived_from", "syndication_key")
    for item in items:
        if not isinstance(item, dict) or item.get("direction") not in DIRECTIONS:
            reject("invalid_direction_or_row")
            continue
        if item.get("independent_of_market") is not True:
            reject("not_declared_market_independent")
            continue
        if not all(isinstance(item.get(key), str) and item[key].strip() for key in required):
            reject("incomplete_provenance")
            continue
        if item.get("origin_type") not in NARRATIVE_ORIGINS or item.get("derived_from") not in NARRATIVE_BASES:
            reject("market_or_unsupported_origin")
            continue
        try:
            published = _time(item["published_at"])
            observed = _time(item["observed_at"])
        except ValueError:
            reject("invalid_timestamp")
            continue
        if published > observed or observed > freeze:
            reject("post_freeze_or_incoherent_time")
            continue
        candidates.append(item)

    by_group: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        by_group.setdefault(item["source_group"].strip(), []).append(item)
    group_rows: list[dict[str, Any]] = []
    for rows in by_group.values():
        if len({row["direction"] for row in rows}) != 1:
            for _ in rows:
                reject("conflict_within_source_group")
            continue
        rows.sort(key=lambda row: _time(row["observed_at"]))
        group_rows.append(rows[0])

    accepted: list[dict[str, Any]] = []
    seen_syndication: set[str] = set()
    for row in sorted(group_rows, key=lambda item: _time(item["observed_at"])):
        family = row["syndication_key"].strip().casefold()
        if family in seen_syndication:
            reject("duplicate_syndication_family")
            continue
        seen_syndication.add(family)
        accepted.append(row)
    diagnostics = {
        "input_rows": len(items),
        "accepted_rows": len(accepted),
        "rejected_rows": len(items) - len(accepted),
        "accepted_source_groups": sorted(row["source_group"] for row in accepted),
        "accepted_syndication_families": sorted(seen_syndication),
        "reasons": reasons,
    }
    return accepted, diagnostics


def _narrative_consensus(rows: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    counts = {direction: sum(row["direction"] == direction for row in rows) for direction in DIRECTIONS}
    ordered = sorted(DIRECTIONS, key=lambda direction: counts[direction], reverse=True)
    leader, runner = ordered[0], ordered[1]
    required = max(2, math.ceil(len(rows) * 2 / 3))
    available = len(rows) >= 2 and counts[leader] >= required and counts[leader] > counts[runner]
    return (leader if available else None), {
        "counts": counts,
        "required_support": required,
        "independent_source_groups": len(rows),
        "status": "available" if available else "insufficient_or_conflicting",
    }


def infer(fixture: dict[str, Any], market: dict[str, Any] | None, baseline: dict[str, Any] | None,
          adjusted: dict[str, Any] | None, freeze_time: str) -> dict[str, Any]:
    market_one_x_two = market.get("one_x_two") if isinstance(market, dict) else None
    market_direction = max(market_one_x_two, key=market_one_x_two.get) if isinstance(market_one_x_two, dict) else None
    if baseline is None or market is None or not isinstance(market_one_x_two, dict):
        return {
            "freeze_time": freeze_time, "market_only_direction": market_direction,
            "sporting_baseline_direction": None, "attraction": {"direction": None, "evidence": []},
            "protection": {"direction": None, "evidence": []}, "feasibility": {"direction": None, "evidence": []},
            "attraction_basis": "unavailable",
            "leg_independence": {"attraction": False, "protection": False, "feasibility": False},
            "loop_status": "none", "ci_grade": "CI-1" if market else "CI-0", "capital_direction": None,
            "combined_direction": market_direction, "without_capital_direction": market_direction,
            "incremental_effect": "unavailable", "independent_evidence_groups": ["audited market family"] if market else [],
            "candidate_label": "unresolved" if market else "none", "red_team_passed": False,
            "hypothesis_status": "unresolved", "non_intent_alternative": "ordinary repricing, liquidity or stale quotes",
            "strongest_support": "no independent sporting anchor", "strongest_contradiction": "capital motive cannot be separated from price",
            "falsifier": "a frozen independent sporting baseline becomes available", "reorder_condition": "independent sporting and cross-book evidence become available",
            "diagnostics": {"reason": "independent sporting baseline or audited ordinary 1X2 unavailable"},
        }
    sporting = baseline["probabilities"]["one_x_two"]
    sporting_direction = max(sporting, key=sporting.get)
    observations = fixture.get("market_observations", [])
    per_book: dict[str, list[tuple[datetime, dict[str, float]]]] = {}
    for row in observations:
        if not isinstance(row, dict) or not isinstance(row.get("bookmaker"), str):
            continue
        per_book.setdefault(row["bookmaker"], []).append((_time(row.get("observed_at")), _devig(row.get("prices"))))
    for values in per_book.values():
        values.sort(key=lambda item: item[0])
    latest = [values[-1][1] for values in per_book.values() if values]
    cross_book = len(latest) >= 2
    dispersion = {
        d: statistics.pstdev([row[d] for row in latest]) if len(latest) >= 2 else 0.0
        for d in DIRECTIONS
    }
    temporal = {}
    signed_moves = {}
    move_consensus = {}
    for d in DIRECTIONS:
        moves = [abs(values[-1][1][d] - values[0][1][d]) for values in per_book.values() if len(values) >= 2]
        temporal[d] = statistics.fmean(moves) if moves else 0.0
        directional_moves = [values[-1][1][d] - values[0][1][d] for values in per_book.values() if len(values) >= 2]
        signed_moves[d] = statistics.fmean(directional_moves) if directional_moves else 0.0
        move_consensus[d] = sum(value > 0 for value in directional_moves)
    residual = {d: market["one_x_two"][d] - sporting[d] for d in DIRECTIONS}
    thresholds = {d: max(0.025, 1.5 * dispersion[d] + 0.5 * temporal[d]) for d in DIRECTIONS}
    persistent_moves = [d for d in DIRECTIONS if move_consensus[d] >= 2 and signed_moves[d] > max(0.015, dispersion[d])]
    if persistent_moves:
        protected = max(persistent_moves, key=lambda d: signed_moves[d])
        protection_basis = "persistent cross-book shortening"
    else:
        strongest_residual = max(DIRECTIONS, key=lambda d: residual[d])
        protected = strongest_residual if cross_book and residual[strongest_residual] > thresholds[strongest_residual] else None
        protection_basis = "market-versus-independent residual"
    positioning = fixture.get("positioning", {})
    measured_input = positioning.get("measured_positions", []) if isinstance(positioning, dict) else []
    measured_rows, rejected_measured = _audited_measured_rows(measured_input, freeze_time)
    narrative_rows = positioning.get("narrative_signals", []) if isinstance(positioning, dict) else []
    measured = _directions(measured_rows)
    independent_narrative_rows, narrative_audit = _audited_narrative_rows(narrative_rows, freeze_time)
    narrative_direction, narrative_consensus = _narrative_consensus(independent_narrative_rows)
    if len(set(measured)) == 1:
        attraction = measured[0]
        attraction_basis = "measured_positioning"
        attraction_independent = True
        attraction_kind = "measured positioning"
    elif not measured and narrative_direction is not None:
        attraction = narrative_direction
        attraction_basis = "independent_narrative"
        attraction_independent = True
        attraction_kind = f"independent media narrative ({narrative_consensus['counts'][narrative_direction]} source groups)"
    else:
        attraction = market_direction
        attraction_basis = "market_price_accessibility"
        attraction_independent = False
        attraction_kind = "market price accessibility fallback"
    leg_independence = {
        "attraction": attraction_independent,
        "protection": bool(cross_book and protected is not None),
        "feasibility": True,
    }
    independent_known = sum(leg_independence.values())
    if protected is not None and protected != sporting_direction:
        loop = "broken"
    else:
        loop = "closed" if independent_known == 3 else "partial" if independent_known >= 2 else "none"
    label = "unresolved"
    capital_direction = None
    hypothesis_status = "unresolved"
    if protected == sporting_direction and protected is not None:
        capital_direction = protected
        if attraction_independent and attraction != protected:
            label = "inducement_candidate"
            hypothesis_status = "supported"
        elif attraction_independent and attraction == protected:
            label = "straight_support_candidate"
            hypothesis_status = "inducement_rejected_by_current_evidence"
        else:
            label = "upset_candidate"
            hypothesis_status = "unresolved_attraction_not_independent"
    elif protected is not None and protected != sporting_direction:
        hypothesis_status = "unresolved_conflict"
    groups = []
    if baseline is not None:
        groups.append("independent sporting baseline")
    if cross_book:
        groups.append("cross-book de-vigged market structure")
    if measured:
        groups.append("measured positioning")
    elif narrative_direction is not None:
        groups.append("independent media narrative attraction")
    red_team = cross_book and capital_direction is not None and protected == capital_direction
    if label != "unresolved" and red_team:
        # Automated inference is capped at CI-2. CI-3 additionally requires a
        # human-reviewed frozen capital sample and full-report acceptance.
        ci = "CI-2"
    else:
        ci = "CI-1"
        label = "unresolved"
        capital_direction = None
    no_capital = sporting_direction
    combined = capital_direction or (max(adjusted["one_x_two"], key=adjusted["one_x_two"].get) if adjusted else sporting_direction)
    return {
        "freeze_time": freeze_time, "market_only_direction": market_direction,
        "sporting_baseline_direction": sporting_direction,
        "attraction": {"direction": attraction, "evidence": [f"{attraction_kind}: {attraction}"] if attraction else []},
        "protection": {"direction": protected, "evidence": ([f"{protection_basis}: residual={residual[protected]:+.3f}, signed_move={signed_moves[protected]:+.3f}, threshold={thresholds[protected]:.3f}"] if protected else ["no cross-book residual or persistent move cleared its data-driven threshold"] )},
        "feasibility": {"direction": sporting_direction, "evidence": [f"market-free score matrix argmax: {sporting_direction}"]},
        "attraction_basis": attraction_basis, "leg_independence": leg_independence,
        "loop_status": loop, "ci_grade": ci, "capital_direction": capital_direction,
        "combined_direction": combined, "without_capital_direction": no_capital,
        "incremental_effect": "changed" if capital_direction and combined != no_capital else "strengthened" if capital_direction else "none",
        "independent_evidence_groups": groups, "candidate_label": label, "red_team_passed": red_team,
        "hypothesis_status": hypothesis_status,
        "non_intent_alternative": "ordinary information repricing, model misspecification, liquidity or stale quotes",
        "strongest_support": (f"protection and feasibility align on {capital_direction}" if capital_direction else "no two independent directional legs align above noise"),
        "strongest_contradiction": ("attraction is not independent of the audited market" if not attraction_independent else "attraction and protected direction conflict" if capital_direction and attraction != capital_direction else "independent and market layers do not establish inducement"),
        "falsifier": "the supporting cross-book movement/residual falls below its dynamic threshold or independent feasibility reverses",
        "reorder_condition": "two independent legs reverse before kickoff",
        "diagnostics": {"market_minus_independent": residual, "cross_book_dispersion": dispersion, "temporal_noise": temporal, "signed_moves": signed_moves, "move_consensus": move_consensus, "dynamic_thresholds": thresholds, "book_count": len(latest), "accepted_measured_position_rows": len(measured_rows), "rejected_measured_position_rows": rejected_measured, "narrative_audit": narrative_audit, "narrative_consensus": narrative_consensus, "narrative_is_measured_capital": False},
    }


def self_test() -> None:
    baseline = {"probabilities": {"one_x_two": {"home": .25, "draw": .25, "away": .50}}}
    market = {"one_x_two": {"home": .55, "draw": .25, "away": .20}}
    fixture = {"market_observations": [
        {"bookmaker": "a", "observed_at": "2026-01-01T07:00:00Z", "prices": {"home": 1.70, "draw": 4, "away": 5}},
        {"bookmaker": "a", "observed_at": "2026-01-01T08:00:00Z", "prices": {"home": 2.00, "draw": 3.8, "away": 3.6}},
        {"bookmaker": "b", "observed_at": "2026-01-01T07:01:00Z", "prices": {"home": 1.72, "draw": 4, "away": 4.9}},
        {"bookmaker": "b", "observed_at": "2026-01-01T08:01:00Z", "prices": {"home": 2.02, "draw": 3.8, "away": 3.55}},
    ], "positioning": {"narrative_signals": [{"direction": "home"}], "measured_positions": []}}
    static_fixture = dict(fixture, market_observations=[fixture["market_observations"][1], fixture["market_observations"][3]])
    card = infer(static_fixture, market, baseline, {"one_x_two": baseline["probabilities"]["one_x_two"]}, "2026-01-01T09:00:00Z")
    if card["ci_grade"] != "CI-1" or card["candidate_label"] != "unresolved":
        raise AssertionError("conflicting protection and feasibility must remain unresolved")
    aligned_market = {"one_x_two": {"home": .48, "draw": .25, "away": .27}}
    aligned = infer(fixture, aligned_market, baseline, {"one_x_two": baseline["probabilities"]["one_x_two"]}, "2026-01-01T09:00:00Z")
    if aligned["candidate_label"] not in {"inducement_candidate", "upset_candidate"} or aligned["capital_direction"] != "away":
        raise AssertionError("capital engine failed to choose an independently supported direction")
    no_base = infer(fixture, market, None, None, "2026-01-01T09:00:00Z")
    if no_base["ci_grade"] != "CI-1" or no_base["candidate_label"] != "unresolved":
        raise AssertionError("no-baseline card escaped the CI-1 cap")
    media_row = {"direction": "home", "independent_of_market": True,
        "origin_type": "editorial_media", "derived_from": "editorial_content",
        "source_name": "Publisher A", "source_group": "publisher-a", "source_ref": "https://a.example/story",
        "published_at": "2026-01-01T07:10:00Z", "observed_at": "2026-01-01T07:20:00Z",
        "syndication_key": "publisher-a-original"}
    two_media = dict(fixture, positioning={"measured_positions": [], "narrative_signals": [
        media_row, {**media_row, "source_name": "Publisher B", "source_group": "publisher-b",
                    "source_ref": "https://b.example/story", "syndication_key": "publisher-b-original"}]})
    media_card = infer(two_media, aligned_market, baseline, {"one_x_two": baseline["probabilities"]["one_x_two"]}, "2026-01-01T09:00:00Z")
    if not media_card["leg_independence"]["attraction"] or media_card["attraction_basis"] != "independent_narrative":
        raise AssertionError("two independent frozen media groups did not form the attraction leg")
    one_media = dict(fixture, positioning={"measured_positions": [], "narrative_signals": [media_row]})
    one_card = infer(one_media, aligned_market, baseline, {"one_x_two": baseline["probabilities"]["one_x_two"]}, "2026-01-01T09:00:00Z")
    if one_card["leg_independence"]["attraction"]:
        raise AssertionError("one media group incorrectly formed an independent attraction leg")
    copied = dict(fixture, positioning={"measured_positions": [], "narrative_signals": [
        media_row, {**media_row, "source_name": "Publisher B", "source_group": "publisher-b",
                    "source_ref": "https://b.example/copy"}]})
    copied_card = infer(copied, aligned_market, baseline, {"one_x_two": baseline["probabilities"]["one_x_two"]}, "2026-01-01T09:00:00Z")
    if copied_card["leg_independence"]["attraction"]:
        raise AssertionError("syndicated copies incorrectly formed independent media evidence")
    print("SELF-TEST PASS: capital triangulation, strict media narrative and no-baseline controls")


if __name__ == "__main__":
    self_test()

