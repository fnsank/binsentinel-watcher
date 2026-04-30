"""Generate historical watcher tasks from Scoop bucket history."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


BUCKET_REPO_URL = "https://github.com/ScoopInstaller/Main.git"
BUCKET_NAME = "main"
GITHUB_RAW = "https://raw.githubusercontent.com/ScoopInstaller/Main"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def ensure_bucket_repo(cache_dir: Path) -> Path:
    if (cache_dir / ".git").exists():
        print(f"Updating local bucket cache: {cache_dir}")
        git(cache_dir, "pull", "--ff-only")
    else:
        print(f"Cloning ScoopInstaller/Main into {cache_dir} ...")
        subprocess.run(
            ["git", "clone", "--filter=blob:none", BUCKET_REPO_URL, str(cache_dir)],
            check=True,
        )
    return cache_dir


def list_packages(bucket_repo: Path) -> list[str]:
    bucket_dir = bucket_repo / "bucket"
    return [path.stem for path in sorted(bucket_dir.glob("*.json"))]


def get_commit_log(
    bucket_repo: Path,
    pkg: str,
    since: datetime | None,
    until: datetime | None,
) -> list[tuple[str, datetime]]:
    args = ["log", "--follow", "--pretty=format:%H %aI"]
    if since:
        args.append(f"--after={since.date().isoformat()}")
    if until:
        args.append(f"--before={until.date().isoformat()}")
    args.extend(["--", f"bucket/{pkg}.json"])

    output = git(bucket_repo, *args).strip()
    if not output:
        return []

    commits = []
    for line in output.splitlines():
        sha, iso_timestamp = line.split(" ", 1)
        commits.append((sha, datetime.fromisoformat(iso_timestamp)))

    commits.reverse()
    return commits


def get_version_at(bucket_repo: Path, sha: str, pkg: str) -> str | None:
    try:
        raw = git(bucket_repo, "show", f"{sha}:bucket/{pkg}.json")
    except RuntimeError:
        return None

    try:
        return str(json.loads(raw).get("version", "")).strip() or None
    except json.JSONDecodeError:
        return None


def load_existing_tasks(meta: Path) -> set[str]:
    keys: set[str] = set()
    for subdir in ("pending", "processing", "done"):
        directory = meta / "queue" / subdir
        if not directory.exists():
            continue
        for task_file in directory.glob("*.json"):
            keys.add(task_file.stem)
    return keys


def write_task(pending_dir: Path, pkg: str, version: str, sha: str) -> None:
    task = {
        "package": pkg,
        "version": version,
        "bucket": BUCKET_NAME,
        "manifest_url": f"{GITHUB_RAW}/{sha}/bucket/{pkg}.json",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    (pending_dir / f"{pkg}__{version}.json").write_text(json.dumps(task, indent=2))


def run(
    meta_repo_path: str,
    since_str: str | None,
    until_str: str | None,
    bucket_cache_str: str,
) -> None:
    meta = Path(meta_repo_path)
    pending_dir = meta / "queue" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    since = (
        datetime.fromisoformat(since_str).replace(tzinfo=timezone.utc)
        if since_str
        else None
    )
    until = (
        datetime.fromisoformat(until_str).replace(tzinfo=timezone.utc)
        if until_str
        else None
    )

    if since and until:
        print(f"Backfill range: {since.date()} to {until.date()}")
    elif since:
        print(f"Backfill range: {since.date()} onward")
    elif until:
        print(f"Backfill range: earliest history to {until.date()}")
    else:
        print("Backfill range: full history")

    bucket_repo = ensure_bucket_repo(Path(bucket_cache_str))
    existing = load_existing_tasks(meta)
    packages = list_packages(bucket_repo)
    print(f"Existing tasks: {len(existing)}; packages discovered: {len(packages)}")

    total_queued = 0
    for index, pkg in enumerate(packages, start=1):
        seen_versions: set[str] = set()
        queued_for_package = 0

        for sha, _ in get_commit_log(bucket_repo, pkg, since, until):
            version = get_version_at(bucket_repo, sha, pkg)
            if not version or version in seen_versions:
                continue
            seen_versions.add(version)

            task_key = f"{pkg}__{version}"
            if task_key in existing:
                continue

            write_task(pending_dir, pkg, version, sha)
            existing.add(task_key)
            queued_for_package += 1
            total_queued += 1

        if queued_for_package:
            print(f"[{index}/{len(packages)}] {pkg}: queued {queued_for_package} versions")
        elif index % 100 == 0:
            print(f"[{index}/{len(packages)}] processed {index} packages")

    print(f"Done. Added tasks: {total_queued}")


def main() -> None:
    parser = argparse.ArgumentParser(description="BinSentinel historical backfill")
    parser.add_argument("meta_repo_path")
    parser.add_argument("--since", metavar="YYYY-MM-DD")
    parser.add_argument("--until", metavar="YYYY-MM-DD")
    parser.add_argument("--bucket-cache", default="./scoop-main-cache", metavar="DIR")
    args = parser.parse_args()
    run(args.meta_repo_path, args.since, args.until, args.bucket_cache)


if __name__ == "__main__":
    main()
