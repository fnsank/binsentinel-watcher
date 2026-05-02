import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from watcher.check_updates_scoop import find_new_versions, load_state, save_state
from watcher.winget import extract_default_locale, extract_package_name, get_changed_package_details, get_head_sha

SOURCE_KEY = "winget"
TASK_SOURCE = "winget"
RAW_BASE_URL = "https://raw.githubusercontent.com/microsoft/winget-pkgs"


def _fetch_package_name(manifest_url: str, token: str) -> str | None:
    headers = {"Authorization": f"token {token}", "Accept": "text/plain"}
    try:
        resp = requests.get(manifest_url, headers=headers, timeout=10)
        if not resp.ok:
            return None
        name = extract_package_name(resp.text)
        if name:
            return name
        # Multi-file manifest: PackageName is in the defaultLocale file, not the version file.
        locale = extract_default_locale(resp.text)
        if not locale or not manifest_url.endswith(".yaml"):
            return None
        locale_url = manifest_url[:-5] + f".locale.{locale}.yaml"
        resp2 = requests.get(locale_url, headers=headers, timeout=10)
        if resp2.ok:
            return extract_package_name(resp2.text)
    except Exception:
        pass
    return None


def write_task_file(
    pending_dir: Path,
    package: str,
    version: str,
    manifest_path: str,
    sha: str,
    name: str | None = None,
) -> None:
    task = {
        "source": TASK_SOURCE,
        "package": package,
        "version": version,
        "manifest_url": f"{RAW_BASE_URL}/{sha}/{manifest_path}",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    if name:
        task["name"] = name
    (pending_dir / f"{package}__{version}.json").write_text(
        json.dumps(task, indent=2),
        encoding="utf-8",
    )


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
        print("首次运行：记录 winget HEAD SHA，本次不创建任务。")
        source_state["last_sha"] = head_sha
        source_state["packages"] = {}
        save_state(state_file, state)
        return

    if last_sha == head_sha:
        print("winget 自上次运行以来无变更。")
        return

    changed = get_changed_package_details(last_sha, head_sha, token)
    new_versions = find_new_versions(
        known,
        {package_id: detail["version"] for package_id, detail in changed.items()},
    )

    for package_id, version in new_versions.items():
        manifest_url = f"{RAW_BASE_URL}/{head_sha}/{changed[package_id]['path']}"
        name = _fetch_package_name(manifest_url, token)
        write_task_file(pending_dir, package_id, version, changed[package_id]["path"], head_sha, name=name)
        known[package_id] = version
        print(f"已入队：{package_id}@{version}")

    source_state["last_sha"] = head_sha
    source_state["packages"] = known
    save_state(state_file, state)
    print(f"完成。winget 共入队 {len(new_versions)} 个任务。")


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN", "")
    if len(sys.argv) != 2 or not token:
        print("用法：GITHUB_TOKEN=<pat> python -m watcher.check_updates_winget <元数据仓库路径>")
        sys.exit(1)
    run(sys.argv[1], token)
