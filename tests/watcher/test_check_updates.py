import json

from watcher.check_updates import write_task_file


def test_write_task_file_manifest_url_contains_sha(tmp_path) -> None:
    write_task_file(tmp_path, "git", "2.44.0", "main", "deadbeef")

    data = json.loads((tmp_path / "git__2.44.0.json").read_text())
    assert data["package"] == "git"
    assert data["version"] == "2.44.0"
    assert "deadbeef" in data["manifest_url"]
    assert "master" not in data["manifest_url"]
