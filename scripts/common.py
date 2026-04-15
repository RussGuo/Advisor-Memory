#!/usr/bin/env python3
"""Shared helpers for advisor-memory scripts."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


CONFIG_PATH = Path.home() / ".advisor-memory" / "config.json"
GBRAIN_CONFIG_PATH = Path.home() / ".gbrain" / "config.json"
PACK_SYSTEM_DIRNAME = "_system"


def load_advisor_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_gbrain_config() -> dict[str, Any]:
    if not GBRAIN_CONFIG_PATH.exists():
        return {}
    try:
        payload = json.loads(GBRAIN_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_brain_root(raw_brain_root: str | None) -> Path:
    candidate = raw_brain_root or os.getenv("ADVISOR_BRAIN_ROOT") or load_advisor_config().get("brain_root")
    if not candidate:
        raise ValueError(
            "Missing brain root. Pass --brain-root, set ADVISOR_BRAIN_ROOT, "
            "or write ~/.advisor-memory/config.json with {\"brain_root\": \"/path/to/brain\"}."
        )
    return Path(str(candidate)).expanduser().resolve()


def split_command(command: str) -> list[str]:
    return shlex.split(command.strip())


def detect_local_gbrain_repo() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "gbrain"
        if (candidate / "src" / "cli.ts").exists():
            return candidate
    return None


def ensure_gbrain_command(
    preferred: str | None = None,
    *,
    install_if_missing: bool = False,
) -> tuple[list[str], Path | None]:
    config = load_advisor_config()

    for candidate in (preferred, os.getenv("ADVISOR_GBRAIN_CMD"), config.get("gbrain_cmd")):
        if not candidate:
            continue
        return split_command(str(candidate)), None

    installed = shutil.which("gbrain")
    if installed:
        return [installed], None

    local_repo = detect_local_gbrain_repo()
    if local_repo is not None and shutil.which("bun"):
        return ["bun", "run", "src/cli.ts"], local_repo

    if install_if_missing and shutil.which("bun"):
        completed = subprocess.run(
            ["bun", "add", "-g", "github:garrytan/gbrain"],
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            installed = shutil.which("gbrain")
            if installed:
                return [installed], None
        raise FileNotFoundError(
            "Failed to install gbrain via bun. "
            f"stdout={completed.stdout.strip()!r} stderr={completed.stderr.strip()!r}"
        )

    raise FileNotFoundError(
        "gbrain command not found. Install with `bun add -g github:garrytan/gbrain`, "
        "or set ADVISOR_GBRAIN_CMD / ~/.advisor-memory/config.json."
    )


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, cwd=str(cwd) if cwd else None)


def has_embedding_credentials() -> bool:
    if os.getenv("OPENAI_API_KEY") or os.getenv("GBRAIN_OPENAI_API_KEY"):
        return True
    return bool(load_gbrain_config().get("openai_api_key"))


def pack_system_root(pack_root: Path) -> Path:
    return pack_root / PACK_SYSTEM_DIRNAME


def pack_manifest_path(pack_root: Path) -> Path:
    new_path = pack_system_root(pack_root) / "manifest.json"
    legacy_path = pack_root / "manifest.json"
    return new_path if new_path.exists() else legacy_path


def pack_indexes_root(pack_root: Path) -> Path:
    new_root = pack_system_root(pack_root) / "indexes"
    legacy_root = pack_root / "indexes"
    return new_root if new_root.exists() else legacy_root


def pack_summaries_root(pack_root: Path) -> Path:
    new_root = pack_system_root(pack_root) / "summaries"
    legacy_root = pack_root / "summaries"
    return new_root if new_root.exists() else legacy_root


def pack_file_summaries_root(pack_root: Path) -> Path:
    return pack_summaries_root(pack_root) / "file-level"


def pack_theme_summaries_root(pack_root: Path) -> Path:
    return pack_summaries_root(pack_root) / "theme-level"


def pack_domain_suggestions_path(pack_root: Path) -> Path:
    new_path = pack_system_root(pack_root) / "domain_suggestions.json"
    legacy_path = pack_root / "domain_suggestions.json"
    return new_path if new_path.exists() else legacy_path


def pack_human_index_path(pack_root: Path) -> Path:
    return pack_root / "index.md"


IMPORT_SKIP_DIRS = {"summaries", "indexes", "inbox", "__pycache__"}


def _collect_importable_paths(brain_root: Path) -> list[Path]:
    """Return relative directories that should be imported into GBrain.

    Strategy: keep the original brain-root-relative path namespace intact
    (e.g. `sources/libraries/<pack>/raw/...`) while skipping routing artifacts
    such as `summaries/` and `indexes/`.
    """
    importable: list[Path] = []
    for child in sorted(brain_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in IMPORT_SKIP_DIRS:
            continue
        if child.name == "sources":
            # Under sources/libraries/<pack>/raw — import only raw dirs
            libraries_root = child / "libraries"
            if libraries_root.exists():
                for pack_dir in sorted(libraries_root.iterdir()):
                    if not pack_dir.is_dir():
                        continue
                    raw_dir = pack_dir / "raw"
                    if raw_dir.exists():
                        importable.append(raw_dir.relative_to(brain_root))
            continue
        importable.append(child.relative_to(brain_root))
    return importable


def _build_import_staging_tree(brain_root: Path, importable_paths: list[Path]) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    staging_dir = tempfile.TemporaryDirectory(prefix="advisor-memory-gbrain-")
    staging_root = Path(staging_dir.name)

    for relative_path in importable_paths:
        source = brain_root / relative_path
        target = staging_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            continue
        target.symlink_to(source, target_is_directory=True)
    return staging_dir, staging_root


def refresh_gbrain(
    brain_root: Path,
    *,
    preferred_gbrain_cmd: str | None = None,
    install_if_missing: bool = False,
) -> dict[str, Any]:
    command_prefix, command_cwd = ensure_gbrain_command(
        preferred_gbrain_cmd,
        install_if_missing=install_if_missing,
    )

    is_git_repo = (brain_root / ".git").exists()
    if is_git_repo:
        refresh_commands = [
            command_prefix + [
                "sync",
                "--repo",
                str(brain_root),
                "--no-pull",
                "--no-embed",
            ]
        ]
        refresh_mode = "sync"
        imported_paths = [str(brain_root)]
    else:
        importable_paths = _collect_importable_paths(brain_root)
        imported_paths = [path.as_posix() for path in importable_paths]
        if importable_paths:
            staging_dir, staging_root = _build_import_staging_tree(brain_root, importable_paths)
            refresh_commands = [command_prefix + ["import", str(staging_root), "--no-embed"]]
        else:
            refresh_commands = [command_prefix + ["import", str(brain_root), "--no-embed"]]
        refresh_mode = "import"

    refresh_stdout_parts: list[str] = []
    try:
        for refresh_command in refresh_commands:
            refresh_result = run_command(refresh_command, cwd=command_cwd)
            if refresh_result.returncode != 0:
                raise RuntimeError(
                    f"gbrain {refresh_mode} failed for {brain_root}: "
                    f"{(refresh_result.stderr or refresh_result.stdout).strip()}"
                )
            if refresh_result.stdout.strip():
                refresh_stdout_parts.append(refresh_result.stdout.strip())
    finally:
        if not is_git_repo and "staging_dir" in locals():
            staging_dir.cleanup()

    embed_command = command_prefix + ["embed", "--stale"]
    embed_warning = None
    embed_stdout = ""
    if has_embedding_credentials():
        embed_result = run_command(embed_command, cwd=command_cwd)
        embed_stdout = embed_result.stdout.strip()
        if embed_result.returncode != 0:
            embed_warning = (
                f"gbrain embed failed for {brain_root}: "
                f"{(embed_result.stderr or embed_result.stdout).strip()}"
            )
    else:
        embed_warning = (
            "Skipped gbrain embed --stale because no OPENAI_API_KEY or "
            "~/.gbrain/config.json openai_api_key was found."
        )

    return {
        "mode": refresh_mode,
        "commands": [cmd for cmd in refresh_commands],
        "import_scope": imported_paths,
        "embed_command": embed_command,
        "refresh_stdout": "\n".join(refresh_stdout_parts),
        "embed_stdout": embed_stdout,
        "embed_warning": embed_warning,
    }
