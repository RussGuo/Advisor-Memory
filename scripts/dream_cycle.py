#!/usr/bin/env python3
"""Minimal but actionable dream-cycle workflow for advisor-memory."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    pack_domain_suggestions_path,
    pack_file_summaries_root,
    pack_human_index_path,
    pack_manifest_path,
    pack_system_root,
    pack_theme_summaries_root,
    refresh_gbrain,
    resolve_brain_root,
)
from register_library_pack import (
    apply_generated_domains,
    assign_domain,
    build_indexes,
    cleanup_legacy_generated_artifacts,
    ensure_dir,
    ensure_taxonomy,
    induce_domains,
    update_registry,
    write_json,
    write_library_map,
    write_summaries,
    write_suggestions,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an advisor-memory dream cycle.")
    parser.add_argument("--brain-root")
    parser.add_argument("--gbrain-cmd", help="Override gbrain command, e.g. 'gbrain' or 'bun run src/cli.ts'.")
    parser.add_argument(
        "--install-gbrain",
        action="store_true",
        help="If gbrain is missing, try installing it with bun during refresh.",
    )
    parser.add_argument(
        "--no-gbrain-refresh",
        action="store_true",
        help="Skip gbrain import/sync and embed. Useful for inspection-only runs.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Automatically refresh stale pack artifacts and write a promotion queue.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return path.stem
    except OSError:
        return path.stem


def scan_working_candidates(brain_root: Path) -> list[dict[str, Any]]:
    working_root = brain_root / "working"
    if not working_root.exists():
        return []
    candidates: list[dict[str, Any]] = []
    for path in sorted(working_root.rglob("*.md")):
        if path.name == "README.md" or path.name.startswith("dream-cycle-queue"):
            continue
        stat = path.stat()
        relative_path = path.relative_to(brain_root).as_posix()
        candidates.append(
            {
                "item_id": f"working:{relative_path}",
                "path": str(path),
                "title": read_title(path),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
                "size_bytes": stat.st_size,
            }
        )
    return candidates


def resolve_raw_path(raw_root: Path, raw_rel_path: str) -> Path:
    return raw_root if raw_root.is_file() else raw_root / raw_rel_path


def scan_pack_health(brain_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    libraries_root = brain_root / "sources" / "libraries"
    stale_summaries: list[dict[str, Any]] = []
    stale_maps: list[dict[str, Any]] = []
    domain_suggestions: list[dict[str, Any]] = []
    if not libraries_root.exists():
        return stale_summaries, stale_maps, domain_suggestions

    for pack_root in sorted(path for path in libraries_root.iterdir() if path.is_dir()):
        manifest_path = pack_manifest_path(pack_root)
        if not manifest_path.exists():
            continue
        manifest = load_json(manifest_path)
        raw_root = Path(manifest.get("raw_root", ""))
        summaries_root = pack_file_summaries_root(pack_root)

        for item in manifest.get("items", []):
            summary_path = summaries_root / f"{item['id'].replace(':', '__')}.md"
            raw_path = resolve_raw_path(raw_root, item["raw_rel_path"])
            if not raw_path.exists():
                stale_summaries.append(
                    {
                        "pack": pack_root.name,
                        "item_id": item["id"],
                        "reason": "missing-raw",
                        "raw_rel_path": item["raw_rel_path"],
                    }
                )
                continue
            if not summary_path.exists():
                stale_summaries.append(
                    {
                        "pack": pack_root.name,
                        "item_id": item["id"],
                        "reason": "missing-summary",
                        "summary_path": str(summary_path),
                        "raw_rel_path": item["raw_rel_path"],
                    }
                )
                continue
            if summary_path.stat().st_mtime < raw_path.stat().st_mtime:
                stale_summaries.append(
                    {
                        "pack": pack_root.name,
                        "item_id": item["id"],
                        "reason": "summary-older-than-raw",
                        "summary_path": str(summary_path),
                        "raw_rel_path": item["raw_rel_path"],
                    }
                )

        human_index_path = pack_human_index_path(pack_root)
        library_map_path = human_index_path if human_index_path.exists() else pack_theme_summaries_root(pack_root) / "library-map.md"
        if not library_map_path.exists():
            stale_maps.append({"pack": pack_root.name, "reason": "missing-library-map"})
        elif library_map_path.stat().st_mtime < manifest_path.stat().st_mtime:
            stale_maps.append(
                {
                    "pack": pack_root.name,
                    "reason": "library-map-older-than-manifest",
                    "library_map_path": str(library_map_path),
                }
            )

        suggestions_path = pack_domain_suggestions_path(pack_root)
        if suggestions_path.exists():
            suggestions = load_json(suggestions_path)
            if suggestions.get("unclassified_count", 0) > 0:
                domain_suggestions.append(
                    {
                        "pack": pack_root.name,
                        "path": str(suggestions_path),
                        "unclassified_count": suggestions.get("unclassified_count", 0),
                        "top_unclassified_tags": suggestions.get("top_unclassified_tags", [])[:10],
                        "top_unclassified_paths": suggestions.get("top_unclassified_paths", [])[:10],
                    }
                )
    return stale_summaries, stale_maps, domain_suggestions


def repair_pack(brain_root: Path, pack_name: str) -> dict[str, Any]:
    pack_root = brain_root / "sources" / "libraries" / pack_name
    existing_manifest_path = pack_manifest_path(pack_root)
    manifest = load_json(existing_manifest_path)
    items = manifest.get("items", [])

    taxonomy = ensure_taxonomy(brain_root, extra_domains={})
    for item in items:
        item["domain"] = assign_domain(item, taxonomy)

    generated_domains = induce_domains(items, taxonomy)
    if generated_domains:
        apply_generated_domains(brain_root, generated_domains)
        taxonomy = ensure_taxonomy(brain_root, extra_domains={})
        for item in items:
            item["domain"] = assign_domain(item, taxonomy)

    indexes = build_indexes(items)
    ensure_dir(pack_system_root(pack_root))
    manifest_path = pack_system_root(pack_root) / "manifest.json"
    manifest["generated_at"] = now_iso()
    manifest["item_count"] = len(items)
    manifest["items"] = items
    write_json(manifest_path, manifest)
    indexes_root = manifest_path.parent / "indexes"
    for name, payload in indexes.items():
        write_json(indexes_root / f"{name}.json", payload)
    write_summaries(pack_root, items)
    write_library_map(pack_root, items, indexes, generated_domains)
    write_suggestions(pack_root, items)
    cleanup_legacy_generated_artifacts(pack_root)
    update_registry(brain_root, manifest["pack"], pack_root, manifest.get("raw_mode", "unknown"), len(items))

    return {
        "pack": pack_name,
        "item_count": len(items),
        "generated_domains": generated_domains,
        "rewritten": [
            str(manifest_path),
            str(indexes_root),
            str(pack_file_summaries_root(pack_root)),
            str(pack_theme_summaries_root(pack_root) / "library-map.md"),
            str(pack_human_index_path(pack_root)),
            str(pack_domain_suggestions_path(pack_root)),
        ],
    }


def write_promotion_queue(
    brain_root: Path,
    working_candidates: list[dict[str, Any]],
    domain_suggestions: list[dict[str, Any]],
) -> dict[str, str]:
    queue_root = brain_root / "working" / "pending-promotions"
    ensure_dir(queue_root)
    generated_at = now_iso()

    json_path = queue_root / "dream-cycle-queue.json"
    markdown_path = queue_root / "dream-cycle-queue.md"

    payload = {
        "generated_at": generated_at,
        "working_candidates": working_candidates,
        "domain_suggestions": domain_suggestions,
    }
    write_json(json_path, payload)

    working_md = "\n".join(
        f"- `{candidate['item_id']}` | `{candidate['title']}` -> `{candidate['path']}` (modified `{candidate['modified_at']}`)"
        for candidate in working_candidates
    ) or "- none"
    suggestions_md = "\n".join(
        f"- `{entry['pack']}`: {entry['unclassified_count']} unclassified items; top tags {entry['top_unclassified_tags']}"
        for entry in domain_suggestions
    ) or "- none"

    markdown = f"""# Dream Cycle Queue / 梦境周期待处理队列

