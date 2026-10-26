#!/usr/bin/env python3
"""Verify MCM checkpoint evidence against preserved configuration and files.

This is a process gate, not a certification of provider independence or of
predictive accuracy.  Missing, stale, mismapped, or tampered odds stay missing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is missing")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must have a timezone")
    return result


def _read_bound_json(proof: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(proof, dict):
        raise ValueError("artifact proof must be an object")
    path = proof.get("path")
    digest = proof.get("sha256")
    if not isinstance(path, str) or not path.strip() or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("artifact proof requires path and SHA-256")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest().casefold() != digest.casefold():
        raise ValueError("artifact SHA-256 mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("artifact must contain a JSON object")
    return value


def _valid_books(snapshot: dict[str, Any], fixture: dict[str, Any],
                 actual: datetime, max_quote_age: int) -> set[str]:
    books: set[str] = set()
    for source_name, source in (snapshot.get("sources") or {}).items():
        if not isinstance(source, dict) or source.get("status") != "ok":
            continue
        for row in source.get("fixtures", []):
            if (not isinstance(row, dict) or row.get("fixture_id") != fixture["id"]
                    or row.get("mapping_status") != "mapped"
                    or row.get("home_team") != fixture["home"]
                    or row.get("away_team") != fixture["away"]):
                continue
            for book in row.get("bookmakers", []):
                if not isinstance(book, dict):
                    continue
                key = book.get("bookmaker_key")
                if not isinstance(key, str) or not key.strip():
                    continue
                for market in book.get("markets", []):
                    if not isinstance(market, dict) or market.get("market_key") != "h2h":
                        continue
                    outcomes = market.get("outcomes")
                    if (isinstance(outcomes, list) and len(outcomes) == 3
                            and all(isinstance(item, dict)
                                    and isinstance(item.get("price"), (int, float))
                                    and not isinstance(item.get("price"), bool)
                                    and item["price"] > 1 for item in outcomes)):
                        names = [str(item.get("name", "")).strip().casefold() for item in outcomes]
                        if (len(set(names)) != 3
                                or fixture["home"].strip().casefold() not in names
                                or fixture["away"].strip().casefold() not in names
                                or not any(name in {"draw", "x", "tie"} for name in names)):
                            continue
                        try:
                            quote_time = _time(market.get("last_update") or book.get("last_update"))
                        except ValueError:
                            continue
                        if quote_time <= actual and actual - quote_time <= timedelta(minutes=max_quote_age):
                            books.add(key.casefold())
    return books


def audit(fixture_id: str, kickoff: str, evidence: Any) -> dict[str, Any]:
    """Derive checkpoint coverage from bound artifacts, never caller counters."""
    result: dict[str, Any] = {
        "status": "unverified", "required_checkpoints": 0,
        "captured_checkpoints": 0, "late_snapshot_available": False,
        "cross_book_available": False, "last_valid_bookmaker_count": 0,
        "checkpoint_results": [], "reasons": [],
    }
    if not isinstance(evidence, dict):
        result["reasons"].append("monitoring configuration and snapshot proofs absent")
        return result
    try:
        config = _read_bound_json(evidence.get("config"))
        if config.get("settlement_scope") != "90m":
            raise ValueError("monitor configuration does not use 90m settlement")
        fixture = next((row for row in config.get("fixtures", [])
                        if isinstance(row, dict) and row.get("id") == fixture_id), None)
        if fixture is None or _time(fixture.get("kickoff")) != _time(kickoff):
            raise ValueError("monitor fixture identity or kickoff differs from report")
        checkpoints = config.get("checkpoints")
        if not isinstance(checkpoints, list) or not checkpoints:
            raise ValueError("monitor configuration has no planned checkpoints")
        tolerance = int(config.get("late_tolerance_minutes", 0))
        if not 0 <= tolerance <= 30:
            raise ValueError("monitor lateness tolerance is invalid")
        max_quote_age = config.get("max_quote_age_minutes")
        if (isinstance(max_quote_age, bool) or not isinstance(max_quote_age, int)
                or not 1 <= max_quote_age <= 240):
            raise ValueError("monitor config must declare max_quote_age_minutes (1..240)")
        proofs = evidence.get("snapshots")
        if not isinstance(proofs, list):
            raise ValueError("snapshot proof list is missing")
        by_id = {proof.get("checkpoint_id"): proof for proof in proofs
                 if isinstance(proof, dict)}
        if len(by_id) != len(proofs):
            raise ValueError("snapshot proofs contain missing or duplicate ids")
        result["required_checkpoints"] = len(checkpoints)
        ordered = sorted(checkpoints, key=lambda row: _time(row["utc"]))
        planned_ids = [row["id"] for row in ordered]
        if len(set(planned_ids)) != len(planned_ids):
            raise ValueError("monitor configuration contains duplicate checkpoint ids")
        if set(by_id) - set(planned_ids):
            raise ValueError("snapshot proofs contain unplanned checkpoint ids")
        last_id = ordered[-1]["id"]
        for checkpoint in ordered:
            cid = checkpoint["id"]
            entry = {"checkpoint_id": cid, "valid": False, "bookmaker_count": 0}
            result["checkpoint_results"].append(entry)
            proof = by_id.get(cid)
            if proof is None:
                entry["reason"] = "snapshot proof missing"
                continue
            try:
                snapshot = _read_bound_json(proof)
                scheduled = _time(checkpoint["utc"])
                actual = _time(snapshot.get("actual_run_at"))
                if (snapshot.get("matchday_id") != config.get("matchday_id")
                        or snapshot.get("checkpoint_id") != cid
                        or _time(snapshot.get("scheduled_at")) != scheduled
                        or snapshot.get("settlement_scope") != "90m"
                        or actual < scheduled
                        or actual > scheduled + timedelta(minutes=tolerance)
                        or actual >= _time(kickoff)):
                    raise ValueError("snapshot identity, horizon or collection time invalid")
                books = _valid_books(snapshot, fixture, actual, max_quote_age)
                if not books:
                    raise ValueError("no mapped complete 1X2 bookmaker offer")
                entry.update(valid=True, bookmaker_count=len(books), actual_run_at=actual.isoformat())
                result["captured_checkpoints"] += 1
                if cid == last_id:
                    result["late_snapshot_available"] = True
                    result["last_valid_bookmaker_count"] = len(books)
                    result["cross_book_available"] = len(books) >= 2
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                entry["reason"] = str(exc)
        result["status"] = "verified" if (
            result["captured_checkpoints"] == result["required_checkpoints"]
        ) else "partial"
        if result["status"] != "verified":
            result["reasons"].append("not every planned checkpoint has valid mapped odds")
        if not result["cross_book_available"]:
            result["reasons"].append("last valid checkpoint lacks two distinct bookmaker ids")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        result["reasons"].append(str(exc))
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        fixture = {"id": "test-1", "home": "Home", "away": "Away",
                   "kickoff": "2026-09-20T00:00:00+08:00"}
        config = {"matchday_id": "test", "settlement_scope": "90m",
                  "late_tolerance_minutes": 9, "max_quote_age_minutes": 60,
                  "fixtures": [fixture],
                  "checkpoints": [{"id": "t1", "utc": "2026-09-19T12:00:00Z"}]}
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        books = [{"bookmaker_key": key, "markets": [{"market_key": "h2h",
                  "last_update": "2026-09-19T11:59:00Z",
                  "outcomes": [{"name": name, "price": 2.0}
                               for name in ("Home", "Draw", "Away")]}]}
                 for key in ("book-a", "book-b")]
        snapshot = {"matchday_id": "test", "checkpoint_id": "t1",
                    "scheduled_at": "2026-09-19T12:00:00Z",
                    "actual_run_at": "2026-09-19T12:00:10Z", "settlement_scope": "90m",
                    "sources": {"provider": {"status": "ok", "fixtures": [{
                        "fixture_id": "test-1", "mapping_status": "mapped",
                        "home_team": "Home", "away_team": "Away", "bookmakers": books}]}}}
        snap_path = root / "snapshot.json"
        snap_path.write_text(json.dumps(snapshot), encoding="utf-8")
        proof = lambda path: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        evidence = {"config": proof(config_path),
                    "snapshots": [{"checkpoint_id": "t1", **proof(snap_path)}]}
        good = audit("test-1", fixture["kickoff"], evidence)
        assert good["status"] == "verified" and good["cross_book_available"]
        snap_path.write_text(snap_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        bad = audit("test-1", fixture["kickoff"], evidence)
        assert bad["status"] == "partial" and bad["captured_checkpoints"] == 0
    print("SELF-TEST PASS: artifact-bound checkpoint and bookmaker coverage")


if __name__ == "__main__":
    self_test()

