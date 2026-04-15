#!/usr/bin/env python3
"""Register or refresh a library pack inside an advisor-memory brain."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    pack_human_index_path,
    pack_manifest_path,
    pack_system_root,
    refresh_gbrain,
    resolve_brain_root,
)


DEFAULT_TAXONOMY = {
    "domains": {
        "product": ["product", "strategy", "design", "pmf", "roadmap", "b2b", "b2c", "startup", "startups"],
        "growth": ["growth", "go-to-market", "gtm", "seo", "retention", "acquisition", "conversion", "analytics"],
        "leadership": ["leadership", "career", "management", "manager", "hiring", "culture"],
        "ai": ["ai", "llm", "agents", "agent", "model", "prompt", "evals"],
        "engineering": ["engineering", "developer", "devtools", "architecture", "infra", "infrastructure"],
        "personal": ["life", "philosophy", "personal", "health", "relationships"],
        "unclassified": [],
    }
}

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "about", "your",
    "their", "them", "they", "have", "will", "more", "less", "over", "under",
    "just", "than", "what", "when", "where", "which", "while", "part", "guide",
    "interview", "interviews", "podcast", "podcasts", "newsletter", "newsletters",
    "episode", "episodes", "conversation", "conversations", "talk", "talks",
    "product", "growth", "leadership", "engineering", "personal", "document",
    "week", "month", "year", "day", "today", "taking", "skipping", "off",
    "next", "back", "organization", "using", "update", "updates",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a corpus as a library pack.")
    parser.add_argument("--brain-root")
    parser.add_argument("--pack-name", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument(
        "--format",
        choices=["lenny-index", "directory-markdown"],
        default="directory-markdown",
        help="How to interpret the source corpus.",
    )
    parser.add_argument("--index-file", help="Optional metadata index file for lenny-index or similar formats.")
    parser.add_argument("--copy-raw", action="store_true", help="Copy raw files instead of symlinking.")
    parser.add_argument("--gbrain-cmd", help="Override gbrain command, e.g. 'gbrain' or 'bun run src/cli.ts'.")
    parser.add_argument(
        "--install-gbrain",
        action="store_true",
        help="If gbrain is missing, try installing it with bun during refresh.",
    )
    parser.add_argument(
        "--no-sync-gbrain",
        action="store_true",
        help="Skip gbrain import/sync and embed after pack registration.",
    )
    parser.add_argument(
        "--new-domain",
        action="append",
        default=[],
        help="Add a new domain in the form name=keyword1,keyword2",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "library-pack"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def system_manifest_path(pack_root: Path) -> Path:
    return pack_system_root(pack_root) / "manifest.json"


def system_indexes_root(pack_root: Path) -> Path:
    return pack_system_root(pack_root) / "indexes"


def system_summaries_root(pack_root: Path) -> Path:
    return pack_system_root(pack_root) / "summaries"


def system_file_summaries_root(pack_root: Path) -> Path:
    return system_summaries_root(pack_root) / "file-level"


def system_theme_summaries_root(pack_root: Path) -> Path:
    return system_summaries_root(pack_root) / "theme-level"


def system_domain_suggestions_path(pack_root: Path) -> Path:
    return pack_system_root(pack_root) / "domain_suggestions.json"


def cleanup_legacy_generated_artifacts(pack_root: Path) -> None:
    for candidate in (
        pack_root / "manifest.json",
        pack_root / "indexes",
        pack_root / "summaries",
        pack_root / "domain_suggestions.json",
    ):
        if candidate.exists() or candidate.is_symlink():
            remove_path(candidate)


def parse_new_domains(entries: list[str]) -> dict[str, list[str]]:
    domains: dict[str, list[str]] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Invalid --new-domain entry: {entry}")
        name, raw_keywords = entry.split("=", 1)
        keywords = [keyword.strip() for keyword in raw_keywords.split(",") if keyword.strip()]
        domains[name.strip()] = keywords
    return domains


def ensure_taxonomy(brain_root: Path, extra_domains: dict[str, list[str]]) -> dict[str, Any]:
    taxonomy_path = brain_root / "sources" / "domain_taxonomy.json"
    generated_path = brain_root / "sources" / "domain_taxonomy.generated.json"

    base = load_json(taxonomy_path) if taxonomy_path.exists() else json.loads(json.dumps(DEFAULT_TAXONOMY))
    generated = load_json(generated_path) if generated_path.exists() else {"domains": {}}

    domains = json.loads(json.dumps(base.setdefault("domains", {})))
    for name, keywords in generated.get("domains", {}).items():
        existing = set(domains.get(name, []))
        existing.update(keywords)
        domains[name] = sorted(existing)
    for name, keywords in extra_domains.items():
        existing = set(domains.get(name, []))
        existing.update(keywords)
        domains[name] = sorted(existing)
    write_json(taxonomy_path, base)
    return {"domains": domains}


def normalize_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_simple_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    raw_meta, body = parts
    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        yaml = None

    if yaml is not None:
        try:
            loaded = yaml.safe_load(raw_meta[4:])
            if isinstance(loaded, dict):
                normalized: dict[str, Any] = {}
                for key, value in loaded.items():
                    if isinstance(value, list):
                        normalized[str(key)] = [str(item) for item in value]
                    elif value is None:
                        continue
                    else:
                        normalized[str(key)] = str(value)
                return normalized, body
        except Exception:
            pass

    meta: dict[str, Any] = {}
    for line in raw_meta.splitlines()[1:]:
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            raw_items = value[1:-1].strip()
            if raw_items:
                meta[key] = [item.strip().strip('"').strip("'") for item in raw_items.split(",")]
            else:
                meta[key] = []
        else:
            meta[key] = value.strip('"').strip("'")
    return meta, body


def infer_type_from_path(path: Path) -> str:
    lowered = str(path).lower()
    if "podcast" in lowered:
        return "podcast"
    if "newsletter" in lowered:
        return "newsletter"
    if "interview" in lowered:
        return "interview"
    return "document"


def normalize_lenny(index: dict, pack_name: str) -> list[dict]:
    items: list[dict] = []
    for source_key, item_type in (("podcasts", "podcast"), ("newsletters", "newsletter")):
        for item in index.get(source_key, []):
            raw_rel_path = item.get("filename", "")
            stem = Path(raw_rel_path).stem
            items.append(
                {
                    "id": f"{pack_name}:{item_type}:{stem}",
                    "pack": pack_name,
                    "title": item.get("title", stem),
                    "type": item_type,
                    "date": item.get("date", ""),
                    "guest": item.get("guest", ""),
                    "tags": list(item.get("tags", [])),
                    "word_count": item.get("word_count", 0),
                    "raw_rel_path": raw_rel_path,
                    "abstract": item.get("description") or item.get("subtitle") or item.get("title", stem),
                    "description": item.get("description", ""),
                    "subtitle": item.get("subtitle", ""),
                }
            )
    items.sort(key=lambda row: row.get("date", ""), reverse=True)
    return items


def build_directory_item_id(pack_name: str, item_type: str, rel_path: Path) -> str:
    path_signature = hashlib.sha1(rel_path.as_posix().encode("utf-8")).hexdigest()[:10]
    return f"{pack_name}:{item_type}:{rel_path.stem}:{path_signature}"


def normalize_directory(source_root: Path, pack_name: str) -> list[dict]:
    items: list[dict] = []
    seen_content_signatures: set[str] = set()
    if source_root.is_file():
        raw_paths = [source_root]
        rel_base = source_root.parent
    else:
        raw_paths = sorted(source_root.rglob("*.md"))
        rel_base = source_root

    for raw_path in raw_paths:
        rel_path = raw_path.relative_to(rel_base)
        text = raw_path.read_text(encoding="utf-8")
        content_signature = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if content_signature in seen_content_signatures:
            continue
        seen_content_signatures.add(content_signature)
        meta, body = parse_simple_frontmatter(text)
        title = meta.get("title") or raw_path.stem.replace("-", " ").replace("_", " ").strip()
        tags = meta.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        abstract = meta.get("description") or meta.get("subtitle") or next(
            (line.strip() for line in body.splitlines() if line.strip()),
            title,
        )
        item_type = meta.get("type") or infer_type_from_path(rel_path)
        items.append(
            {
                "id": build_directory_item_id(pack_name, item_type, rel_path),
                "pack": pack_name,
                "title": title,
                "type": item_type,
                "date": meta.get("date", ""),
                "guest": meta.get("guest", ""),
                "tags": tags,
                "word_count": len(body.split()),
                "raw_rel_path": rel_path.as_posix(),
                "abstract": abstract,
                "description": meta.get("description", ""),
                "subtitle": meta.get("subtitle", ""),
                }
            )
    if not items:
        raise ValueError(f"No markdown files found under {source_root}")
    items.sort(key=lambda row: row.get("date", ""), reverse=True)
    return items


def assign_domain(item: dict[str, Any], taxonomy: dict[str, Any]) -> str:
    haystack = normalize_phrase(
        " ".join(
        [
            item.get("title", ""),
            item.get("abstract", ""),
            item.get("guest", ""),
            item.get("raw_rel_path", ""),
            " ".join(item.get("tags", [])),
        ]
        )
    )
    best_domain = "unclassified"
    best_score = 0
    for domain, keywords in taxonomy.get("domains", {}).items():
        if domain == "unclassified":
            continue
        score = 0
        padded_haystack = f" {haystack} "
        for keyword in keywords:
            normalized_keyword = normalize_phrase(keyword)
            if not normalized_keyword:
                continue
            if f" {normalized_keyword} " in padded_haystack:
                score += 1
        if score > best_score:
            best_score = score
            best_domain = domain
    return best_domain if best_score > 0 else "unclassified"


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in text.lower().replace("/", " ").replace("-", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum())
        if len(token) < 3 or token in STOPWORDS or any(ch.isdigit() for ch in token):
            continue
        tokens.append(token)
    return tokens


def induce_domains(items: list[dict[str, Any]], taxonomy: dict[str, Any], max_new_domains: int = 3) -> dict[str, list[str]]:
    existing_domains = set(taxonomy.get("domains", {}).keys())
    existing_keywords = {keyword.lower() for values in taxonomy.get("domains", {}).values() for keyword in values}
    unclassified = [item for item in items if item["domain"] == "unclassified"]
    if not unclassified:
        return {}

    candidate_to_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in unclassified:
        signals = set()
        signals.update(tokenize(item.get("title", "")))
        signals.update(tokenize(item.get("abstract", "")))
        signals.update(tokenize(item.get("raw_rel_path", "")))
        signals.update(token.lower() for token in item.get("tags", []))
        for signal in signals:
            if signal in existing_domains or signal in existing_keywords or signal in STOPWORDS:
                continue
            candidate_to_items[signal].append(item)

    threshold = max(2, min(5, len(unclassified) // 4 or 2))
    ranked = sorted(candidate_to_items.items(), key=lambda pair: len(pair[1]), reverse=True)
    new_domains: dict[str, list[str]] = {}
    selected_item_sets: list[set[str]] = []

    for candidate, related_items in ranked:
        if len(related_items) < threshold or len(new_domains) >= max_new_domains:
            continue
        item_set = {item["id"] for item in related_items}
        if any(len(item_set & existing) / max(len(item_set), 1) >= 0.8 for existing in selected_item_sets):
            continue
        keyword_counts = Counter()
        for item in related_items:
            keyword_counts.update(tokenize(item.get("title", "")))
            keyword_counts.update(tokenize(item.get("abstract", "")))
            keyword_counts.update(token.lower() for token in item.get("tags", []))
        keywords = [candidate]
        for keyword, _ in keyword_counts.most_common(10):
            if keyword not in keywords and keyword not in STOPWORDS:
                keywords.append(keyword)
        new_domains[candidate] = keywords[:8]
        selected_item_sets.append(item_set)
    return new_domains


def apply_generated_domains(brain_root: Path, generated_domains: dict[str, list[str]]) -> None:
    generated_path = brain_root / "sources" / "domain_taxonomy.generated.json"
    payload = load_json(generated_path) if generated_path.exists() else {"domains": {}}
    for name, keywords in generated_domains.items():
        existing = set(payload["domains"].get(name, []))
        existing.update(keywords)
        payload["domains"][name] = sorted(existing)
    write_json(generated_path, payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_item_path(raw_source: Path, item: dict[str, Any]) -> Path:
    return raw_source if raw_source.is_file() else raw_source / item["raw_rel_path"]


def item_signature(item: dict[str, Any]) -> str:
    relevant = {
        "title": item.get("title", ""),
        "type": item.get("type", ""),
        "date": item.get("date", ""),
        "guest": item.get("guest", ""),
        "tags": item.get("tags", []),
        "domain": item.get("domain", ""),
        "word_count": item.get("word_count", 0),
        "raw_rel_path": item.get("raw_rel_path", ""),
        "abstract": item.get("abstract", ""),
        "description": item.get("description", ""),
        "subtitle": item.get("subtitle", ""),
    }
    return json.dumps(relevant, ensure_ascii=False, sort_keys=True)


def merge_item_metadata(
    items: list[dict[str, Any]],
    raw_source: Path,
    existing_items: dict[str, dict[str, Any]],
    generated_at: str,
) -> None:
    for item in items:
        source_path = source_item_path(raw_source, item)
        checksum = sha256_file(source_path) if source_path.exists() and source_path.is_file() else ""
        previous = existing_items.get(item["id"])

        item["source_checksum"] = checksum
        item["imported_at"] = previous.get("imported_at", generated_at) if previous else generated_at

        if previous and previous.get("source_checksum") == checksum and item_signature(previous) == item_signature(item):
            item["updated_at"] = previous.get("updated_at", previous.get("imported_at", generated_at))
        else:
            item["updated_at"] = generated_at


def ensure_raw_directory(raw_target: Path, raw_source: Path, copy_raw: bool) -> str:
    if raw_target.is_symlink():
        if raw_target.resolve() == raw_source.resolve():
            return "symlink"
        raise RuntimeError(f"Raw target already points somewhere else: {raw_target}")
    if raw_target.exists() and not raw_target.is_dir():
        raise RuntimeError(f"Raw target is not a directory: {raw_target}")
    if raw_target.exists():
        if copy_raw:
            shutil.copytree(raw_source, raw_target, dirs_exist_ok=True)
            return "copy"
        return "directory"
    if copy_raw:
        shutil.copytree(raw_source, raw_target)
        return "copy"
    raw_target.symlink_to(raw_source.resolve(), target_is_directory=True)
    return "symlink"


def ensure_single_file_raw(raw_target: Path, raw_source: Path, copy_raw: bool) -> str:
    if raw_target.is_symlink():
        raise RuntimeError(f"Expected raw directory for single-file pack, found symlink: {raw_target}")
    ensure_dir(raw_target)

    destination = raw_target / raw_source.name
    for child in raw_target.iterdir():
        if child.name == raw_source.name:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()

    if copy_raw:
        if destination.is_symlink():
            destination.unlink()
        shutil.copy2(raw_source, destination)
        return "copy-file"

    if destination.is_symlink() and destination.resolve() == raw_source.resolve():
        return "symlink-file"
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    destination.symlink_to(raw_source.resolve())
    return "symlink-file"


def ensure_raw(raw_target: Path, raw_source: Path, copy_raw: bool) -> str:
    if raw_source.is_dir():
        return ensure_raw_directory(raw_target, raw_source, copy_raw)
    return ensure_single_file_raw(raw_target, raw_source, copy_raw)


def build_indexes(items: list[dict]) -> dict[str, Any]:
    by_tag: dict[str, list[str]] = defaultdict(list)
    by_entity: dict[str, list[str]] = defaultdict(list)
    by_type: dict[str, list[str]] = defaultdict(list)
    by_domain: dict[str, list[str]] = defaultdict(list)
    by_date: list[dict[str, str]] = []

    for item in items:
        item_id = item["id"]
        by_type[item["type"]].append(item_id)
        by_domain[item["domain"]].append(item_id)
        if item.get("guest"):
            by_entity[item["guest"]].append(item_id)
        for tag in item.get("tags", []):
            by_tag[tag].append(item_id)
        if item.get("date"):
            by_date.append({"id": item_id, "date": item["date"]})

    by_date.sort(key=lambda row: row["date"], reverse=True)
    return {
        "by_date": by_date,
        "by_tag": dict(sorted(by_tag.items(), key=lambda item: item[0].lower())),
        "by_entity": dict(sorted(by_entity.items(), key=lambda item: item[0].lower())),
        "by_type": dict(sorted(by_type.items(), key=lambda item: item[0].lower())),
        "by_domain": dict(sorted(by_domain.items(), key=lambda item: item[0].lower())),
    }


def write_summaries(pack_root: Path, items: list[dict]) -> None:
    file_root = system_file_summaries_root(pack_root)
    theme_root = system_theme_summaries_root(pack_root)
    ensure_dir(file_root)
    ensure_dir(theme_root)
    for item in items:
        escaped_title = item["title"].replace('"', '\\"')
        escaped_guest = item.get("guest", "").replace('"', '\\"')
        summary = f"""---
