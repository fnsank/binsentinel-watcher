import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from watcher.scoop import get_changed_packages, get_head_sha


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {"last_sha": None, "packages": {}}
    return json.loads(state_file.read_text())


def save_state(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2))


def find_new_versions(known: dict[str, str], current: dict[str, str]) -> dict[str, str]:
    return {pkg: ver for pkg, ver in current.items() if known.get(pkg) != ver}


def write_task_file(pending_dir: Path, package: str, version: str, bucket: str) -> None:
    task = {
        "package": package,
        "version": version,
        "bucket": bucket,
        "manifest_url": (
            f"https://raw.githubusercontent.com/ScoopInstaller/Main"
            f"/master/bucket/{package}.json"
        ),
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    (pending_dir / f"{package}__{version}.json").write_text(json.dumps(task, indent=2))


def run(meta_repo_path: str, token: str) -> None:
    meta = Path(meta_repo_path)
    state_file = meta / "state.json"
    pending_dir = meta / "queue" / "pending"

    state = load_state(state_file)
    last_sha = state.get("last_sha")
    known = state.get("packages", {})

    head_sha = get_head_sha(token)

    if last_sha is None:
        print("首次运行：记录 HEAD SHA，本次不创建任务。")
        save_state(state_file, {"last_sha": head_sha, "packages": {}})
        return

    if last_sha == head_sha:
        print("自上次运行以来无变更。")
        return

    changed = get_changed_packages(last_sha, head_sha, token)
    new_versions = find_new_versions(known, changed)

    for pkg, ver in new_versions.items():
        write_task_file(pending_dir, pkg, ver, "main")
        known[pkg] = ver
        print(f"已入队：{pkg}@{ver}")

    save_state(state_file, {"last_sha": head_sha, "packages": known})
    print(f"完成。共入队 {len(new_versions)} 个任务。")


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN", "")
    if len(sys.argv) != 2 or not token:
        print("用法：GITHUB_TOKEN=<pat> python -m watcher.check_updates <元数据仓库路径>")
        sys.exit(1)
    run(sys.argv[1], token)

