#!/usr/bin/env python3
"""Smart ingest entrypoint for new corpora."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import resolve_brain_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a new corpus with minimal user input by inferring pack identity and format."
    )
    parser.add_argument("--brain-root")
    parser.add_argument("--source", required=True, help="File or directory containing the new corpus.")
    parser.add_argument("--pack-name", help="Optional explicit pack name.")
    parser.add_argument("--copy-raw", action="store_true")
    parser.add_argument("--gbrain-cmd", help="Override gbrain command, e.g. 'gbrain' or 'bun run src/cli.ts'.")
    parser.add_argument(
        "--install-gbrain",
        action="store_true",
        help="If gbrain is missing, try installing it with bun during refresh.",
    )
    parser.add_argument("--no-sync-gbrain", action="store_true")
    return parser.parse_args()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "library-pack"


def load_registry(brain_root: Path) -> dict[str, Any]:
    registry_path = brain_root / "sources" / "libraries" / "registry.json"
    if not registry_path.exists():
        return {"packs": []}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def detect_format(source: Path) -> tuple[str, Path | None]:
    if source.is_dir():
        index_file = source / "references" / "01-start-here" / "index.json"
        if index_file.exists():
            return "lenny-index", index_file
    return "directory-markdown", None


def infer_pack_name(source: Path, fmt: str) -> str:
    if fmt == "lenny-index":
        lower = source.name.lower()
        if "lenny" in lower:
            return "lenny"
    basis = source.stem if source.is_file() else source.name
    return slugify(basis)


def resolve_existing_pack(registry: dict[str, Any], source: Path, suggested_pack: str) -> str | None:
    source_resolved = source.resolve()
    for pack in registry.get("packs", []):
        if pack.get("name") == suggested_pack:
            return suggested_pack
        manifest_path = pack.get("manifest_path")
        if not manifest_path:
            continue
        manifest_file = Path(manifest_path)
        if not manifest_file.exists():
            continue
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        source_root = manifest.get("source_root")
        raw_root = manifest.get("raw_root")
        if source_root and Path(source_root).resolve() == source_resolved:
            return pack["name"]
        if raw_root and Path(raw_root).resolve() == source_resolved:
            return pack["name"]
    return None


def main() -> int:
    args = parse_args()
    try:
        brain_root = resolve_brain_root(args.brain_root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        print(f"Source not found: {source}", file=sys.stderr)
        return 1

    fmt, index_file = detect_format(source)
    inferred_pack = args.pack_name or infer_pack_name(source, fmt)
    registry = load_registry(brain_root)
    matched_pack = resolve_existing_pack(registry, source, inferred_pack)
    pack_name = matched_pack or inferred_pack

    register_script = Path(__file__).with_name("register_library_pack.py")
    command = [
        sys.executable,
        str(register_script),
        "--brain-root",
        str(brain_root),
        "--pack-name",
        pack_name,
        "--source-root",
        str(source),
        "--format",
        fmt,
    ]
    if index_file is not None:
        command.extend(["--index-file", str(index_file)])
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

    payload = json.loads(completed.stdout)
    wrapper_payload = {
        "action": "updated-existing-pack" if matched_pack else "created-new-pack",
        "pack_name": pack_name,
        "source": str(source),
        "detected_format": fmt,
        "details": payload,
    }
    print(json.dumps(wrapper_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
