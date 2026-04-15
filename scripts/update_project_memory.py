#!/usr/bin/env python3
"""Apply a confirmed project-memory review into a durable project page."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import refresh_gbrain, resolve_brain_root
from promote import infer_page_type, normalize_target, parse_existing_page, prepend_timeline_entry, serialize_page


MANAGED_BLOCK_START = "<!-- advisor-memory:project-review:start -->"
MANAGED_BLOCK_END = "<!-- advisor-memory:project-review:end -->"
MANAGED_BLOCK_RE = re.compile(
    rf"{re.escape(MANAGED_BLOCK_START)}.*?{re.escape(MANAGED_BLOCK_END)}",
    re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a confirmed consult review into a durable project page."
    )
    parser.add_argument("--brain-root")
    parser.add_argument("--review-file", required=True, help="Path to a project-memory review JSON file.")
    parser.add_argument(
        "--project-target",
        help="Optional override for the target project page inside the brain. Defaults to the review's project_target.",
    )
    parser.add_argument(
        "--accept",
        required=True,
        help="Comma-separated candidate ids to accept, or `all` / `default`.",
    )
    parser.add_argument("--gbrain-cmd", help="Override gbrain command, e.g. 'gbrain' or 'bun run src/cli.ts'.")
    parser.add_argument(
        "--install-gbrain",
        action="store_true",
        help="If gbrain is missing, try installing it with bun during refresh.",
    )
    parser.add_argument("--no-sync-gbrain", action="store_true", help="Skip GBrain refresh after writing the page.")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def replace_managed_block(compiled_truth: str, new_block: str) -> str:
    if MANAGED_BLOCK_RE.search(compiled_truth):
        return MANAGED_BLOCK_RE.sub(new_block, compiled_truth).strip()
    if compiled_truth.strip():
        return compiled_truth.strip() + "\n\n" + new_block
    return new_block


def build_managed_block(
    query: str,
    accepted_candidates: list[dict[str, Any]],
    recommended_reads: list[dict[str, Any]],
    durable_pages: list[str],
    reviewed_at: str,
) -> str:
    focus = [item["text"] for item in accepted_candidates if item.get("kind") == "focus"]
    non_focus = [item["text"] for item in accepted_candidates if item.get("kind") != "focus"]

    lines = [
        MANAGED_BLOCK_START,
        "## Advisor-Memory Project Review",
        f"Last reviewed: `{reviewed_at}`",
        f"Review query: {query}",
    ]

    if focus:
        lines.extend([
            "",
            "### Current Focus",
            *[f"- {text}" for text in focus],
        ])

    if non_focus:
        lines.extend([
            "",
            "### Confirmed Updates",
            *[f"- {text}" for text in non_focus],
        ])

    if durable_pages:
        lines.extend([
            "",
            "### Related Durable Memory",
            *[f"- `{slug}`" for slug in durable_pages[:5]],
        ])

    if recommended_reads:
        lines.extend([
            "",
            "### Supporting Sources",
            *[
                f"- `{entry['pack']}` | {entry['title']} -> `{entry['raw_rel_path']}`"
                for entry in recommended_reads[:5]
            ],
        ])

    lines.append(MANAGED_BLOCK_END)
    return "\n".join(lines)


def accepted_source_refs(accepted_candidates: list[dict[str, Any]], recommended_reads: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in accepted_candidates:
        for ref in item.get("source_refs", []):
            if ref not in refs:
                refs.append(str(ref))
    for entry in recommended_reads[:5]:
        for ref in (entry.get("id"), f"{entry.get('pack')}:{entry.get('raw_rel_path')}"):
            if ref and ref not in refs:
                refs.append(str(ref))
    return refs


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    review_path = Path(args.review_file).expanduser().resolve()
    if not review_path.exists():
        print(json.dumps({"error": f"Review file not found: {review_path}"}, ensure_ascii=False, indent=2))
        return 1

    review = load_json(review_path)
    target_value = args.project_target or review.get("project_target")
    if not target_value:
        print(json.dumps({"error": "Review file does not define a project_target."}, ensure_ascii=False, indent=2))
        return 1

    try:
        target_path = normalize_target(brain_root, str(target_value))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    accept_mode = args.accept.strip().lower()
    accept_all = accept_mode == "all"
    accept_default = accept_mode == "default"
    accepted_ids = {item.strip() for item in args.accept.split(",") if item.strip()}
    candidates = review.get("candidate_updates", [])
    accepted_candidates = [
        item for item in candidates
        if accept_all
        or (accept_default and bool(item.get("default_selected")))
        or str(item.get("id", "")) in accepted_ids
    ]
    if not accepted_candidates:
        print(json.dumps({"error": "No candidate updates selected. Pass --accept all, --accept default, or specific ids."}, ensure_ascii=False, indent=2))
        return 1

    existing = parse_existing_page(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    page_type = existing["type"] or infer_page_type(target_path)
    title = existing["title"] or target_path.stem.replace("-", " ").replace("_", " ").title()

    managed_block = build_managed_block(
        review.get("query", ""),
        accepted_candidates,
        review.get("recommended_reads", []),
        review.get("durable_pages", []),
        now_iso(),
    )

    compiled_truth = existing["compiled_truth"].strip()
    if not compiled_truth:
        compiled_truth = "## Executive Summary\nProject page updated from an advisor-memory consult review."
    compiled_truth = replace_managed_block(compiled_truth, managed_block)

    source_refs = [str(value) for value in existing["frontmatter"].get("source_refs", [])] if isinstance(existing["frontmatter"].get("source_refs"), list) else []
    for ref in accepted_source_refs(accepted_candidates, review.get("recommended_reads", [])):
        if ref not in source_refs:
            source_refs.append(ref)

    extra_frontmatter = {
        **existing["frontmatter"],
        "source_refs": source_refs,
        "last_project_review_at": now_iso(),
        "last_project_review_query": review.get("query", ""),
        "last_project_review_file": str(review_path),
    }
    tags = sorted(set(existing["tags"] + ["advisor-memory", "project-memory-review"]))

    accepted_text = "; ".join(item["text"] for item in accepted_candidates[:4])
    if len(accepted_candidates) > 4:
        accepted_text += "; ..."
    timestamp = datetime.now(timezone.utc).date().isoformat()
    timeline_entry = (
        f"- **{timestamp}** | Applied consult review `{review_path.name}` to `{target_path.relative_to(brain_root).as_posix()}`.\n"
        f"  Query: {review.get('query', '')}\n"
        f"  Confirmed updates: {accepted_text}\n"
        "  [Source: advisor-memory update_project_memory.py]"
    )
    timeline = prepend_timeline_entry(existing["timeline"], timeline_entry)

    content = serialize_page(page_type, title, tags, extra_frontmatter, compiled_truth, timeline)
    target_path.write_text(content, encoding="utf-8")

    gbrain_refresh = None
    if not args.no_sync_gbrain:
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
        "status": "ok",
        "review_file": str(review_path),
        "target": str(target_path),
        "accepted_ids": [item.get("id") for item in accepted_candidates],
        "page_type": page_type,
        "title": title,
        "gbrain_refresh": gbrain_refresh,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
