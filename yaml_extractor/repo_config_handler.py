from __future__ import annotations
import os
import re
import pathlib
import shutil
import subprocess
import time
import stat
from dataclasses import dataclass
from typing import Iterable, List, Optional

import yaml

# ==================== Exceptions ====================

class RepoError(Exception):
    pass

class LayoutError(Exception):
    pass

# ==================== Header template ====================

def make_header_with_ip(ip_or_host: str) -> dict:
    """
    Build the static header, swapping in the provided IP/host for the LLM endpoint.
    """
    endpoint = f"http://{ip_or_host}:11434/api/generate"
    return {
        # === LOF Detection ===
        "enable_lof": True,
        "lof_n_neighbors": 5,
        "lof_contamination": 0.05,
        # === Rolling Window Flood Detection ===
        "enable_rolling_window": True,
        "rolling_window_size": 1000,
        "rolling_window_threshold": 0.7,
        # === LLM Configuration ===
        "enable_llm": True,
        "llm_provider": "ollama",
        "llm_config": {
            "endpoint": endpoint,
            "model": "mistral:instruct",
            "timeout": 60,
        },
    }

# ==================== Utils ====================

def _is_yaml(p: pathlib.Path) -> bool:
    return p.suffix.lower() in (".yml", ".yaml")

def _load_yaml(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}

