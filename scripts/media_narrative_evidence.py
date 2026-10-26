#!/usr/bin/env python3
"""Freeze pre-kickoff media narratives as an auditable attraction signal.

This artifact describes narrative attractiveness only.  It is never measured
betting flow and never counts toward the licensed capital-evidence target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from capital_intent_engine import _audited_narrative_rows, _narrative_consensus, _time


SCHEMA = "mcm-media-narrative-freeze/v1"
VERSION = "1.8.3"
FORBIDDEN_KEYS = ("odds", "price", "bookmaker", "sportsbook", "handicap", "盘口", "赔率", "水位")


def _reject_market_fields(value: Any, path: str = "input") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            folded = str(key).casefold()
            if key != "independent_of_market" and any(term in folded for term in FORBIDDEN_KEYS):
                raise ValueError(f"{path}.{key} is market-derived and forbidden in media narrative evidence")
            _reject_market_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_market_fields(item, f"{path}[{index}]")


def _digest(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "mcmmedia_" + hashlib.sha256(body).hexdigest()[:32]


def freeze(data: dict[str, Any]) -> dict[str, Any]:
    _reject_market_fields(data)
    event = data.get("event", {})
    if not isinstance(event.get("id"), str) or not event["id"].strip() or event.get("horizon") != "90m":
        raise ValueError("event identity and 90m horizon are required")
    freeze_time = _time(data.get("freeze_time"))
    kickoff = _time(event.get("kickoff"))
    if freeze_time >= kickoff:
        raise ValueError("media narrative freeze must precede kickoff")
    accepted, audit = _audited_narrative_rows(data.get("observations"), data["freeze_time"])
    direction, consensus = _narrative_consensus(accepted)
    signal_rows = accepted if direction is not None else []
    return {
        "schema_version": SCHEMA,
        "engine_version": VERSION,
        "mode": "observe_only",
        "event": event,
        "freeze_time": data["freeze_time"],
        "narratively_attractive_direction": direction,
        "independent_attraction_available": direction is not None,
        "narrative_signals": signal_rows,
        "audit": audit,
        "consensus": consensus,
        "positioning_patch": {"narrative_signals": signal_rows, "measured_positions": []},
        "evidence_class": "media_narrative_attraction",
        "measured_capital_evidence": False,
        "counts_toward_licensed_capital_target": False,
        "capital_direction_available_from_this_artifact_alone": False,
        "capital_direction_requires": ["cross-book protection/resistance", "market-free sporting feasibility"],
        "automatic_probability_adjustment": False,
        "probability_delta_applied": 0,
        "live_ranking_changed": False,
        "input_digest": _digest(data),
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
    row = {"direction": "home", "independent_of_market": True,
           "origin_type": "editorial_media", "derived_from": "editorial_content",
           "source_name": "Publisher A", "source_group": "publisher-a",
           "source_ref": "https://a.example/story", "published_at": "2026-01-01T07:00:00Z",
           "observed_at": "2026-01-01T07:10:00Z", "syndication_key": "a-original"}
    raw = {"event": {"id": "media-1", "kickoff": "2026-01-01T12:00:00Z", "horizon": "90m"},
           "freeze_time": "2026-01-01T10:00:00Z", "observations": [
               row, {**row, "source_name": "Publisher B", "source_group": "publisher-b",
                     "source_ref": "https://b.example/story", "syndication_key": "b-original"}]}
    output = freeze(raw)
    if output["narratively_attractive_direction"] != "home" or output["counts_toward_licensed_capital_target"]:
        raise AssertionError("independent media consensus or capital boundary failed")
    copied = json.loads(json.dumps(raw)); copied["observations"][1]["syndication_key"] = "a-original"
    if freeze(copied)["independent_attraction_available"]:
        raise AssertionError("syndicated copies were double-counted")
    contaminated = json.loads(json.dumps(raw)); contaminated["observations"][0]["odds"] = 1.8
    try:
        freeze(contaminated)
    except ValueError:
        pass
    else:
        raise AssertionError("market-derived media evidence was accepted")
    post = json.loads(json.dumps(raw)); post["observations"][0]["observed_at"] = "2026-01-01T10:01:00Z"
    if freeze(post)["independent_attraction_available"]:
        raise AssertionError("post-freeze media evidence was accepted")
    print("SELF-TEST PASS: media narratives are frozen, deduplicated and isolated from measured capital")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("input", type=Path)
    freeze_parser.add_argument("--output", required=True, type=Path)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
        else:
            _write_new(args.output, freeze(json.loads(args.input.read_text(encoding="utf-8"))))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

