#!/usr/bin/env python3
"""Validate and resolve reviewed cross-provider football identities.

There is deliberately no fuzzy matching. Unknown or conflicting identities are
returned for manual review so provider joins cannot silently contaminate data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "mcm-identity-registry/v1"


def _normalise(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def validate(registry: dict[str, Any]) -> dict[str, Any]:
    if registry.get("schema_version") != SCHEMA or not isinstance(registry.get("entries"), list):
        raise ValueError("identity registry schema_version/entries invalid")
    canonical_seen: set[str] = set()
    provider_ids: dict[tuple[str, str], str] = {}
    aliases: dict[tuple[str, str], str] = {}
    for index, entry in enumerate(registry["entries"]):
        if not isinstance(entry, dict):
            raise ValueError(f"entries[{index}] must be an object")
        canonical_id = entry.get("canonical_team_id")
        canonical_name = entry.get("canonical_name")
        providers = entry.get("providers")
        if not all(isinstance(value, str) and value.strip() for value in (canonical_id, canonical_name)) or not isinstance(providers, dict):
            raise ValueError(f"entries[{index}] identity fields invalid")
        if canonical_id in canonical_seen:
            raise ValueError(f"duplicate canonical_team_id: {canonical_id}")
        canonical_seen.add(canonical_id)
        for provider, mapping in providers.items():
            if not isinstance(provider, str) or not provider.strip() or not isinstance(mapping, dict):
                raise ValueError(f"entries[{index}].providers invalid")
            provider_key = provider.casefold()
            provider_id = mapping.get("id")
            if provider_id is not None:
                if not isinstance(provider_id, str) or not provider_id.strip():
                    raise ValueError(f"entries[{index}] provider id invalid")
                key = (provider_key, provider_id)
                if key in provider_ids:
                    raise ValueError(f"duplicate provider id: {provider}/{provider_id}")
                provider_ids[key] = canonical_id
            names = mapping.get("names", [])
            if not isinstance(names, list) or not names or not all(isinstance(name, str) and name.strip() for name in names):
                raise ValueError(f"entries[{index}] reviewed aliases invalid")
            for name in names:
                key = (provider_key, _normalise(name))
                if key in aliases:
                    raise ValueError(f"duplicate reviewed alias: {provider}/{name}")
                aliases[key] = canonical_id
    return {"valid": True, "entry_count": len(canonical_seen), "provider_id_count": len(provider_ids), "reviewed_alias_count": len(aliases)}


def resolve(registry: dict[str, Any], provider: str, provider_id: str | None, name: str | None) -> dict[str, Any]:
    validate(registry)
    by_id = None
    by_name = None
    for entry in registry["entries"]:
        mapping = entry["providers"].get(provider)
        if not isinstance(mapping, dict):
            mapping = next((value for key, value in entry["providers"].items() if key.casefold() == provider.casefold()), None)
        if not isinstance(mapping, dict):
            continue
        if provider_id is not None and mapping.get("id") == provider_id:
            by_id = entry
        if isinstance(name, str) and _normalise(name) in {_normalise(alias) for alias in mapping.get("names", [])}:
            by_name = entry
    if by_id and by_name and by_id["canonical_team_id"] != by_name["canonical_team_id"]:
        return {"status": "conflict", "canonical_team_id": None, "requires_manual_review": True}
    entry = by_id or by_name
    if entry:
        return {"status": "mapped_by_id" if by_id else "mapped_by_reviewed_alias", "canonical_team_id": entry["canonical_team_id"], "canonical_name": entry["canonical_name"], "requires_manual_review": False}
    return {"status": "unresolved", "canonical_team_id": None, "requires_manual_review": True}


def self_test() -> None:
    registry = {"schema_version": SCHEMA, "entries": [
        {"canonical_team_id": "team-a", "canonical_name": "Team A", "providers": {"p1": {"id": "1", "names": ["Team A"]}}},
        {"canonical_team_id": "team-b", "canonical_name": "Team B", "providers": {"p1": {"id": "2", "names": ["Team B"]}}},
    ]}
    if resolve(registry, "p1", "1", "Team A")["status"] != "mapped_by_id":
        raise AssertionError("reviewed identity resolution failed")
    if resolve(registry, "p1", None, "Team C")["status"] != "unresolved":
        raise AssertionError("unknown identity was auto-accepted")
    if resolve(registry, "p1", "1", "Team B")["status"] != "conflict":
        raise AssertionError("identity conflict was not blocked")
    print("SELF-TEST PASS: strict reviewed identity mapping and conflict gate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("registry", type=Path)
    lookup = sub.add_parser("resolve")
    lookup.add_argument("registry", type=Path)
    lookup.add_argument("--provider", required=True)
    lookup.add_argument("--provider-id")
    lookup.add_argument("--name")
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
        else:
            registry = json.loads(args.registry.read_text(encoding="utf-8"))
            result = validate(registry) if args.command == "validate" else resolve(registry, args.provider, args.provider_id, args.name)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

