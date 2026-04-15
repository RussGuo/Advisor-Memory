#!/usr/bin/env python3
"""Default advisor-wide consult entrypoint for advisor-memory."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import ensure_gbrain_command, has_embedding_credentials, resolve_brain_root, run_command
from promote import normalize_target, parse_existing_page
from search_library_pack import load_contexts, resolve_raw_path, score_item, tokenize_query


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consult advisor-memory across GBrain and all relevant library packs by default."
    )
    parser.add_argument("--brain-root")
    parser.add_argument(
        "--pack-name",
        action="append",
        default=[],
        help="Optional pack restriction. Omit to search across the full advisor memory.",
    )
    parser.add_argument("--gbrain-cmd", help="Override gbrain command, e.g. 'gbrain' or 'bun run src/cli.ts'.")
    parser.add_argument(
        "--install-gbrain",
        action="store_true",
        help="If gbrain is missing, try installing it with bun before consult.",
    )
    parser.add_argument("--gbrain-limit", type=int, default=8)
    parser.add_argument("--pack-limit", type=int, default=3)
    parser.add_argument("--docs-per-pack", type=int, default=2)
    parser.add_argument("--read-lines", type=int, default=80)
    parser.add_argument("--context-radius", type=int, default=50)
    parser.add_argument(
        "--project-target",
        help="Optional project page path inside the brain, e.g. projects/project-a.md. When set, consult writes a project-memory review that should be confirmed by the user before applying.",
    )
    parser.add_argument("query")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_stem(value: str) -> str:
    lowered = value.lower().strip().replace("/", "-")
    return re.sub(r"[^a-z0-9._-]+", "-", lowered).strip("-") or "project"


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def load_taxonomy(brain_root: Path) -> dict[str, list[str]]:
    base_path = brain_root / "sources" / "domain_taxonomy.json"
    generated_path = brain_root / "sources" / "domain_taxonomy.generated.json"
    base = load_json(base_path) if base_path.exists() else {"domains": {}}
    generated = load_json(generated_path) if generated_path.exists() else {"domains": {}}
    merged: dict[str, set[str]] = {}
    for payload in (base.get("domains", {}), generated.get("domains", {})):
        for domain, keywords in payload.items():
            merged.setdefault(domain, set()).update(str(keyword) for keyword in keywords)
    return {domain: sorted(values) for domain, values in merged.items()}


def merge_domain_payloads(*payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for entry in payload:
            domain = str(entry.get("domain", "")).strip()
            if not domain:
                continue
            existing = merged.get(domain)
            matched_keywords = sorted(set((existing or {}).get("matched_keywords", []) + entry.get("matched_keywords", [])))
            score = max(int(entry.get("score", 0)), int((existing or {}).get("score", 0)))
            merged[domain] = {
                "domain": domain,
                "score": score,
                "matched_keywords": matched_keywords,
            }
    return sorted(merged.values(), key=lambda row: (row["score"], row["domain"]), reverse=True)


def infer_domains(query: str, taxonomy: dict[str, list[str]]) -> list[dict[str, Any]]:
    lowered = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    padded = f" {lowered} "
    results: list[dict[str, Any]] = []
    for domain, keywords in taxonomy.items():
        if domain == "unclassified":
            continue
        matched = []
        for keyword in keywords:
            normalized = re.sub(r"[^a-z0-9]+", " ", str(keyword).lower()).strip()
            if normalized and f" {normalized} " in padded:
                matched.append(normalized)
        if matched:
            results.append({
                "domain": domain,
                "score": len(matched),
                "matched_keywords": sorted(set(matched)),
            })
    results.sort(key=lambda row: (row["score"], row["domain"]), reverse=True)
    return results


def extract_timeline_entries(timeline: str, limit: int = 3) -> list[str]:
    entries = []
    current: list[str] = []
    for line in timeline.splitlines():
        if line.startswith("- **"):
            if current:
                entries.append("\n".join(current).strip())
                current = []
            current.append(line)
            continue
        if current:
            current.append(line)
    if current:
        entries.append("\n".join(current).strip())
    return [entry for entry in entries[:limit] if entry]


def project_identifiers(project_path: Path, page: dict[str, Any]) -> list[str]:
    aliases = page["frontmatter"].get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []
    identifiers = [
        page["title"],
        project_path.stem.replace("-", " ").replace("_", " "),
        " ".join(part.replace("-", " ").replace("_", " ") for part in project_path.parts[-2:]),
        *[str(alias) for alias in aliases],
    ]
    deduped = []
    seen = set()
    for identifier in identifiers:
        normalized = normalize_text(str(identifier))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(str(identifier))
    return deduped


def resolve_project_context(
    brain_root: Path,
    query: str,
    explicit_target: str | None,
    taxonomy: dict[str, list[str]],
) -> dict[str, Any] | None:
    if explicit_target:
        project_path = normalize_target(brain_root, explicit_target)
        page = parse_existing_page(project_path)
        mode = "explicit"
        score = None
        matched_identifiers = [page["title"]]
    else:
        projects_root = brain_root / "projects"
        if not projects_root.exists():
            return None
        query_normalized = normalize_text(query)
        padded_query = f" {query_normalized} "
        query_tokens = [token for token in query_normalized.split() if token]
        best: tuple[int, Path, dict[str, Any], list[str]] | None = None
        for project_path in sorted(projects_root.rglob("*.md")):
            page = parse_existing_page(project_path)
            identifiers = project_identifiers(project_path, page)
            current_score = 0
            matched_identifiers: list[str] = []
            for identifier in identifiers:
                normalized_identifier = normalize_text(identifier)
                if not normalized_identifier:
                    continue
                if f" {normalized_identifier} " in padded_query:
                    current_score += 24 + len(normalized_identifier.split())
                    matched_identifiers.append(identifier)
                    continue
                identifier_tokens = normalized_identifier.split()
                overlap = sum(1 for token in query_tokens if token in identifier_tokens)
                if overlap:
                    current_score += overlap * 4
                    matched_identifiers.append(identifier)
            if current_score <= 0:
                continue
            if best is None or current_score > best[0]:
                best = (current_score, project_path, page, matched_identifiers)
        if best is None or best[0] < 6:
            return None
        score, project_path, page, matched_identifiers = best
        mode = "auto"

    compiled_truth = page["compiled_truth"].strip()
    compiled_truth_excerpt = compiled_truth[:3000].strip()
    timeline_entries = extract_timeline_entries(page["timeline"], limit=3)
    explicit_domains = page["frontmatter"].get("domains", [])
    if not isinstance(explicit_domains, list):
        explicit_domains = []
    domain_signals = []
    stable_domain_names = set(taxonomy.keys())
    for candidate in [*explicit_domains, *page["tags"]]:
        normalized = normalize_text(str(candidate))
        if normalized in stable_domain_names and normalized != "unclassified":
            domain_signals.append({
                "domain": normalized,
                "score": 1,
                "matched_keywords": [normalized],
            })
    domain_signals = merge_domain_payloads(domain_signals)
    return {
        "path": project_path.relative_to(brain_root).as_posix(),
        "title": page["title"],
        "tags": page["tags"],
        "compiled_truth": compiled_truth,
        "compiled_truth_excerpt": compiled_truth_excerpt,
        "timeline_entries": timeline_entries,
        "source_refs": page["frontmatter"].get("source_refs", []),
        "resolution": {
            "mode": mode,
            "score": score,
            "matched_identifiers": matched_identifiers,
        },
        "domain_signals": domain_signals,
    }


def parse_gbrain_results(output: str) -> list[dict[str, Any]]:
    results = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line == "No results.":
            continue
        match = re.match(r"^\[(?P<score>[^\]]+)\]\s+(?P<slug>\S+)\s+--\s*(?P<excerpt>.*)$", line)
        if not match:
            continue
        try:
            score = float(match.group("score"))
        except ValueError:
            score = 0.0
        results.append({
            "score": score,
            "slug": match.group("slug"),
            "excerpt": match.group("excerpt"),
        })
    return results


def run_gbrain_lookup(query: str, limit: int, gbrain_cmd: str | None, install_gbrain: bool) -> dict[str, Any]:
    try:
        command_prefix, command_cwd = ensure_gbrain_command(gbrain_cmd, install_if_missing=install_gbrain)
    except FileNotFoundError as exc:
        return {
            "status": "unavailable",
            "warning": str(exc),
            "query_hits": [],
            "search_hits": [],
            "selected_pages": [],
        }

    semantic_enabled = has_embedding_credentials()
    outputs: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    operations = ("query", "search") if semantic_enabled else ("search",)
    for op_name in operations:
        command = command_prefix + [op_name, query, "--limit", str(limit)]
        completed = run_command(command, cwd=command_cwd)
        if completed.returncode != 0:
            warnings.append((completed.stderr or completed.stdout).strip())
            outputs[f"{op_name}_hits"] = []
            continue
        outputs[f"{op_name}_hits"] = parse_gbrain_results(completed.stdout)

    combined_by_slug: dict[str, dict[str, Any]] = {}
    for source_name in ("query_hits", "search_hits"):
        for hit in outputs.get(source_name, []):
            existing = combined_by_slug.get(hit["slug"])
            merged = {
                "slug": hit["slug"],
                "score": max(hit["score"], existing["score"]) if existing else hit["score"],
                "excerpt": hit["excerpt"],
                "sources": sorted(set((existing or {}).get("sources", []) + [source_name.replace("_hits", "")])),
            }
            combined_by_slug[hit["slug"]] = merged

    selected_pages = []
    sorted_hits = sorted(
        combined_by_slug.values(),
        key=lambda row: (not row["slug"].startswith("sources/libraries/"), row["score"]),
        reverse=True,
    )
    chosen = []
    for hit in sorted_hits:
        if hit["slug"].startswith("sources/libraries/"):
            continue
        chosen.append(hit)
        if len(chosen) >= 3:
            break

    for hit in chosen:
        command = command_prefix + ["get", hit["slug"]]
        completed = run_command(command, cwd=command_cwd)
        if completed.returncode != 0:
            warnings.append((completed.stderr or completed.stdout).strip())
            continue
        selected_pages.append({
            "slug": hit["slug"],
            "score": hit["score"],
            "sources": hit["sources"],
            "excerpt": hit["excerpt"],
            "content": completed.stdout,
        })

    payload = {
        "mode": "semantic-hybrid" if semantic_enabled else "keyword-first",
        "status": "ok" if outputs.get("query_hits") or outputs.get("search_hits") or selected_pages else "empty",
        "query_hits": outputs.get("query_hits", []),
        "search_hits": outputs.get("search_hits", []),
        "selected_pages": selected_pages,
    }
    if not semantic_enabled:
        payload["note"] = (
            "No OpenAI embedding credential detected. GBrain lookup ran in keyword-first mode "
            "and advisor-memory relied on pack metadata/fulltext/raw reads for deeper evidence."
        )
    if not selected_pages and combined_by_slug:
        payload["fallback_note"] = (
            "GBrain returned source-library hits, but no durable non-library pages were selected for `get`. "
            "Use the selected pack raw reads as the main evidence layer."
        )
    if warnings:
        payload["warnings"] = warnings
    return payload


def load_registry(brain_root: Path) -> dict[str, Any]:
    registry_path = brain_root / "sources" / "libraries" / "registry.json"
    if not registry_path.exists():
        return {"packs": []}
    return load_json(registry_path)


def pick_contexts(brain_root: Path, restricted_packs: list[str]) -> list[dict[str, Any]]:
    if restricted_packs:
        contexts = []
        for pack_name in restricted_packs:
            contexts.extend(load_contexts(brain_root, pack_name, False))
        return contexts
    return load_contexts(brain_root, None, True)


def score_pack(
    context: dict[str, Any],
    query: str,
    routed_domains: list[str],
    gbrain_hits: list[dict[str, Any]],
    docs_per_pack: int,
) -> dict[str, Any]:
    tokens = tokenize_query(query.lower().strip())
    metadata_hits = []
    for item in context["items"]:
        score = score_item(item, tokens, query.lower().strip())
        if score <= 0:
            continue
        metadata_hits.append({
            "id": item["id"],
            "title": item["title"],
            "type": item.get("type"),
            "domain": item.get("domain", "unclassified"),
            "date": item.get("date", ""),
            "raw_rel_path": item["raw_rel_path"],
            "score": score,
        })
    metadata_hits.sort(key=lambda row: (row["score"], row.get("date", "")), reverse=True)

    registry_domains = list(context["manifest"].get("domains", []))
    if not registry_domains:
        registry_domains = sorted({item.get("domain", "unclassified") for item in context["items"]})
    domain_overlap = [domain for domain in routed_domains if domain in registry_domains]

    gbrain_raw_hits = [
        hit for hit in gbrain_hits
        if hit["slug"].startswith(f"sources/libraries/{context['pack']}/raw/")
    ]

    top_score = metadata_hits[0]["score"] if metadata_hits else 0
    pack_score = top_score + len(metadata_hits[:5]) * 2 + len(domain_overlap) * 6 + len(gbrain_raw_hits) * 3

    return {
        "pack": context["pack"],
        "pack_root": context["manifest"].get("pack_root"),
        "domains": registry_domains,
        "domain_overlap": domain_overlap,
        "metadata_hits": metadata_hits[: max(6, docs_per_pack * 3)],
        "gbrain_raw_hits": gbrain_raw_hits[:4],
        "score": pack_score,
    }


def raw_evidence_for_pack(
    context: dict[str, Any],
    query: str,
    docs_per_pack: int,
    read_lines: int,
    context_radius: int,
    metadata_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def pick_segment(lines: list[str], phrase: str, line_tokens: list[str]) -> tuple[int, int, int, str, list[int]]:
        best_idx = 0
        best_score = 0
        matched_lines: list[int] = []
        for idx, line in enumerate(lines):
            lowered_line = line.lower()
            line_score = 0
            if phrase and phrase in lowered_line:
                line_score += 24
            token_hits = 0
            for token in line_tokens:
                if token in lowered_line:
                    token_hits += 1
                    line_score += 5
            if token_hits > 0 and line_score > 0:
                matched_lines.append(idx + 1)
            if line_score > best_score:
                best_idx = idx
                best_score = line_score

        if best_score <= 0:
            end = min(len(lines), read_lines)
            return 0, end, 0, "head-fallback", []

        start = max(0, best_idx - context_radius)
        end = min(len(lines), best_idx + context_radius + 1)
        if end - start > read_lines:
            end = min(len(lines), start + read_lines)
        return start, end, best_score, "matched-window", matched_lines[:10]

    query_lower = query.lower().strip()
    tokens = tokenize_query(query_lower)
    metadata_scores = {hit["id"]: int(hit.get("score", 0)) for hit in metadata_hits}
    candidates = []
    for item in context["items"]:
        raw_path = resolve_raw_path(context["raw_root"], item["raw_rel_path"])
        if not raw_path.exists():
            continue
        try:
            text = raw_path.read_text(encoding="utf-8")
        except OSError:
            continue
        lowered = text.lower()
        score = 0
        if query_lower and query_lower in lowered:
            score += 24
        for token in tokens:
            if token in lowered:
                score += 4
        score += min(metadata_scores.get(item["id"], 0), 20)
        if score <= 0:
            continue
        content_lines = text.splitlines(True)
        start_line, end_line, segment_score, segment_mode, matched_lines = pick_segment(content_lines, query_lower, tokens)
        excerpt = "".join(content_lines[start_line:end_line])
        candidates.append({
            "id": item["id"],
            "title": item["title"],
            "type": item.get("type"),
            "domain": item.get("domain", "unclassified"),
            "date": item.get("date", ""),
            "raw_rel_path": item["raw_rel_path"],
            "score": score + segment_score,
            "content": excerpt,
            "total_lines": len(content_lines),
            "truncated": start_line > 0 or end_line < len(content_lines),
            "line_range": [start_line + 1, end_line],
            "segment_mode": segment_mode,
            "matched_lines": matched_lines,
        })
    candidates.sort(key=lambda row: (row["score"], row.get("date", "")), reverse=True)
    return candidates[:docs_per_pack]


def build_advisory_path() -> list[str]:
    return [
        "1. Query GBrain durable memory first / 先查 GBrain 长期记忆",
        "2. Infer likely domains from the question / 从问题推断领域",
        "3. Score every registered pack, then auto-select the most relevant ones / 对所有 pack 打分并自动选择最相关的几个",
        "4. Read raw source files from the selected packs / 读取选中 pack 的原文",
        "5. Synthesize advice from durable memory plus raw evidence / 用长期记忆和原始证据一起综合回答",
    ]


def build_answer_contract(project_context: dict[str, Any] | None) -> list[str]:
    if project_context:
        project_title = project_context["title"]
        return [
            f"Answer as a recommendation for `{project_title}`, not as a corpus summary. / 以 `{project_title}` 的项目建议来回答，而不是资料摘要。",
            "Start with the concrete decision, recommendation, or next move. / 先给明确决策、建议或下一步。",
            "Explain why that recommendation fits the current project context. / 解释为什么这个建议适合当前项目上下文。",
            "Use external packs as supporting evidence, not as the center of gravity. / 外部 pack 只作为支撑证据，不要喧宾夺主。",
            "End with risks, tradeoffs, and 2-3 actionable next steps. / 最后给风险、取舍和 2-3 个可执行下一步。",
        ]
    return [
        "Answer as advice or synthesis, not as a document dump. / 用建议或综合判断回答，不要只做资料转述。",
        "Prefer recommendation plus evidence over summary plus links. / 优先给建议加证据，而不是摘要加链接。",
    ]


def summarize_compiled_truth(compiled_truth: str) -> str:
    for paragraph in compiled_truth.split("\n\n"):
        stripped = paragraph.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        return " ".join(stripped.split())[:320]
    return ""


def build_project_memory_review(
    *,
    brain_root: Path,
    project_target: Path,
    query: str,
    routed_domains_payload: list[dict[str, Any]],
    gbrain_payload: dict[str, Any],
    recommended_reads: list[dict[str, Any]],
) -> dict[str, Any]:
    existing = parse_existing_page(project_target)
    relative_target = project_target.relative_to(brain_root).as_posix()
    routed_domains = [entry["domain"] for entry in routed_domains_payload]
    durable_pages = [
        page["slug"]
        for page in gbrain_payload.get("selected_pages", [])
        if not str(page.get("slug", "")).startswith("sources/libraries/")
    ]
    top_reads = recommended_reads[:3]

    candidate_updates: list[dict[str, Any]] = [
        {
            "id": "consult-focus",
            "kind": "focus",
            "text": f"Current strategic question under review: {query}",
            "source_refs": [],
            "default_selected": True,
        }
    ]

    if routed_domains:
        candidate_updates.append(
            {
                "id": "active-domains",
                "kind": "domains",
                "text": f"Domains most relevant to this consult: {', '.join(routed_domains)}.",
                "source_refs": [],
                "default_selected": True,
            }
        )

    if durable_pages:
        candidate_updates.append(
            {
                "id": "related-durable-pages",
                "kind": "durable-links",
                "text": "Related durable pages to reconcile with this project: " + ", ".join(durable_pages[:5]),
                "source_refs": durable_pages[:5],
                "default_selected": True,
            }
        )
    else:
        candidate_updates.append(
            {
                "id": "durable-memory-gap",
                "kind": "memory-gap",
                "text": "This consult surfaced little or no matching durable project memory. If the conclusion matters, write it back to the project page.",
                "source_refs": [],
                "default_selected": False,
            }
        )

    if top_reads:
        candidate_updates.append(
            {
                "id": "supporting-sources",
                "kind": "sources",
                "text": "Supporting sources surfaced: "
                + "; ".join(f"{entry['title']} ({entry['pack']})" for entry in top_reads),
                "source_refs": [entry["id"] for entry in top_reads if entry.get("id")],
                "default_selected": True,
            }
        )

    generated_at = now_iso()
    review_root = brain_root / "working" / "project-memory-reviews"
    review_root.mkdir(parents=True, exist_ok=True)
    base_name = f"{generated_at[:19].replace(':', '-')}-{sanitize_stem(project_target.stem)}"
    review_json_path = review_root / f"{base_name}.json"
    review_md_path = review_root / f"{base_name}.md"

    review = {
        "generated_at": generated_at,
        "status": "needs-confirmation",
        "query": query,
        "project_target": relative_target,
        "project_title": existing["title"],
        "existing_project_summary": summarize_compiled_truth(existing["compiled_truth"]),
        "candidate_updates": candidate_updates,
        "recommended_reads": top_reads,
        "durable_pages": durable_pages[:5],
        "confirmation_prompt": (
            f"This consult surfaced {len(candidate_updates)} possible updates for `{relative_target}`. "
            "Confirm with the user before writing them into durable project memory."
        ),
    }
    write_json(review_json_path, review)

    candidates_md = "\n".join(
        f"- `{item['id']}` | {item['text']}"
        for item in candidate_updates
    ) or "- none"
    reads_md = "\n".join(
        f"- `{entry['pack']}` | {entry['title']} -> `{entry['raw_rel_path']}`"
        for entry in top_reads
    ) or "- none"
    markdown = f"""# Project Memory Review / 项目记忆待确认更新