id: "{item['id']}"
pack: "{item['pack']}"
type: "{item['type']}"
title: "{escaped_title}"
date: "{item.get('date', '')}"
domain: "{item['domain']}"
guest: "{escaped_guest}"
raw_rel_path: "{item['raw_rel_path']}"
tags: {json.dumps(item.get('tags', []), ensure_ascii=False)}
word_count: {item.get('word_count', 0)}
---

# {item['title']}

## Snapshot

- Type: `{item['type']}`
- Domain: `{item['domain']}`
- Date: `{item.get('date', 'unknown')}`
- Guest: `{item.get('guest') or 'n/a'}`
- Raw: `raw/{item['raw_rel_path']}`

## Abstract

{item.get('abstract') or 'No abstract available.'}

## When To Open Raw

- Open the raw file when exact wording, examples, or timestamps matter.
- Cite the raw source path when answering from this item.
"""
        write_text(file_root / f"{item['id'].replace(':', '__')}.md", summary)

    counts = Counter(item["domain"] for item in items)
    top = "\n".join(f"- `{domain}`: {count}" for domain, count in counts.most_common())
    write_text(
        theme_root / "README.md",
        "# Theme-Level Summaries\n\nThis directory is reserved for cross-document summaries.\n\n## Domain Counts\n\n"
        + (top or "- none")
        + "\n",
    )


def write_library_map(pack_root: Path, items: list[dict], indexes: dict[str, Any], generated_domains: dict[str, list[str]]) -> None:
    theme_root = system_theme_summaries_root(pack_root)
    ensure_dir(theme_root)

    def recommendation_score(item: dict[str, Any]) -> tuple[int, int, str]:
        word_count = int(item.get("word_count", 0) or 0)
        title = item.get("title", "").lower()
        low_signal = word_count < 500 or any(token in title for token in ("free", "week off", "announcement", "hiring"))
        return (0 if low_signal else 1, min(word_count, 20000), item.get("date", ""))

    def pick_examples(domain: str, limit: int = 3) -> list[dict]:
        matches = [item for item in items if item["domain"] == domain]
        matches.sort(key=recommendation_score, reverse=True)
        return matches[:limit]

    def pick_recommended_start(limit: int = 10) -> list[dict]:
        chosen: list[dict] = []
        seen_ids: set[str] = set()
        for domain, _ in domain_counts.most_common():
            if domain == "unclassified":
                continue
            for item in pick_examples(domain, limit=2):
                if item["id"] in seen_ids:
                    continue
                chosen.append(item)
                seen_ids.add(item["id"])
                if len(chosen) >= limit:
                    return chosen
        remaining = sorted(items, key=recommendation_score, reverse=True)
        for item in remaining:
            if item["id"] in seen_ids:
                continue
            chosen.append(item)
            seen_ids.add(item["id"])
            if len(chosen) >= limit:
                break
        return chosen[:limit]

    domain_counts = Counter(item["domain"] for item in items)
    tag_counts = Counter()
    guest_counts = Counter()
    for item in items:
        tag_counts.update(item.get("tags", []))
        if item.get("guest"):
            guest_counts[item["guest"]] += 1

    dated_items = [item for item in items if item.get("date")]
    date_range = {
        "latest": max((item["date"] for item in dated_items), default=""),
        "earliest": min((item["date"] for item in dated_items), default=""),
    }
    recommended_start = pick_recommended_start()

    interesting_tags = [
        tag for tag, _ in tag_counts.most_common(20)
        if tag not in {"newsletter", "podcast", "design", "leadership", "strategy"}
    ][:6]
    key_questions = []
    for domain, _ in domain_counts.most_common():
        if domain == "unclassified":
            continue
        key_questions.append(f"这个库里关于 {domain} 最值得先读的内容是什么？")
        if len(key_questions) >= 3:
            break
    for tag in interesting_tags:
        key_questions.append(f"这个库里是怎么讨论 {tag} 的？")
        if len(key_questions) >= 6:
            break

    map_payload = {
        "pack": pack_root.name,
        "generated_at": now_iso(),
        "item_count": len(items),
        "type_counts": {k: len(v) for k, v in indexes.get("by_type", {}).items()},
        "domain_counts": dict(domain_counts),
        "top_tags": tag_counts.most_common(15),
        "top_entities": [entry for entry in guest_counts.most_common(15) if entry[1] > 1],
        "top_guests": guest_counts.most_common(15),
        "date_range": date_range,
        "generated_domains": generated_domains,
        "recommended_start": [
            {
                "id": item["id"],
                "title": item["title"],
                "domain": item["domain"],
                "date": item.get("date", ""),
                "raw_rel_path": item["raw_rel_path"],
            }
            for item in recommended_start
        ],
        "key_questions": key_questions,
        "domain_examples": {
            domain: [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "date": item.get("date", ""),
                    "raw_rel_path": item["raw_rel_path"],
                }
                for item in pick_examples(domain)
            ]
            for domain in domain_counts
        },
    }
    write_json(theme_root / "library-map.json", map_payload)

    domain_lines = []
    for domain, count in domain_counts.most_common():
        domain_lines.append(f"### `{domain}` ({count})")
        examples = pick_examples(domain)
        if examples:
            for item in examples:
                date = item.get("date") or "undated"
                domain_lines.append(f"- [{date}] {item['title']} -> `raw/{item['raw_rel_path']}`")
        else:
            domain_lines.append("- No representative files.")
        domain_lines.append("")

    generated_lines = []
    for domain, keywords in generated_domains.items():
        generated_lines.append(f"- `{domain}`: {', '.join(keywords)}")

    top_tags_md = "\n".join(f"- `{tag}`: {count}" for tag, count in tag_counts.most_common(12)) or "- none"
    repeated_entities = [(entity, count) for entity, count in guest_counts.most_common(12) if count > 1]
    top_entities_md = "\n".join(f"- `{entity}`: {count}" for entity, count in repeated_entities) or "- none"
    top_guests_md = "\n".join(f"- `{entity}`" for entity, _ in guest_counts.most_common(12)) or "- none"
    type_lines = "\n".join(f"- `{type_name}`: {len(item_ids)}" for type_name, item_ids in indexes.get("by_type", {}).items()) or "- none"
    recommended_md = "\n".join(
        f"- [{item.get('date') or 'undated'}] {item['title']} (`{item['domain']}`) -> `raw/{item['raw_rel_path']}`"
        for item in recommended_start
    ) or "- none"
    key_questions_md = "\n".join(f"- {question}" for question in key_questions) or "- none"

    content = f"""# {pack_root.name} Library

