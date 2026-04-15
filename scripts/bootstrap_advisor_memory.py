#!/usr/bin/env python3
"""One-command first-run bootstrap for advisor-memory."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import (
    CONFIG_PATH,
    ensure_gbrain_command,
    load_advisor_config,
    run_command,
    save_advisor_config,
)
from init_lenny_first_memory import (
    ensure_dir,
    write_default_taxonomy,
    write_harness_snippets,
    write_working_readme,
)


DEFAULT_BRAIN_ROOT = Path.home() / "brain"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="First-run bootstrap: install/check gbrain, initialize the brain, write default config, and optionally register Lenny."
    )
    parser.add_argument("--brain-root", help="Target brain root. Defaults to ~/.advisor-memory config, ADVISOR_BRAIN_ROOT, or ~/brain.")
    parser.add_argument("--lenny-root", help="Optional local path to the lennys-podcast-newsletter repository for a Lenny-first bootstrap.")
    parser.add_argument("--copy-raw", action="store_true", help="Copy raw source files instead of symlinking when registering Lenny.")
    parser.add_argument("--gbrain-cmd", help="Override gbrain command, e.g. 'gbrain' or 'bun run src/cli.ts'.")
    parser.add_argument(
        "--install-gbrain",
        action="store_true",
        help="If gbrain is missing, try installing it with bun before bootstrap.",
    )
    parser.add_argument(
        "--no-write-config",
        action="store_true",
        help="Do not write ~/.advisor-memory/config.json with the resolved brain root.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of human-readable text.")
    return parser.parse_args()


def resolve_bootstrap_brain_root(raw_brain_root: str | None) -> Path:
    if raw_brain_root:
        return Path(raw_brain_root).expanduser().resolve()
    if os.getenv("ADVISOR_BRAIN_ROOT"):
        return Path(os.environ["ADVISOR_BRAIN_ROOT"]).expanduser().resolve()
    config = load_advisor_config()
    if config.get("brain_root"):
        return Path(str(config["brain_root"])).expanduser().resolve()
    return DEFAULT_BRAIN_ROOT.expanduser().resolve()


def command_to_string(command_prefix: list[str]) -> str:
    if len(command_prefix) == 1 and Path(command_prefix[0]).name == "gbrain":
        return "gbrain"
    return " ".join(shlex.quote(part) for part in command_prefix)


def persistent_gbrain_cmd(raw_override: str | None, command_prefix: list[str], command_cwd: Path | None) -> str | None:
    if raw_override:
        return raw_override
    if command_cwd is not None:
        return None
    if len(command_prefix) == 1 and Path(command_prefix[0]).name == "gbrain":
        return "gbrain" if shutil.which("gbrain") else command_prefix[0]
    return None


def parse_json_output(result: subprocess.CompletedProcess[str]) -> Any:
    stdout = result.stdout.strip()
    candidates = [stdout]
    if stdout:
        candidates.append(stdout.splitlines()[-1].strip())
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {"raw_stdout": stdout, "raw_stderr": result.stderr.strip()}


def ensure_brain_layout(brain_root: Path) -> dict[str, Any]:
    ensure_dir(brain_root)
    created: list[str] = []
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
        target = brain_root / rel_path
        if not target.exists():
            created.append(rel_path)
        ensure_dir(target)

    write_working_readme(brain_root / "working" / "README.md")
    taxonomy_path = brain_root / "sources" / "domain_taxonomy.json"
    if not taxonomy_path.exists():
        write_default_taxonomy(taxonomy_path)
        created.append("sources/domain_taxonomy.json")

    snippets = write_harness_snippets(brain_root)
    return {
        "brain_root": str(brain_root),
        "created_paths": created,
        "snippet_paths": [str(path) for path in snippets],
        "taxonomy_path": str(taxonomy_path),
    }


def main() -> int:
    args = parse_args()
    brain_root = resolve_bootstrap_brain_root(args.brain_root)

    try:
        command_prefix, command_cwd = ensure_gbrain_command(
            args.gbrain_cmd,
            install_if_missing=args.install_gbrain,
        )
    except FileNotFoundError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(str(exc), file=sys.stderr)
        return 1

    init_result = run_command(command_prefix + ["init", "--pglite", "--json"], cwd=command_cwd)
    if init_result.returncode != 0:
        message = (init_result.stderr or init_result.stdout).strip()
        if args.json:
            print(json.dumps({"error": f"gbrain init failed: {message}"}, ensure_ascii=False, indent=2))
        else:
            print(f"gbrain init failed: {message}", file=sys.stderr)
        return 1

    doctor_result = run_command(command_prefix + ["doctor", "--json"], cwd=command_cwd)
    if doctor_result.returncode != 0:
        message = (doctor_result.stderr or doctor_result.stdout).strip()
        if args.json:
            print(json.dumps({"error": f"gbrain doctor failed: {message}"}, ensure_ascii=False, indent=2))
        else:
            print(f"gbrain doctor failed: {message}", file=sys.stderr)
        return 1

    layout_payload = ensure_brain_layout(brain_root)
    bootstrap_mode = "empty-brain"
    lenny_payload = None
    if args.lenny_root:
        init_script = Path(__file__).with_name("init_lenny_first_memory.py")
        command = [
            sys.executable,
            str(init_script),
            "--brain-root",
            str(brain_root),
            "--lenny-root",
            str(Path(args.lenny_root).expanduser().resolve()),
        ]
        if args.copy_raw:
            command.append("--copy-raw")
        if args.gbrain_cmd:
            command.extend(["--gbrain-cmd", args.gbrain_cmd])
        if args.install_gbrain:
            command.append("--install-gbrain")
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout).strip()
            if args.json:
                print(json.dumps({"error": f"Lenny bootstrap failed: {message}"}, ensure_ascii=False, indent=2))
            else:
                print(f"Lenny bootstrap failed: {message}", file=sys.stderr)
            return completed.returncode
        bootstrap_mode = "lenny-first"
        lenny_payload = {"stdout": completed.stdout.strip()}

    config_payload = None
    if not args.no_write_config:
        merged = load_advisor_config()
        merged["brain_root"] = str(brain_root)
        persistent_cmd = persistent_gbrain_cmd(args.gbrain_cmd, command_prefix, command_cwd)
        if persistent_cmd:
            merged["gbrain_cmd"] = persistent_cmd
        save_advisor_config(merged)
        config_payload = {
            "config_path": str(CONFIG_PATH),
            "brain_root": str(brain_root),
            "gbrain_cmd": merged.get("gbrain_cmd"),
        }

    script_dir = Path(__file__).resolve().parent
    next_steps = {
        "consult": f'python3 {shlex.quote(str(script_dir / "consult_advisor_memory.py"))} "How should we improve onboarding and PMF?"',
        "search_lenny": None if not args.lenny_root else f'python3 {shlex.quote(str(script_dir / "search_library_pack.py"))} --pack-name lenny search "product-market fit" --limit 5',
        "ingest": f"python3 {shlex.quote(str(script_dir / 'smart_ingest_library_pack.py'))} --source /path/to/new-corpus",
    }

    payload = {
        "status": "ok",
        "mode": bootstrap_mode,
        "brain_root": str(brain_root),
        "gbrain": {
            "command": command_to_string(command_prefix),
            "init": parse_json_output(init_result),
            "doctor": parse_json_output(doctor_result),
        },
        "layout": layout_payload,
        "config": config_payload,
        "lenny": lenny_payload,
        "next_steps": next_steps,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("Advisor Memory bootstrap complete.")
    print("Advisor Memory 是一个顾问型分层记忆系统：把长期记忆、项目记忆和外部资料库统一成一个可咨询、可更新、可回溯的共享知识库。")
    print("")
    print(f"Brain root: {brain_root}")
    if config_payload:
        print(f"Default config: {config_payload['config_path']}")
    print(f"GBrain: {payload['gbrain']['command']}")
    print(f"Mode: {bootstrap_mode}")
    print("")
    print("First commands / 第一步建议：")
    print(f"- Broad consult / 顾问咨询: {next_steps['consult']}")
    if next_steps["search_lenny"]:
        print(f"- Search Lenny / 搜 Lenny: {next_steps['search_lenny']}")
    print(f"- Ingest new corpus / 导入新资料: {next_steps['ingest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
