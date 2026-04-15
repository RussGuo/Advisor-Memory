#!/usr/bin/env python3
"""Bootstrap a Lenny-first advisor-memory workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import pack_human_index_path, pack_manifest_path, resolve_brain_root


DEFAULT_TAXONOMY = {
    "domains": {
        "product": ["product", "strategy", "design", "pmf", "roadmap", "onboarding", "ux", "b2b", "b2c", "startup", "startups"],
        "growth": ["growth", "go-to-market", "gtm", "activation", "seo", "retention", "acquisition", "conversion", "analytics"],
        "leadership": ["leadership", "career", "management", "manager", "hiring", "culture"],
        "ai": ["ai", "llm", "agents", "agent", "model", "prompt", "evals"],
        "engineering": ["engineering", "developer", "devtools", "architecture", "infra", "infrastructure"],
        "personal": ["life", "philosophy", "personal", "health", "relationships"],
        "unclassified": [],
    }
}

SNIPPET_CONTENT = """# Advisor Memory Operating Rules / 顾问记忆运行规则

- Use `gbrain` as the durable memory substrate. / 用 `gbrain` 作为长期记忆底座。
- No OpenAI embedding key is required for day-one operation. Without it, advisor-memory should still run in a Lenny-style keyword/fulltext/raw mode. / 第一天运行不要求 OpenAI embedding key；没有它时，advisor-memory 也应以 Lenny 风格的 keyword/fulltext/raw 模式正常工作。
- Treat `sources/libraries/` as the registered source-library area, with `lenny/` as the first pack. Each pack should expose a human-facing `index.md`, while machine metadata lives under `_system/`. / 把 `sources/libraries/` 视为已注册资料库区域，`lenny/` 是第一个 pack。每个 pack 都应暴露给人看的 `index.md`，机器元数据则放在 `_system/`。
- When the user gives a new file or folder to absorb, default to `scripts/smart_ingest_library_pack.py`. / 当用户给新文件或文件夹时，默认走 `scripts/smart_ingest_library_pack.py`。
- When the user asks what a registered corpus says, route by domain, use the library map or indexes to find the right files, then open the most relevant raw sources. / 当用户问“这个库怎么说”时，先按领域路由，再用 library map 或 indexes 找文件，最后打开最相关原文。
- For broad advisory questions, default to `scripts/consult_advisor_memory.py` so the system searches GBrain plus the most relevant packs automatically. Do not require special trigger phrases or pack selection first. / 对广义咨询问题，默认使用 `scripts/consult_advisor_memory.py`，让系统自动检索 GBrain 和最相关的 pack。不要要求用户先说特定触发词，也不要要求先选 pack。
- If the user mentions a known project, treat that project page as the primary context and answer with a project decision or recommendation, not a library summary. / 如果用户提到一个已知项目，就把该项目页当成主上下文，输出项目决策或建议，而不是资料摘要。
- If a consult is tied to a project page, generate a project-memory review first, ask the user whether it should be written back, then apply it with `scripts/update_project_memory.py`. / 如果一次咨询绑定到某个项目页，先生成项目记忆候选更新，询问用户是否写回，再用 `scripts/update_project_memory.py` 应用。
- Prefer full raw documents after routing when the context window permits; use summaries for navigation, not as the final evidence layer. / 路由完成后，只要 context 允许，优先读取完整原文；summary 只负责导航，不是最终证据层。
- When a queue item should become durable memory, use `scripts/promote.py` instead of manually copying text between folders. / 当 queue item 需要进入长期记忆时，优先用 `scripts/promote.py`，不要手工复制粘贴。
- Promote only durable, reused, or decision-changing insights into `concepts/`, `projects/`, `people/`, `companies/`, or `ideas/`. / 只把稳定、复用过、或改变决策的洞见提升到长期页面。
- Keep backlinks from durable pages to pack name, source title, and raw file path. / 长期页面必须保留 pack 名、来源标题、原文路径的回链。
- For multi-pack retrieval, prefer `scripts/search_library_pack.py --all-packs`. / 多库联合检索时，优先使用 `scripts/search_library_pack.py --all-packs`。
- After a write batch, refresh GBrain: git-backed brains should run `gbrain sync --repo <brain-root> --no-pull --no-embed`, non-git brains should run `gbrain import <brain-root> --no-embed`, then run `gbrain embed --stale` only when an OpenAI key is configured. / 写入后刷新 GBrain：git brain 用 `sync`，非 git brain 用 `import`；只有在配置了 OpenAI key 时才执行 `gbrain embed --stale`。
- During nightly consolidation, run `scripts/dream_cycle.py --apply` when safe to auto-refresh stale artifacts and emit a promotion queue. / 夜间巩固时，若条件允许，运行 `scripts/dream_cycle.py --apply` 自动修复过期结构并生成待提升队列。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize a brain root and register the Lenny corpus as the first library pack."
    )
    parser.add_argument("--brain-root", help="Target brain root directory to create or update.")
    parser.add_argument("--lenny-root", required=True, help="Local path to the lennys-podcast-newsletter repository.")
    parser.add_argument("--copy-raw", action="store_true", help="Copy raw source files instead of symlinking.")
    parser.add_argument("--gbrain-cmd", help="Override gbrain command, e.g. 'gbrain' or 'bun run src/cli.ts'.")
    parser.add_argument(
        "--install-gbrain",
        action="store_true",
        help="If gbrain is missing, try installing it with bun during refresh.",
    )
    parser.add_argument(
        "--no-sync-gbrain",
        action="store_true",
        help="Skip gbrain import/embed after bootstrapping. Only use this for pack-only mode.",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_working_readme(path: Path) -> None:
    content = """# Working Memory / 工作记忆

Use this area for short-horizon memory.  
这里存放短周期、短时效的工作记忆。

- active topics / 当前活跃话题
- recent conversations / 最近对话
- pending promotions into durable memory / 待提升到长期记忆的内容

Nothing here should remain forever.  
这里的内容不应该永久停留。

Promote durable material into normal brain pages during the dream cycle or periodic consolidation.  
在 dream cycle 或周期性巩固时，把稳定内容提升到长期页面。
"""
    write_text(path, content)


def write_default_taxonomy(path: Path) -> None:
    write_json(path, DEFAULT_TAXONOMY)


def write_harness_snippets(brain_root: Path) -> list[Path]:
    paths = [
        brain_root / "AGENTS.advisor-memory.snippet.md",
        brain_root / "CLAUDE.advisor-memory.snippet.md",
        brain_root / "advisor-memory.instructions.snippet.md",
    ]
    for path in paths:
        write_text(path, SNIPPET_CONTENT)
    return paths


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    lenny_root = Path(args.lenny_root).expanduser().resolve()
    lenny_index_path = lenny_root / "references" / "01-start-here" / "index.json"

    if not lenny_root.exists():
        print(f"Lenny repo not found: {lenny_root}", file=sys.stderr)
        return 1
    if not lenny_index_path.exists():
        print(f"Missing Lenny index: {lenny_index_path}", file=sys.stderr)
        return 1

    ensure_dir(brain_root)
    for rel_path in (
        "people",
        "companies",
        "projects",
        "concepts",
        "ideas",
        "working/active-topics",
        "working/recent-conversations",
        "working/pending-promotions",
        "working/project-memory-reviews",
        "sources/libraries",
        "inbox",
    ):
        ensure_dir(brain_root / rel_path)

    write_working_readme(brain_root / "working" / "README.md")
    taxonomy_path = brain_root / "sources" / "domain_taxonomy.json"
    if not taxonomy_path.exists():
        write_default_taxonomy(taxonomy_path)

    register_script = Path(__file__).with_name("register_library_pack.py")
    command = [
        sys.executable,
        str(register_script),
        "--brain-root",
        str(brain_root),
        "--pack-name",
        "lenny",
        "--source-root",
        str(lenny_root),
        "--format",
        "lenny-index",
        "--index-file",
        str(lenny_index_path),
    ]
    if args.copy_raw:
        command.append("--copy-raw")
    if args.gbrain_cmd:
        command.extend(["--gbrain-cmd", args.gbrain_cmd])
    if args.install_gbrain:
        command.append("--install-gbrain")
    if args.no_sync_gbrain:
        command.append("--no-sync-gbrain")
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout, file=sys.stderr)
        return completed.returncode

    pack_root = brain_root / "sources" / "libraries" / "lenny"
    manifest_path = pack_manifest_path(pack_root)
    manifest = load_json(manifest_path)
    snippet_paths = write_harness_snippets(brain_root)

    print(f"Initialized advisor-memory brain at {brain_root}")
    print(f"Registered Lenny pack with {manifest['item_count']} items")
    print(f"Raw mode: {manifest.get('raw_mode', 'unknown')}")
    print(f"Manifest: {manifest_path}")
    print(f"Library entry / 人类入口: {pack_human_index_path(pack_root)}")
    for path in snippet_paths:
        print(f"Snippet: {path}")
    print(f"Taxonomy: {taxonomy_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
