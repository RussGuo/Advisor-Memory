#!/usr/bin/env python3
"""Search or read one or more registered library packs inside an advisor-memory brain."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from common import pack_human_index_path, pack_manifest_path, resolve_brain_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search registered library packs.")
    parser.add_argument("--brain-root")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--pack-name")
    scope.add_argument("--all-packs", action="store_true", help="Search across every registered pack.")
    parser.add_argument("command", choices=["search", "fulltext", "read", "tags", "entities", "stats"])
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--type")
    parser.add_argument("--tag")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--lines", type=int, default=200)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(brain_root: Path, pack_name: str) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    pack_root = brain_root / "sources" / "libraries" / pack_name
    manifest_path = pack_manifest_path(pack_root)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    manifest = load_json(manifest_path)
    return manifest, manifest.get("items", []), Path(manifest["raw_root"])


def list_registered_packs(brain_root: Path) -> list[str]:
    registry_path = brain_root / "sources" / "libraries" / "registry.json"
    if registry_path.exists():
        registry = load_json(registry_path)
        packs = [str(pack["name"]) for pack in registry.get("packs", []) if pack.get("name")]
        if packs:
            return sorted(set(packs))
    libraries_root = brain_root / "sources" / "libraries"
    if not libraries_root.exists():
        return []
    packs = []
    for pack_root in sorted(path for path in libraries_root.iterdir() if path.is_dir()):
        if pack_manifest_path(pack_root).exists():
            packs.append(pack_root.name)
    return packs


def load_contexts(brain_root: Path, pack_name: str | None, all_packs: bool) -> list[dict[str, Any]]:
    pack_names = list_registered_packs(brain_root) if all_packs else [pack_name or ""]
    contexts: list[dict[str, Any]] = []
    for current_pack in pack_names:
        manifest, items, raw_root = load_manifest(brain_root, current_pack)
        contexts.append({
            "pack": current_pack,
            "manifest": manifest,
            "items": items,
            "raw_root": raw_root,
        })
    if not contexts:
        raise FileNotFoundError(f"No registered library packs under {brain_root / 'sources' / 'libraries'}")
    return contexts


def resolve_raw_path(raw_root: Path, raw_rel_path: str) -> Path:
    return raw_root if raw_root.is_file() else raw_root / raw_rel_path


def tokenize_query(query: str) -> list[str]:
    return [token for token in query.lower().split() if token]


def score_item(item: dict[str, Any], tokens: list[str], phrase: str) -> int:
    title = item.get("title", "").lower()
    abstract = item.get("abstract", "").lower()
    guest = item.get("guest", "").lower()
    raw_rel_path = item.get("raw_rel_path", "").lower()
    domain = item.get("domain", "").lower()
    tags = " ".join(item.get("tags", [])).lower()
    pack = item.get("pack", "").lower()

    score = 0
    if phrase:
        if phrase in title:
            score += 12
        if phrase in tags:
            score += 10
        if phrase in abstract:
            score += 8
        if phrase in guest or phrase in domain:
            score += 6
        if phrase in raw_rel_path or phrase in pack:
            score += 4
    for token in tokens:
        if token in title:
            score += 5
        if token in tags:
            score += 4
        if token in abstract:
            score += 3
        if token in guest or token in domain:
            score += 2
        if token in raw_rel_path or token in pack:
            score += 1
    return score


def search_contexts(contexts: list[dict[str, Any]], query: str, item_type: str | None, tag: str | None, limit: int) -> list[dict[str, Any]]:
    query_lower = query.lower().strip()
    tokens = tokenize_query(query_lower)
    results: list[dict[str, Any]] = []
    for context in contexts:
        pack_name = context["pack"]
        for item in context["items"]:
            if item_type and item.get("type") != item_type:
                continue
            if tag and tag.lower() not in [value.lower() for value in item.get("tags", [])]:
                continue
            score = 0
            if query_lower:
                score = score_item(item, tokens, query_lower)
                if score <= 0:
                    continue
            enriched = dict(item)
            enriched["pack"] = pack_name
            enriched["_score"] = score
            results.append(enriched)
    results.sort(key=lambda row: (row.get("_score", 0), row.get("date", "")), reverse=True)
    return [{key: value for key, value in item.items() if key != "_score"} for item in results[:limit]]


def fulltext_contexts(contexts: list[dict[str, Any]], query: str, item_type: str | None, limit: int) -> list[dict[str, Any]]:
    query_lower = query.lower().strip()
    if not query_lower:
        raise ValueError("fulltext requires a query")
    results: list[dict[str, Any]] = []
    for context in contexts:
        pack_name = context["pack"]
        raw_root = context["raw_root"]
        for item in context["items"]:
            if item_type and item.get("type") != item_type:
                continue
            raw_path = resolve_raw_path(raw_root, item["raw_rel_path"])
            if not raw_path.exists():
                continue
            text = raw_path.read_text(encoding="utf-8")
            if query_lower not in text.lower():
                continue
            snippets = []
            lines = text.splitlines()
            for idx, line in enumerate(lines):
                if query_lower in line.lower():
                    start = max(0, idx - 1)
                    end = min(len(lines), idx + 2)
                    snippets.append("\n".join(lines[start:end]).strip())
                    if len(snippets) >= 2:
                        break
            results.append({
                "pack": pack_name,
                "id": item["id"],
                "title": item["title"],
                "type": item["type"],
                "raw_rel_path": item["raw_rel_path"],
                "snippets": snippets,
                "_date": item.get("date", ""),
            })
    results.sort(key=lambda row: row.get("_date", ""), reverse=True)
    return [{key: value for key, value in item.items() if key != "_date"} for item in results[:limit]]


def parse_locator(locator: str) -> tuple[str | None, str]:
    if ":" in locator and locator.count(":") == 1:
        possible_pack, possible_rel = locator.split(":", 1)
        if "/" in possible_rel:
            return possible_pack, possible_rel
    return None, locator


def find_item(contexts: list[dict[str, Any]], locator: str) -> tuple[dict[str, Any] | None, str | None]:
    pack_hint, normalized_locator = parse_locator(locator)
    scoped_contexts = [context for context in contexts if context["pack"] == pack_hint] if pack_hint else contexts
    if pack_hint and not scoped_contexts:
        return None, f"Unknown pack in locator: {pack_hint}"

    exact_matches = []
    suffix_matches = []
    for context in scoped_contexts:
        pack_name = context["pack"]
        for item in context["items"]:
            if item.get("id") == locator or item.get("id") == normalized_locator:
                exact_matches.append((context, item))
                continue
            if item.get("raw_rel_path") == normalized_locator:
                exact_matches.append((context, item))
                continue
            if item.get("raw_rel_path", "").endswith(normalized_locator):
                suffix_matches.append((context, item))

    if len(exact_matches) == 1:
        context, item = exact_matches[0]
        return {
            "pack": context["pack"],
            "raw_root": context["raw_root"],
            "item": item,
        }, None
    if len(exact_matches) > 1:
        matches = [f"{context['pack']}:{item['raw_rel_path']}" for context, item in exact_matches[:5]]
        return None, f"Ambiguous locator: {locator}. Matches: {matches}"

    if len(suffix_matches) == 1:
        context, item = suffix_matches[0]
        return {
            "pack": context["pack"],
            "raw_root": context["raw_root"],
            "item": item,
        }, None
    if len(suffix_matches) > 1:
        matches = [f"{context['pack']}:{item['raw_rel_path']}" for context, item in suffix_matches[:5]]
        return None, f"Ambiguous locator: {locator}. Matches: {matches}"
    return None, None


def read_item(raw_root: Path, raw_rel_path: str, lines: int) -> dict[str, Any]:
    raw_path = resolve_raw_path(raw_root, raw_rel_path)
    if not raw_path.exists():
        return {"error": f"File not found: {raw_rel_path}"}
    content_lines = raw_path.read_text(encoding="utf-8").splitlines(True)
    return {
        "raw_rel_path": raw_rel_path,
        "content": "".join(content_lines[:lines]),
        "total_lines": len(content_lines),
        "truncated": len(content_lines) > lines,
    }


def entity_counts(contexts: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts = Counter()
    for context in contexts:
        for item in context["items"]:
            if item.get("guest"):
                counts[item["guest"]] += 1
    return counts.most_common()


def tag_counts(contexts: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts = Counter()
    for context in contexts:
        for item in context["items"]:
            counts.update(item.get("tags", []))
    return counts.most_common()


def stats_payload(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    totals = Counter()
    per_pack: dict[str, Any] = {}
    for context in contexts:
        counts = Counter(item.get("type", "unknown") for item in context["items"])
        totals.update(counts)
        per_pack[context["pack"]] = {
            "total": len(context["items"]),
            "types": dict(counts),
            "raw_root": str(context["raw_root"]),
            "human_index_path": str(pack_human_index_path(Path(context["manifest"]["pack_root"]))),
            "generated_at": context["manifest"].get("generated_at"),
        }
    if len(contexts) == 1:
        pack_name = contexts[0]["pack"]
        return {
            "pack": pack_name,
            "total": len(contexts[0]["items"]),
            "types": per_pack[pack_name]["types"],
            "raw_root": per_pack[pack_name]["raw_root"],
            "human_index_path": per_pack[pack_name]["human_index_path"],
            "generated_at": per_pack[pack_name]["generated_at"],
        }
    return {
        "scope": "all-packs",
        "pack_count": len(contexts),
        "total": sum(len(context["items"]) for context in contexts),
        "types": dict(totals),
        "packs": per_pack,
    }


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    try:
        contexts = load_contexts(brain_root, args.pack_name, args.all_packs)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    if args.command == "search":
        print(json.dumps(search_contexts(contexts, args.query, args.type, args.tag, args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "fulltext":
        print(json.dumps(fulltext_contexts(contexts, args.query, args.type, args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "read":
        match, error = find_item(contexts, args.query)
        if error:
            print(json.dumps({"error": error}, ensure_ascii=False, indent=2))
            return 1
        if not match:
            print(json.dumps({"error": f"File not found: {args.query}"}, ensure_ascii=False, indent=2))
            return 1
        payload = read_item(match["raw_root"], match["item"]["raw_rel_path"], args.lines)
        payload["pack"] = match["pack"]
        payload["id"] = match["item"]["id"]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "tags":
        for tag, count in tag_counts(contexts):
            print(f"{tag}\t{count}")
        return 0
    if args.command == "entities":
        for entity, count in entity_counts(contexts):
            print(f"{entity}\t{count}")
        return 0
    if args.command == "stats":
        print(json.dumps(stats_payload(contexts), ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
