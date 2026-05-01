import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

RAW_BASE_URL = "https://raw.githubusercontent.com/microsoft/winget-pkgs"


def is_main_manifest(path: Path) -> bool:
    if path.suffix.lower() != ".yaml":
        return False
    name = path.name
    if name.endswith(".installer.yaml"):
        return False
    if ".locale." in name:
        return False
    return True


def load_existing_task_keys(meta_repo_path: Path) -> set[str]:
    existing: set[str] = set()
    for subdir in ("pending", "processing", "done"):
        queue_dir = meta_repo_path / "queue" / subdir
        if not queue_dir.exists():
            continue
        for task_file in queue_dir.glob("*.json"):
            existing.add(task_file.stem)
    return existing


def collect_version_dirs(package_root: Path) -> list[Path]:
    if not package_root.exists():
        raise FileNotFoundError(f"manifest root not found: {package_root}")

    if package_root.is_dir() and any(is_main_manifest(path) for path in package_root.glob("*.yaml")):
        return [package_root]

    version_dirs = [path for path in package_root.iterdir() if path.is_dir()]
    return sorted(version_dirs, key=lambda path: path.name)


def find_main_manifest(version_dir: Path) -> Path | None:
    manifests = [path for path in version_dir.glob("*.yaml") if is_main_manifest(path)]
    if not manifests:
        return None
    manifests.sort(key=lambda path: path.name)
    return manifests[0]


def write_task_file(pending_dir: Path, package_id: str, version: str, manifest_path: str, sha: str) -> None:
    task = {
        "source": "winget",
        "package": package_id,
        "version": version,
        "manifest_url": f"{RAW_BASE_URL}/{sha}/{manifest_path}",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    (pending_dir / f"{package_id}__{version}.json").write_text(
        json.dumps(task, indent=2),
        encoding="utf-8",
    )


def queue_manifest_root(meta_repo_path: Path, winget_repo_path: Path, manifest_root: str, sha: str) -> int:
    package_root = winget_repo_path / Path(manifest_root)
    pending_dir = meta_repo_path / "queue" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    existing = load_existing_task_keys(meta_repo_path)
    queued = 0

    for version_dir in collect_version_dirs(package_root):
        manifest = find_main_manifest(version_dir)
        if manifest is None:
            continue

        package_id = manifest.stem
        version = version_dir.name
        task_key = f"{package_id}__{version}"
        if task_key in existing:
            print(f"跳过已存在任务：{task_key}")
            continue

        write_task_file(
            pending_dir,
            package_id,
            version,
            manifest.relative_to(winget_repo_path).as_posix(),
            sha,
        )
        existing.add(task_key)
        queued += 1
        print(f"已入队：{task_key}")

    print(f"完成。共新增 {queued} 个 winget 任务。")
    return queued


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue tasks from a specific winget manifest directory.")
    parser.add_argument("meta_repo_path")
    parser.add_argument("--winget-repo-path", required=True)
    parser.add_argument("--manifest-root", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()

    queue_manifest_root(
        Path(args.meta_repo_path),
        Path(args.winget_repo_path),
        args.manifest_root,
        args.sha,
    )


if __name__ == "__main__":
    main()