Generated / 生成时间: `{generated_at}`

## Working Candidates / 待提升工作记忆

{working_md}

## Domain Suggestions / 分类扩展建议

{suggestions_md}

## Next Actions / 建议后续动作

- Review working candidates and promote stable items into `concepts/`, `projects/`, `people/`, `companies/`, or `ideas/`.
- Promote a specific item with `python3 scripts/promote.py --brain-root /path/to/brain --item <item_id> --target concepts/example.md`.
- 审阅 `working/` 候选项，把稳定内容提升到长期记忆页面。
- Review domain suggestions and decide whether the auto-generated taxonomy should become part of the stable base map.
- 审阅自动生成的 domain 建议，决定是否合并进稳定 taxonomy。
"""
    markdown_path.write_text(markdown, encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    working_candidates = scan_working_candidates(brain_root)
    stale_summaries, stale_maps, domain_suggestions = scan_pack_health(brain_root)

    applied_repairs: list[dict[str, Any]] = []
    promotion_queue = None
    if args.apply:
        affected_packs = sorted({
            entry["pack"] for entry in stale_summaries + stale_maps + domain_suggestions
        })
        for pack_name in affected_packs:
            applied_repairs.append(repair_pack(brain_root, pack_name))
        promotion_queue = write_promotion_queue(brain_root, working_candidates, domain_suggestions)
        stale_summaries, stale_maps, domain_suggestions = scan_pack_health(brain_root)

    gbrain_refresh = None
    if not args.no_gbrain_refresh:
        try:
            gbrain_refresh = refresh_gbrain(
                brain_root,
                preferred_gbrain_cmd=args.gbrain_cmd,
                install_if_missing=args.install_gbrain,
            )
        except (FileNotFoundError, RuntimeError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
            return 1

    payload = {
        "generated_at": now_iso(),
        "brain_root": str(brain_root),
        "mode": "apply" if args.apply else "inspect",
        "working_candidates": working_candidates,
        "stale_summaries": stale_summaries,
        "stale_library_maps": stale_maps,
        "domain_suggestions": domain_suggestions,
        "applied_repairs": applied_repairs,
        "promotion_queue": promotion_queue,
        "gbrain_refresh": gbrain_refresh,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
