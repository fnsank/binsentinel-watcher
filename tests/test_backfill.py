import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.backfill import get_commit_log, load_existing_tasks, write_task


def test_load_existing_tasks_collects_keys_from_all_queue_dirs(tmp_path) -> None:
    pending = tmp_path / "queue" / "pending"
    processing = tmp_path / "queue" / "processing"
    done = tmp_path / "queue" / "done"
    pending.mkdir(parents=True)
    processing.mkdir(parents=True)
    done.mkdir(parents=True)

    (pending / "git__2.44.0.json").write_text("{}")
    (processing / "7zip__24.01.json").write_text("{}")
    (done / "fzf__0.52.0.json").write_text("{}")

    result = load_existing_tasks(tmp_path)

    assert result == {"git__2.44.0", "7zip__24.01", "fzf__0.52.0"}


def test_load_existing_tasks_returns_empty_set_when_queue_dirs_missing(tmp_path) -> None:
    (tmp_path / "queue" / "pending").mkdir(parents=True)

    result = load_existing_tasks(tmp_path)

    assert result == set()


def test_write_task_writes_expected_task_payload(tmp_path) -> None:
    write_task(tmp_path, "git", "2.44.0", "abc123")

    task_file = tmp_path / "git__2.44.0.json"
    assert task_file.exists()

    data = json.loads(task_file.read_text())
    assert data["package"] == "git"
    assert data["version"] == "2.44.0"
    assert "abc123" in data["manifest_url"]
    assert "master" not in data["manifest_url"]
    assert "queued_at" in data


def test_get_commit_log_places_date_filters_before_pathspec() -> None:
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)
    until = datetime(2024, 1, 7, tzinfo=timezone.utc)

    with patch("scripts.backfill.git", return_value="") as mock_git:
        get_commit_log(Path("repo"), "git", since, until)

    git_args = mock_git.call_args[0][1:]
    assert git_args == (
        "log",
        "--follow",
        "--pretty=format:%H %aI",
        "--after=2024-01-01",
        "--before=2024-01-07",
        "--",
        "bucket/git.json",
    )