def _write_yaml(path: pathlib.Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("# AUTO-GENERATED: DO NOT EDIT\n")
        yaml.safe_dump(data, f, sort_keys=False)

def _deep_merge(a, b, array_policy: str = "replace"):
    """
    Deep-merge a <- b (b overrides).
    Dicts merge by key; lists either 'replace' (default) or 'extend'.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, vb in b.items():
            out[k] = _deep_merge(out[k], vb, array_policy) if k in out else vb
        return out
    if isinstance(a, list) and isinstance(b, list):
        return (list(a) + list(b)) if array_policy == "extend" else list(b)
    return b if b is not None else a

def _safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "default")).strip("-")
    return s[:128] or "default"

# ==================== Windows-safe delete ====================

def _robust_rmtree(path: pathlib.Path, retries: int = 6, base_delay: float = 0.2):
    if not path.exists():
        return
    def _onerror(func, p, exc_info):
        try: os.chmod(p, stat.S_IWRITE)
        except Exception: pass
        try: func(p)
        except Exception: pass
    for i in range(retries):
        try:
            shutil.rmtree(path, onerror=_onerror)
            return
        except PermissionError:
            time.sleep(base_delay * (2 ** i))
    shutil.rmtree(path, onerror=_onerror, ignore_errors=True)

# ==================== Clone helper (unique folder) ====================

def _clone_repo(repo_url: str, dest_parent: pathlib.Path, branch: Optional[str]) -> pathlib.Path:
    """
    Clone into a fresh unique subfolder under dest_parent; return the repo root.
    Avoids deleting existing clones to sidestep Windows file locks.
    """
    dest_parent.mkdir(parents=True, exist_ok=True)
    unique = dest_parent / f"_repo_clone_{int(time.time()*1000)}"

    # Try GitPython first (optional), fall back to CLI.
    try:
        import git  # type: ignore
        repo = git.Repo.clone_from(repo_url, unique, depth=1 if not branch else 1)
        try:
            if branch:
                repo.git.checkout(branch)
        finally:
            repo.close()   # important on Windows
        return unique
    except Exception:
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [repo_url, str(unique)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as e:
            raise RepoError("Git not found. Install Git or add GitPython.") from e
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", "ignore") if e.stderr else str(e)
            raise RepoError(f"git clone failed: {stderr}") from e
        return unique

# ==================== Selection & results ====================

def _pick_suffix_files(loganomaly: pathlib.Path, app_name: str) -> tuple[list[pathlib.Path], str]:
    """
    If loganomaly/<appid>/ exists: use its YAMLs; else use YAMLs in loganomaly/ root.
    """
    app_folder = loganomaly / app_name
    if app_folder.exists() and app_folder.is_dir():
        files = sorted([p for p in app_folder.iterdir() if p.is_file() and _is_yaml(p)], key=lambda p: p.name)
        return files, "app_folder"
    files = sorted([p for p in loganomaly.iterdir() if p.is_file() and _is_yaml(p)], key=lambda p: p.name)
    return files, "common_root"

@dataclass
class BuildResult:
    appid: str
    merged: dict
    out_path: pathlib.Path
    suffix_files_used: List[pathlib.Path]
    mode: str  # "app_folder" or "common_root"

# ==================== Core builder ====================

def _build_one_from_clone(
    repo_root: pathlib.Path,
    *,
    app_name: str,
    ip: str,
    tmp_base: pathlib.Path,
    out_base: pathlib.Path,
    array_policy: str,
) -> BuildResult:
    loganomaly = repo_root / "loganomaly"
    if not loganomaly.exists() or not loganomaly.is_dir():
        raise LayoutError(f"Expected folder '{loganomaly}' not found in the repo.")

    suffix_files, mode = _pick_suffix_files(loganomaly, app_name)
    if not suffix_files:
        where = f"loganomaly/{app_name}" if mode == "app_folder" else "loganomaly"
        raise LayoutError(f"No YAML files found in '{where}'.")

    safe = _safe_name(app_name)

    # Copy suffix files to tmp (audit trail)
    tmp_target = tmp_base / safe
    if tmp_target.exists():
        _robust_rmtree(tmp_target)
    tmp_target.mkdir(parents=True, exist_ok=True)

    copied_paths: list[pathlib.Path] = []
    for p in suffix_files:
        dst = tmp_target / p.name
        shutil.copy2(p, dst)
        copied_paths.append(dst)

    # Merge suffix YAMLs
    suffix_merged: dict = {}
    for p in copied_paths:
        suffix_merged = _deep_merge(suffix_merged, _load_yaml(p), array_policy=array_policy)

    # Merge header(ip) <- suffix (suffix overrides)
    header = make_header_with_ip(ip)
    merged = _deep_merge(header, suffix_merged, array_policy=array_policy)
    _force_endpoint_ip(merged, ip)

    # Write final file
    out_base.mkdir(parents=True, exist_ok=True)
    out_path = out_base / f"{safe}.yaml"
    _write_yaml(out_path, merged)

    return BuildResult(
        appid=app_name,
        merged=merged,
        out_path=out_path,
        suffix_files_used=copied_paths,
        mode=mode,
    )

# ==================== Public APIs ====================

def build_configs_from_existing_repo(
    repo_root: pathlib.Path,
    *,
    appids: Optional[Iterable[str]],
    ip: str,
    workdir: os.PathLike = ".",
    tmp_dir: str = "tmp_config",
    out_dir: str = "config",
    array_policy: str = "replace",
    verbose: bool = True,   # <— NEW for visibility
) -> List[BuildResult]:
    repo_root = pathlib.Path(repo_root).resolve()
    wd = pathlib.Path(workdir).resolve()

    # tmp stays under pipeline/
    tmp_base = wd / tmp_dir
    tmp_base.mkdir(parents=True, exist_ok=True)

    # ✅ outputs go to project root (one level up from pipeline/)
    out_base = wd.parent / out_dir
    out_base.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"[build] repo_root = {repo_root}")
        print(f"[build] workdir   = {wd}")
        print(f"[build] tmp_base  = {tmp_base}")
        print(f"[build] out_base  = {out_base}")

    targets = list(appids) if appids else ["default"]
    results: List[BuildResult] = []

    for app_name in targets:
        if verbose:
            print(f"[build] building appid = {app_name}")
        res = _build_one_from_clone(
            repo_root,
            app_name=app_name,
            ip=ip,
            tmp_base=tmp_base,
            out_base=out_base,
            array_policy=array_policy,
        )
        if verbose:
            print(f"[build] wrote => {res.out_path}")
        results.append(res)
    return results

def build_configs_from_repo(
    repo_url: str,
    *,
    appids: Optional[Iterable[str]],
    ip: str,
    branch: Optional[str] = None,
    workdir: os.PathLike = ".",
    tmp_dir: str = "tmp_config",
    out_dir: str = "config",
    array_policy: str = "replace",
    verbose: bool = True
) -> List[BuildResult]:
    """
    Clone once (into a fresh unique dir) and build configs for many app IDs.
    Cleans up the unique clone at the end.
    """
    wd = pathlib.Path(workdir).resolve()
    clone_parent = wd / "_repo_clone"
    tmp_base = wd / tmp_dir
    out_base = wd / out_dir
    tmp_base.mkdir(parents=True, exist_ok=True)
    out_base.mkdir(parents=True, exist_ok=True)
    clone_parent.mkdir(parents=True, exist_ok=True)

    repo_root = _clone_repo(repo_url, clone_parent, branch)
    try:
        return build_configs_from_existing_repo(
            repo_root=repo_root,
            appids=appids,
            ip=ip,
            workdir=workdir,
            tmp_dir=tmp_dir,
            out_dir=out_dir,
            array_policy=array_policy,
            verbose=verbose,     # <— pass through
        )
    finally:
        _robust_rmtree(repo_root)

def build_config_from_repo(
    repo_url: str,
    *,
    appid: Optional[str],
    ip: str,
    branch: Optional[str] = None,
    workdir: os.PathLike = ".",
    tmp_dir: str = "tmp_config",
    out_dir: str = "config",
    array_policy: str = "replace",
) -> BuildResult:
    """
    Single-app convenience wrapper (clones for this one call).
    """
    results = build_configs_from_repo(
        repo_url=repo_url,
        appids=[appid] if appid else None,
        ip=ip,
        branch=branch,
        workdir=workdir,
        tmp_dir=tmp_dir,
        out_dir=out_dir,
        array_policy=array_policy,
    )
    return results[0]


def _force_endpoint_ip(cfg: dict, ip: str) -> None:
    """
    Ensure cfg['llm_config']['endpoint'] uses the given IP/host, regardless of suffix YAML.
    Safe no-op if llm_config is missing.
    """
    if cfg is None:
        return
    llm = cfg.setdefault("llm_config", {})
    llm["endpoint"] = f"http://{ip}:11434/api/generate"
