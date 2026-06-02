"""SHA-256 manifest for frozen OOS reproducibility (plan §0.10)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(repo: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return None


def build_manifest(
    repo_root: Path,
    artifact_paths: list[Path],
    config_paths: list[Path],
) -> dict:
    repo_root = repo_root.resolve()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head(repo_root),
        "configs": {str(p.relative_to(repo_root)): _sha256(p) for p in config_paths if p.exists()},
        "artifacts": {str(p.relative_to(repo_root)): _sha256(p) for p in artifact_paths if p.exists()},
    }


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