This is the human-facing entrypoint for this library pack. Start here to
understand what the pack contains before opening raw files.

## Snapshot

- Pack: `{pack_root.name}`
- Total items: {len(items)}
- Earliest date: `{date_range['earliest'] or 'unknown'}`
- Latest date: `{date_range['latest'] or 'unknown'}`

## Types

{type_lines}

## Top Tags

{top_tags_md}

## Top Entities

{top_entities_md}

## Representative Guests

{top_guests_md}

## Recommended First Reads

{recommended_md}

## Key Entry Questions

{key_questions_md}

## Domains

{chr(10).join(domain_lines).rstrip()}

## Auto-Generated Domains

{chr(10).join(generated_lines) if generated_lines else '- none'}

## How To Use This Map

- Start here to see the rough shape of the library.
- Use the recommended reads as the fastest way to get oriented.
- Use the key questions as natural entry points for asking the system about this pack.
- Then open the representative raw files for the domain you care about.
- Use `search_library_pack.py` for targeted retrieval after you know the shape.
"""
    write_text(theme_root / "library-map.md", content)
    write_text(pack_human_index_path(pack_root), content)


def write_suggestions(pack_root: Path, items: list[dict]) -> None:
    unclassified = [item for item in items if item["domain"] == "unclassified"]
    tag_counts = Counter()
    path_counts = Counter()
    for item in unclassified:
        tag_counts.update(item.get("tags", []))
        first_path = item.get("raw_rel_path", "").split("/", 1)[0]
        if first_path:
            path_counts[first_path] += 1
    payload = {
        "generated_at": now_iso(),
        "unclassified_count": len(unclassified),
        "top_unclassified_tags": tag_counts.most_common(20),
        "top_unclassified_paths": path_counts.most_common(20),
        "sample_ids": [item["id"] for item in unclassified[:20]],
    }
    write_json(system_domain_suggestions_path(pack_root), payload)


def update_registry(brain_root: Path, pack_name: str, pack_root: Path, raw_mode: str, item_count: int) -> None:
    registry_path = brain_root / "sources" / "libraries" / "registry.json"
    registry = {"packs": []}
    if registry_path.exists():
        registry = load_json(registry_path)
    existing_pack = next((pack for pack in registry.get("packs", []) if pack.get("name") == pack_name), None)
    packs = [pack for pack in registry.get("packs", []) if pack.get("name") != pack_name]
    manifest_path = system_manifest_path(pack_root)
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    domains = sorted(
        {
            item.get("domain", "unclassified")
            for item in manifest.get("items", [])
            if item.get("domain")
        }
    )
    packs.append(
        {
            "name": pack_name,
            "kind": "library-pack",
            "pack_root": str(pack_root),
            "manifest_path": str(manifest_path),
            "human_index_path": str(pack_human_index_path(pack_root)),
            "initialized_at": existing_pack.get("initialized_at", now_iso()) if existing_pack else now_iso(),
            "raw_mode": raw_mode,
            "item_count": item_count,
            "domains": domains,
        }
    )
    registry["packs"] = sorted(packs, key=lambda item: item["name"])
    write_json(registry_path, registry)
    write_library_catalog(brain_root, registry)


def write_library_catalog(brain_root: Path, registry: dict[str, Any]) -> None:
    libraries_root = brain_root / "sources" / "libraries"
    ensure_dir(libraries_root)
    lines = [
        "# Libraries",
        "",
        "Human-facing entrypoints for the registered source libraries.",
        "",
    ]
    packs = registry.get("packs", [])
    if not packs:
        lines.append("- No registered packs.")
    else:
        for pack in packs:
            pack_name = str(pack.get("name", "unknown"))
            item_count = pack.get("item_count", 0)
            domains = ", ".join(pack.get("domains", [])[:6]) or "unclassified"
            lines.append(f"- [{pack_name}]({pack_name}/index.md) — {item_count} items — domains: {domains}")
    write_text(libraries_root / "index.md", "\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    source_root = Path(args.source_root).expanduser().resolve()
    pack_name = args.pack_name.strip().lower().replace(" ", "-")
    generated_at = now_iso()

    if not source_root.exists():
        print(f"Source not found: {source_root}", file=sys.stderr)
        return 1

    ensure_dir(brain_root / "sources" / "libraries")
    extra_domains = parse_new_domains(args.new_domain)
    taxonomy = ensure_taxonomy(brain_root, extra_domains)

    try:
        if args.format == "lenny-index":
            index_file = Path(args.index_file).expanduser().resolve() if args.index_file else source_root / "references" / "01-start-here" / "index.json"
            if not index_file.exists():
                print(f"Missing index file: {index_file}", file=sys.stderr)
                return 1
            raw_source = source_root / "references"
            items = normalize_lenny(load_json(index_file), pack_name)
        else:
            raw_source = source_root
            items = normalize_directory(source_root, pack_name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for item in items:
        item["domain"] = assign_domain(item, taxonomy)

    generated_domains = induce_domains(items, taxonomy)
    if generated_domains:
        apply_generated_domains(brain_root, generated_domains)
        taxonomy = ensure_taxonomy(brain_root, extra_domains={})
        for item in items:
            item["domain"] = assign_domain(item, taxonomy)

    pack_root = brain_root / "sources" / "libraries" / pack_name
    ensure_dir(pack_root)
    ensure_dir(pack_system_root(pack_root))
    previous_manifest_path = pack_manifest_path(pack_root)
    previous_manifest = load_json(previous_manifest_path) if previous_manifest_path.exists() else {}
    existing_items = {item["id"]: item for item in previous_manifest.get("items", [])}
    merge_item_metadata(items, raw_source, existing_items, generated_at)
    raw_mode = ensure_raw(pack_root / "raw", raw_source, args.copy_raw)
    indexes = build_indexes(items)

    manifest_path = system_manifest_path(pack_root)
    indexes_root = system_indexes_root(pack_root)
    summaries_root = system_summaries_root(pack_root)
    human_index_path = pack_human_index_path(pack_root)
    manifest = {
        "manifest_version": 1,
        "pack": pack_name,
        "pack_root": str(pack_root),
        "source_root": str(source_root),
        "source_format": args.format,
        "raw_root": str((pack_root / "raw").resolve()),
        "generated_at": generated_at,
        "raw_mode": raw_mode,
        "item_count": len(items),
        "system_root": str(pack_system_root(pack_root)),
        "indexes_root": str(indexes_root),
        "summaries_root": str(summaries_root),
        "library_map_path": str(human_index_path),
        "human_index_path": str(human_index_path),
        "items": items,
    }
    write_json(manifest_path, manifest)
    for name, payload in indexes.items():
        write_json(indexes_root / f"{name}.json", payload)
    write_summaries(pack_root, items)
    write_library_map(pack_root, items, indexes, generated_domains)
    write_suggestions(pack_root, items)
    cleanup_legacy_generated_artifacts(pack_root)
    update_registry(brain_root, pack_name, pack_root, raw_mode, len(items))

    gbrain_refresh = None
    if not args.no_sync_gbrain:
        try:
            gbrain_refresh = refresh_gbrain(
                brain_root,
                preferred_gbrain_cmd=args.gbrain_cmd,
                install_if_missing=args.install_gbrain,
            )
        except (FileNotFoundError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    print(json.dumps({
        "pack": pack_name,
        "item_count": len(items),
        "raw_mode": raw_mode,
        "pack_root": str(pack_root),
        "generated_domains": generated_domains,
        "unclassified": sum(1 for item in items if item["domain"] == "unclassified"),
        "gbrain_refresh": gbrain_refresh,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
