"""
One-off migration: backfill the 'name' field in winget task files by
fetching PackageName from the pinned manifest_url.

Multi-file manifest packages store PackageName in the defaultLocale file,
not the version manifest, so we do a two-step fetch when needed.

Usage:
    GITHUB_TOKEN=<pat> python scripts/backfill_names.py <meta-repo-path>
    python scripts/backfill_names.py <meta-repo-path> --token <pat> --dry-run
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

QUEUE_SUBDIRS = ("pending", "processing", "done")


def _extract(yaml_text: str, field: str) -> str | None:
    for line in yaml_text.splitlines():
        if line.startswith(f"{field}:"):
            return line.split(":", 1)[1].strip()
    return None


def fetch_name(manifest_url: str, token: str | None) -> str | None:
    headers: dict[str, str] = {"Accept": "text/plain"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        resp = requests.get(manifest_url, headers=headers, timeout=15)
        if not resp.ok:
            return None
        name = _extract(resp.text, "PackageName")
        if name:
            return name
        # Multi-file manifest: PackageName lives in the defaultLocale file.
        locale = _extract(resp.text, "DefaultLocale")
        if not locale or not manifest_url.endswith(".yaml"):
            return None
        locale_url = manifest_url[:-5] + f".locale.{locale}.yaml"
        resp2 = requests.get(locale_url, headers=headers, timeout=15)
        if resp2.ok:
            return _extract(resp2.text, "PackageName")
    except Exception as exc:
        print(f"  warn: {exc}", file=sys.stderr)
    return None


def load_task(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"skip {path.name}: {exc}", file=sys.stderr)
        return None


def backfill(meta_repo_path: Path, token: str | None, dry_run: bool) -> None:
    updated = skipped = failed = 0

    for subdir in QUEUE_SUBDIRS:
        queue_dir = meta_repo_path / "queue" / subdir
        if not queue_dir.exists():
            continue

        files = sorted(queue_dir.glob("*.json"))
        if files:
            print(f"\n--- {subdir} ({len(files)} files) ---")

        for task_file in files:
            data = load_task(task_file)
            if data is None:
                failed += 1
                continue
            if "name" in data:
                skipped += 1
                continue
            if data.get("source") != "winget":
                skipped += 1
                continue

            manifest_url = data.get("manifest_url", "")
            if not manifest_url:
                print(f"  {task_file.name}: no manifest_url, skip")
                skipped += 1
                continue

            print(f"  {task_file.name} ... ", end="", flush=True)
            name = fetch_name(manifest_url, token)

            if name:
                data["name"] = name
                print(name)
                if not dry_run:
                    task_file.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                updated += 1
            else:
                print("(no name found)")
                failed += 1

            time.sleep(0.15)

    label = "[DRY RUN] " if dry_run else ""
    print(f"\n{label}完成：更新 {updated}，跳过 {skipped}（已有 name 或非 winget），未找到名字 {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill 'name' in winget task files.")
    parser.add_argument("meta_repo_path", help="Path to binsentinel-meta repository")
    parser.add_argument("--token", default=None, help="GitHub token (overrides GITHUB_TOKEN env var)")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("warning: no GITHUB_TOKEN set; requests may be rate-limited", file=sys.stderr)

    backfill(Path(args.meta_repo_path), token, args.dry_run)


if __name__ == "__main__":
    main()
