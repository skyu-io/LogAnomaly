from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

REPO_DEFAULT = "https://github.com/skyu-io/oho-log-anomaly-skyu-gitops-446358f6.git"
DEFAULT_CONFIG_ROOT = "loganomaly/config"

@dataclass(frozen=True)
class CopyResult:
    source_base: Path               # folder we treated as the source root
    destination: Path               # destination folder you requested
    copied_files: List[Path]        # destination file paths actually written
    mode: str                       # "app", "app-like", "app-files", or "common"
    repo_dir: Path                  # where the repo lived (tmp dir if we cloned)

def _run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )

def _clone_repo(repo_url: str, dest: Path) -> None:
    # Clone repo default branch; no branch selection needed.
    args = ["git", "clone", "--depth", "1", repo_url, str(dest)]
    _run(args)

def _is_yaml(p: Path) -> bool:
    return p.suffix.lower() in {".yml", ".yaml"}

def _yaml_files_under(root: Path) -> List[Path]:
    if root.is_file():
        return [root] if _is_yaml(root) else []
    return [p for p in root.rglob("*") if p.is_file() and _is_yaml(p)]

def _copy_yaml_files(sources: List[Path], src_base: Path, dest_dir: Path, overwrite: bool) -> List[Path]:
    copied: List[Path] = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    for sp in sources:
        rel = sp.relative_to(src_base)
        dp = dest_dir / rel
        dp.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not dp.exists():
            shutil.copy2(sp, dp)
        copied.append(dp)
    return copied

def _best_app_match(config_root: Path, app_id: str) -> Tuple[Optional[Path], Optional[str]]:
    """
    Returns the best directory match for the app and a mode label:
      - ("app", exact folder)
      - ("app-like", first folder containing app_id)
      - (None, None) if not found
    """
    exact = config_root / app_id
    if exact.exists() and exact.is_dir():
        return exact, "app"

    low = app_id.lower()
    for sub in sorted([p for p in config_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        if low in sub.name.lower():
            return sub, "app-like"
    return None, None

def _app_files_in_root(config_root: Path, app_id: str) -> List[Path]:
    low = app_id.lower()
    return [p for p in config_root.glob("*.y*ml") if low in p.name.lower()]

def _common_location(config_root: Path) -> Optional[Path]:
    common_dir = config_root / "common"
    if common_dir.exists() and common_dir.is_dir():
        return common_dir
    # fallback: any common*.yml in root
    root_common = [p for p in config_root.glob("common*.y*ml")]
    return config_root if root_common else None

def fetch_yaml_config(
    *,
    destination_config_dir: str | Path,
    app_id: Optional[str] = None,
    repo_url: str = REPO_DEFAULT,
    config_root_rel: str = DEFAULT_CONFIG_ROOT,
    reuse_local_repo: Optional[str | Path] = None,
    overwrite: bool = True,
    clean_destination_first: bool = True,
) -> CopyResult:
    """
    Clone (or reuse) the GitOps repo and copy ONLY YAML files from:
      1) <config_root>/<app_id>        (exact folder)        -> mode="app"
      2) <config_root>/<*app_id*>      (contains folder)     -> mode="app-like"
      3) <config_root>/*app_id*.yml    (root YAML files)     -> mode="app-files"
      4) <config_root>/common/**.yml or <config_root>/common*.yml -> mode="common"

    - Always uses the repo's default branch.
    - Never copies non-YAML files.
    """
    tmp_dir: Optional[Path] = None
    try:
        if reuse_local_repo:
            repo_dir = Path(reuse_local_repo).resolve()
        else:
            tmp_dir = Path(tempfile.mkdtemp(prefix="gitops_yaml_"))
            _clone_repo(repo_url, tmp_dir)
            repo_dir = tmp_dir

        config_root = (repo_dir / config_root_rel).resolve()
        if not config_root.exists():
            raise FileNotFoundError(f"Config root not found: {config_root}")

        chosen_base: Optional[Path] = None
        mode: Optional[str] = None
        sources: List[Path] = []

        if app_id:
            chosen_base, mode = _best_app_match(config_root, app_id)
            if chosen_base:
                sources = _yaml_files_under(chosen_base)
            else:
                files = _app_files_in_root(config_root, app_id)
                if files:
                    chosen_base = config_root
                    mode = "app-files"
                    sources = files

        if not sources:
            # Fallback: common
            common_base = _common_location(config_root)
            if not common_base:
                raise FileNotFoundError(f"No app-specific or common YAML found under {config_root}")

            if common_base.name == "common":
                chosen_base = common_base
                mode = "common"
                sources = _yaml_files_under(common_base)
            else:
                chosen_base = config_root
                mode = "common"
                sources = [p for p in config_root.glob("common*.y*ml")]

        if not sources:
            raise FileNotFoundError("Discovered a base but found no YAML files to copy.")

        dest = Path(destination_config_dir).resolve()
        if clean_destination_first and dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

        copied = _copy_yaml_files(sources, chosen_base, dest, overwrite=overwrite)

        return CopyResult(
            source_base=chosen_base,
            destination=dest,
            copied_files=copied,
            mode=mode or "unknown",
            repo_dir=repo_dir,
        )

    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
