#!/usr/bin/env python3
"""Promote a working-memory item or library source into a durable brain page."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import refresh_gbrain, resolve_brain_root
from register_library_pack import parse_simple_frontmatter
from search_library_pack import find_item, load_contexts, resolve_raw_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote a queue item or source item into a durable concept/project/person/company page."
    )
    parser.add_argument("--brain-root")
    parser.add_argument("--item", required=True, help="Working item id/path or library item id/path.")
    parser.add_argument("--target", required=True, help="Target page path inside the brain, e.g. concepts/pmf.md")
    parser.add_argument("--title", help="Optional explicit page title.")
    parser.add_argument(
        "--summary",
        help="Optional executive summary override. If omitted, promote.py derives a scaffold summary from the source.",
    )
    parser.add_argument(
        "--replace-compiled-truth",
        action="store_true",
        help="Rewrite compiled truth instead of preserving an existing one.",
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


def slug_to_title(value: str) -> str:
    return re.sub(r"[-_]+", " ", value).strip().title()


def infer_page_type(target_path: Path) -> str:
    lowered = ("/" + target_path.as_posix()).lower()
    if "/people/" in lowered:
        return "person"
    if "/companies/" in lowered:
        return "company"
    if "/projects/" in lowered:
        return "project"
    if "/media/" in lowered:
        return "media"
    return "concept"


def split_page_body(body: str) -> tuple[str, str]:
    lines = body.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "---" and any(existing.strip() for existing in lines[:idx]):
            compiled_truth = "\n".join(lines[:idx]).strip()
            timeline = "\n".join(lines[idx + 1 :]).strip()
            return compiled_truth, timeline
    return body.strip(), ""


def render_frontmatter(
    page_type: str,
    title: str,
    tags: list[str],
    extra: dict[str, Any],
) -> str:
    lines = ["---", f"type: {json.dumps(page_type, ensure_ascii=False)}", f"title: {json.dumps(title, ensure_ascii=False)}"]
    if tags:
        lines.append(f"tags: {json.dumps(tags, ensure_ascii=False)}")
    for key, value in extra.items():
        if key in {"type", "title", "tags"}:
            continue
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def serialize_page(
    page_type: str,
    title: str,
    tags: list[str],
    extra_frontmatter: dict[str, Any],
    compiled_truth: str,
    timeline: str,
) -> str:
    frontmatter = render_frontmatter(page_type, title, tags, extra_frontmatter)
    body = compiled_truth.strip()
    if timeline.strip():
        body += "\n\n---\n\n" + timeline.strip()
    return frontmatter + "\n\n" + body.strip() + "\n"


def parse_existing_page(target_path: Path) -> dict[str, Any]:
    if not target_path.exists():
        return {
            "type": infer_page_type(target_path),
            "title": slug_to_title(target_path.stem),
            "tags": [],
            "frontmatter": {},
            "compiled_truth": "",
            "timeline": "",
        }
    text = target_path.read_text(encoding="utf-8")
    frontmatter, body = parse_simple_frontmatter(text)
    compiled_truth, timeline = split_page_body(body)
    tags = frontmatter.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    cleaned_frontmatter = dict(frontmatter)
    cleaned_frontmatter.pop("tags", None)
    page_type = str(cleaned_frontmatter.pop("type", infer_page_type(target_path)))
    title = str(cleaned_frontmatter.pop("title", slug_to_title(target_path.stem)))
    return {
        "type": page_type,
        "title": title,
        "tags": [str(tag) for tag in tags],
        "frontmatter": cleaned_frontmatter,
        "compiled_truth": compiled_truth,
        "timeline": timeline,
    }


def extract_first_heading_and_paragraph(text: str, fallback_title: str) -> tuple[str, str]:
    _, body = parse_simple_frontmatter(text)
    title = fallback_title
    paragraph = ""
    lines = body.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip() or fallback_title
            break
    paragraphs = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if stripped.startswith("#"):
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current).strip())
    for candidate in paragraphs:
        if candidate:
            paragraph = candidate
            break
    return title, paragraph


def normalize_target(brain_root: Path, target: str) -> Path:
    candidate = Path(target).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (brain_root / candidate).resolve()
    try:
        resolved.relative_to(brain_root)
    except ValueError as exc:
        raise ValueError(f"Target must live inside the brain root: {resolved}") from exc
    if resolved.suffix.lower() != ".md":
        raise ValueError(f"Target must be a markdown file: {resolved}")
    return resolved


def resolve_working_item(brain_root: Path, locator: str) -> dict[str, Any] | None:
    working_root = brain_root / "working"
    candidates = []
    normalized = locator.removeprefix("working:")
    direct_candidates = [
        Path(locator).expanduser(),
        brain_root / normalized,
        working_root / normalized,
    ]
    for path in direct_candidates:
        if path.exists() and path.is_file():
            resolved = path.resolve()
            if resolved not in candidates:
                candidates.append(resolved)

    if not candidates and working_root.exists():
        suffix_matches = [
            path.resolve()
            for path in working_root.rglob("*.md")
            if path.name == Path(normalized).name or path.as_posix().endswith(normalized)
        ]
        deduped = []
        seen = set()
        for path in suffix_matches:
            if str(path) in seen:
                continue
            seen.add(str(path))
            deduped.append(path)
        candidates = deduped

    if not candidates:
        return None
    if len(candidates) > 1:
        raise ValueError(f"Ambiguous working item: {locator}. Matches: {[str(path) for path in candidates[:5]]}")

    path = candidates[0]
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(brain_root).as_posix()
    title, paragraph = extract_first_heading_and_paragraph(text, slug_to_title(path.stem))
    return {
        "kind": "working",
        "item_id": f"working:{relative}",
        "title": title,
        "summary": paragraph or f"Promoted from `{relative}`.",
        "source_label": f"working:{relative}",
        "source_path": str(path),
        "raw_text": text,
        "raw_excerpt": paragraph or text[:800],
        "domain": "working",
        "tags": ["working-memory"],
    }


def resolve_library_item(brain_root: Path, locator: str) -> dict[str, Any] | None:
    contexts = load_contexts(brain_root, None, True)
    match, error = find_item(contexts, locator)
    if error:
        raise ValueError(error)
    if not match:
        return None
    item = match["item"]
    raw_root = match["raw_root"]
    raw_path = resolve_raw_path(raw_root, item["raw_rel_path"])
    text = raw_path.read_text(encoding="utf-8")
    title, paragraph = extract_first_heading_and_paragraph(text, item.get("title", slug_to_title(Path(item["raw_rel_path"]).stem)))
    abstract = item.get("abstract", "")
    return {
        "kind": "library",
        "pack": match["pack"],
        "item_id": item["id"],
        "title": item.get("title") or title,
        "summary": abstract or paragraph or f"Promoted from `{match['pack']}:{item['raw_rel_path']}`.",
        "source_label": f"{match['pack']}:{item['raw_rel_path']}",
        "source_path": str(raw_path),
        "raw_text": text,
        "raw_excerpt": paragraph or abstract or text[:800],
        "domain": item.get("domain", "unclassified"),
        "tags": [str(tag) for tag in item.get("tags", [])],
        "raw_rel_path": item["raw_rel_path"],
        "date": item.get("date", ""),
    }


def resolve_source(brain_root: Path, locator: str) -> dict[str, Any]:
    working = resolve_working_item(brain_root, locator)
    if working:
        return working
    library = resolve_library_item(brain_root, locator)
    if library:
        return library
    raise ValueError(f"Could not resolve item: {locator}")


def build_compiled_truth(
    source: dict[str, Any],
    target_path: Path,
    explicit_summary: str | None,
) -> str:
    page_title = slug_to_title(target_path.stem)
    summary = explicit_summary or source["summary"] or f"Promoted from `{source['source_label']}`."
    source_excerpt = source.get("raw_excerpt", "").strip()
    domain = source.get("domain", "unclassified")
    source_path = source["source_label"]
    lines = [
        "## Executive Summary",
        summary,
        "",
        "## Current Synthesis",
        f"- This page was promoted into durable memory from `{source_path}`.",
        f"- Initial domain signal: `{domain}`.",
        f"- Use this as a scaffold and rewrite it into a stable judgment for `{page_title}` after review.",
    ]
    if source_excerpt:
        lines.extend([
            "",
            "## Source Snapshot",
            source_excerpt,
        ])
    return "\n".join(lines).strip()


def prepend_timeline_entry(existing_timeline: str, entry: str) -> str:
    if not existing_timeline.strip():
        return "## Timeline\n\n" + entry
    stripped = existing_timeline.strip()
    if stripped.startswith("## Timeline"):
        body = stripped[len("## Timeline") :].lstrip()
        if body:
            return "## Timeline\n\n" + entry + "\n\n" + body
        return "## Timeline\n\n" + entry
    return "## Timeline\n\n" + entry + "\n\n" + stripped


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
        target_path = normalize_target(brain_root, args.target)
        source = resolve_source(brain_root, args.item)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    existing = parse_existing_page(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    page_type = existing["type"] or infer_page_type(target_path)
    title = args.title or existing["title"] or source["title"] or slug_to_title(target_path.stem)
    tags = sorted(set(existing["tags"] + ["advisor-memory", source.get("domain", "unclassified")] + source.get("tags", [])))

    source_refs = [str(value) for value in existing["frontmatter"].get("source_refs", [])] if isinstance(existing["frontmatter"].get("source_refs"), list) else []
    if source["source_label"] not in source_refs:
        source_refs.append(source["source_label"])

    extra_frontmatter = {
        **existing["frontmatter"],
        "source_refs": source_refs,
        "last_promoted_at": now_iso(),
        "last_promoted_from": source["source_label"],
    }

    compiled_truth = existing["compiled_truth"]
    if args.replace_compiled_truth or not compiled_truth.strip():
        compiled_truth = build_compiled_truth(source, target_path, args.summary)

    timestamp = datetime.now(timezone.utc).date().isoformat()
    timeline_entry = (
        f"- **{timestamp}** | Promoted `{source['source_label']}` into `{target_path.relative_to(brain_root).as_posix()}`.\n"
        f"  Initial summary: {source['summary']}\n"
        f"  [Source: advisor-memory promote.py]"
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
        "item": args.item,
        "resolved_source": source["source_label"],
        "target": str(target_path),
        "page_type": page_type,
        "title": title,
        "compiled_truth_mode": "replaced" if args.replace_compiled_truth or not existing["compiled_truth"].strip() else "preserved",
        "gbrain_refresh": gbrain_refresh,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
