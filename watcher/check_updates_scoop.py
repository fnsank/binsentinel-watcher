import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from watcher.scoop import get_changed_packages, get_head_sha

SOURCE_KEY = "scoop-main"
TASK_SOURCE = "scoop"


def _empty_source_state() -> dict:
    return {"last_sha": None, "packages": {}}


def _default_state() -> dict:
    return {
        "sources": {
            SOURCE_KEY: _empty_source_state(),
            "winget": _empty_source_state(),
        }
    }


def _normalize_state(state: dict | None) -> dict:
    if not state:
        return _default_state()

    if "sources" in state:
        normalized = _default_state()
        for source_key, source_state in state.get("sources", {}).items():
            if not isinstance(source_state, dict):
                continue
            normalized["sources"][source_key] = {
                "last_sha": source_state.get("last_sha"),
                "packages": dict(source_state.get("packages", {})),
            }
        return normalized

    return {
        "sources": {
            SOURCE_KEY: {
                "last_sha": state.get("last_sha"),
                "packages": dict(state.get("packages", {})),
            },
            "winget": _empty_source_state(),
        }
    }


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return _default_state()
    return _normalize_state(json.loads(state_file.read_text()))


def save_state(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(_normalize_state(state), indent=2))


def find_new_versions(known: dict[str, str], current: dict[str, str]) -> dict[str, str]:
    return {pkg: ver for pkg, ver in current.items() if known.get(pkg) != ver}


def write_task_file(pending_dir: Path, package: str, version: str, bucket: str, sha: str) -> None:
    task = {
        "source": TASK_SOURCE,
        "package": package,
        "version": version,
        "bucket": bucket,
        "manifest_url": (
            f"https://raw.githubusercontent.com/ScoopInstaller/Main"
            f"/{sha}/bucket/{package}.json"
        ),
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    (pending_dir / f"{package}__{version}.json").write_text(json.dumps(task, indent=2))


def run(meta_repo_path: str, token: str) -> None:
    meta = Path(meta_repo_path)
    state_file = meta / "state.json"
    pending_dir = meta / "queue" / "pending"

    state = load_state(state_file)
    source_state = state["sources"][SOURCE_KEY]
    last_sha = source_state.get("last_sha")
    known = dict(source_state.get("packages", {}))

    head_sha = get_head_sha(token)

    if last_sha is None:
        print("首次运行：记录 HEAD SHA，本次不创建任务。")
        source_state["last_sha"] = head_sha
        source_state["packages"] = {}
        save_state(state_file, state)
        return

    if last_sha == head_sha:
        print("自上次运行以来无变更。")
        return

    changed = get_changed_packages(last_sha, head_sha, token)
    new_versions = find_new_versions(known, changed)

    for pkg, ver in new_versions.items():
        write_task_file(pending_dir, pkg, ver, "main", head_sha)
        known[pkg] = ver
        print(f"已入队：{pkg}@{ver}")

    source_state["last_sha"] = head_sha
    source_state["packages"] = known
    save_state(state_file, state)
    print(f"完成。共入队 {len(new_versions)} 个任务。")


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN", "")
    if len(sys.argv) != 2 or not token:
        print("用法：GITHUB_TOKEN=<pat> python -m watcher.check_updates_scoop <元数据仓库路径>")
        sys.exit(1)
    run(sys.argv[1], token)