Generated / 生成时间: `{generated_at}`
Project / 项目页: `{relative_target}`
Query / 咨询问题: {query}

## Existing Project Summary / 现有项目摘要

{review['existing_project_summary'] or '- empty / 当前为空'}

## Candidate Updates / 候选更新

{candidates_md}

## Supporting Reads / 支撑来源

{reads_md}

## Confirmation Rule / 确认规则

- Ask the user whether these updates should be written back into the project page.
- Confirm first, then run `python3 scripts/update_project_memory.py --brain-root {brain_root} --review-file {review_json_path} --accept default`.
"""
    review_md_path.write_text(markdown, encoding="utf-8")
    review["review_json_path"] = str(review_json_path)
    review["review_markdown_path"] = str(review_md_path)
    review["suggested_apply_command"] = (
        f"python3 scripts/update_project_memory.py --brain-root {brain_root} "
        f"--review-file {review_json_path} --accept default"
    )
    write_json(review_json_path, review)
    return review


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    query = args.query.strip()
    registry = load_registry(brain_root)
    contexts = pick_contexts(brain_root, args.pack_name)
    taxonomy = load_taxonomy(brain_root)
    query_domains_payload = infer_domains(query, taxonomy)
    project_context = resolve_project_context(brain_root, query, args.project_target, taxonomy)
    project_domains_payload = project_context["domain_signals"] if project_context else []
    routed_domains_payload = merge_domain_payloads(query_domains_payload, project_domains_payload)
    routed_domains = [entry["domain"] for entry in routed_domains_payload]

    gbrain_payload = run_gbrain_lookup(query, args.gbrain_limit, args.gbrain_cmd, args.install_gbrain)
    combined_gbrain_hits = []
    seen_slugs = set()
    for source_name in ("query_hits", "search_hits"):
        for hit in gbrain_payload.get(source_name, []):
            if hit["slug"] in seen_slugs:
                continue
            combined_gbrain_hits.append(hit)
            seen_slugs.add(hit["slug"])

    scored_packs = [
        score_pack(context, query, routed_domains, combined_gbrain_hits, args.docs_per_pack)
        for context in contexts
    ]
    scored_packs = [pack for pack in scored_packs if pack["score"] > 0 or not args.pack_name]
    scored_packs.sort(key=lambda row: row["score"], reverse=True)

    if not scored_packs:
        scored_packs = [
            {
                "pack": context["pack"],
                "pack_root": context["manifest"].get("pack_root"),
                "domains": sorted({item.get("domain", "unclassified") for item in context["items"]}),
                "domain_overlap": [],
                "metadata_hits": [],
                "gbrain_raw_hits": [],
                "score": 0,
            }
            for context in contexts[: args.pack_limit]
        ]

    selected_packs = []
    for pack in scored_packs[: args.pack_limit]:
        context = next(context for context in contexts if context["pack"] == pack["pack"])
        raw_reads = raw_evidence_for_pack(
            context,
            query,
            args.docs_per_pack,
            args.read_lines,
            args.context_radius,
            pack["metadata_hits"],
        )
        selected_packs.append({
            **pack,
            "raw_reads": raw_reads,
        })

    recommended_reads = []
    for pack in selected_packs:
        for raw_read in pack["raw_reads"]:
            recommended_reads.append({
                "pack": pack["pack"],
                "id": raw_read["id"],
                "title": raw_read["title"],
                "domain": raw_read["domain"],
                "date": raw_read.get("date", ""),
                "raw_rel_path": raw_read["raw_rel_path"],
                "score": raw_read["score"],
            })
    recommended_reads.sort(key=lambda row: (row["score"], row.get("date", "")), reverse=True)

    project_memory_review = None
    if args.project_target:
        try:
            project_target = normalize_target(brain_root, args.project_target)
            project_memory_review = build_project_memory_review(
                brain_root=brain_root,
                project_target=project_target,
                query=query,
                routed_domains_payload=routed_domains_payload,
                gbrain_payload=gbrain_payload,
                recommended_reads=recommended_reads,
            )
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
            return 1

    payload = {
        "generated_at": now_iso(),
        "brain_root": str(brain_root),
        "query": query,
        "mode": "project-advisor-consult" if project_context else "advisor-consult",
        "scope": {
            "default_behavior": "advisor-wide",
            "restricted_packs": args.pack_name,
            "registered_pack_count": len(registry.get("packs", [])),
        },
        "project_context": project_context,
        "routed_domains": routed_domains_payload,
        "gbrain": gbrain_payload,
        "selected_packs": selected_packs,
        "recommended_reads": recommended_reads[: max(6, args.pack_limit * args.docs_per_pack)],
        "advisory_path": build_advisory_path(),
        "answer_contract": build_answer_contract(project_context),
        "project_memory_review": project_memory_review,
        "best_practice": [
            "Do not ask the user to choose a pack unless they explicitly want to narrow scope. / 除非用户明确要缩小范围，否则不要先让用户选 pack。",
            "Use summaries and metadata only for routing; final reasoning should use raw evidence. / summary 和 metadata 只用于路由，最终推理应使用原始证据。",
            "Use pack-specific retrieval only as a precision feature, not a required workflow. / pack 级检索只应作为精准模式，不应成为必选流程。",
            "When a consult is attached to a project page, generate candidate project-memory updates first, ask the user for confirmation, then apply them. / 当一次咨询绑定到项目页时，先生成候选更新，询问用户确认，再写回项目记忆。",
            "When a project is in play, treat the project page as the primary frame and the libraries as supporting evidence for a recommendation. / 当涉及具体项目时，把项目页当主上下文，把资料库当成建议的支撑证据。",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
