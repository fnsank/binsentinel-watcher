import json
from unittest.mock import patch

from watcher.check_updates_scoop import (
    find_new_versions,
    load_state,
    run,
    save_state,
    write_task_file,
)


class TestLoadState:
    def test_文件不存在时返回默认值(self, tmp_path):
        result = load_state(tmp_path / "state.json")
        assert result == {
            "sources": {
                "scoop-main": {"last_sha": None, "packages": {}},
                "winget": {"last_sha": None, "packages": {}},
            }
        }

    def test_旧格式state自动迁移到sources(self, tmp_path):
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_sha": "abc", "packages": {"git": "2.43.0"}}))
        result = load_state(f)
        assert result["sources"]["scoop-main"]["last_sha"] == "abc"
        assert result["sources"]["scoop-main"]["packages"]["git"] == "2.43.0"
        assert result["sources"]["winget"] == {"last_sha": None, "packages": {}}

    def test_带utf8_bom的state也能读取(self, tmp_path):
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps({"last_sha": "abc", "packages": {"git": "2.43.0"}}),
            encoding="utf-8-sig",
        )
        result = load_state(f)
        assert result["sources"]["scoop-main"]["last_sha"] == "abc"
        assert result["sources"]["scoop-main"]["packages"]["git"] == "2.43.0"


class TestSaveState:
    def test_将state字典写入JSON文件(self, tmp_path):
        f = tmp_path / "state.json"
        save_state(
            f,
            {
                "sources": {
                    "scoop-main": {"last_sha": "xyz", "packages": {"curl": "8.5.0"}},
                    "winget": {"last_sha": None, "packages": {}},
                }
            },
        )
        data = json.loads(f.read_text())
        assert data["sources"]["scoop-main"]["last_sha"] == "xyz"
        assert data["sources"]["scoop-main"]["packages"]["curl"] == "8.5.0"
        assert "last_sha" not in data
        assert "packages" not in data


class TestFindNewVersions:
    def test_检测到版本升级(self):
        result = find_new_versions({"git": "2.43.0"}, {"git": "2.44.0"})
        assert result == {"git": "2.44.0"}

    def test_检测到全新的包(self):
        result = find_new_versions({}, {"git": "2.44.0"})
        assert result == {"git": "2.44.0"}

    def test_版本相同时返回空字典(self):
        result = find_new_versions({"git": "2.44.0"}, {"git": "2.44.0"})
        assert result == {}

    def test_多包时只返回有变化的包(self):
        known = {"git": "2.43.0", "curl": "8.5.0"}
        current = {"git": "2.44.0", "curl": "8.5.0"}
        result = find_new_versions(known, current)
        assert result == {"git": "2.44.0"}


class TestWriteTaskFile:
    def test_创建正确命名的任务文件(self, tmp_path):
        write_task_file(tmp_path, "git", "2.44.0", "main", "deadbeef")
        assert (tmp_path / "git__2.44.0.json").exists()

    def test_任务文件包含所有必要字段(self, tmp_path):
        write_task_file(tmp_path, "curl", "8.5.0", "main", "deadbeef")
        data = json.loads((tmp_path / "curl__8.5.0.json").read_text())
        assert data["source"] == "scoop"
        assert data["package"] == "curl"
        assert data["version"] == "8.5.0"
        assert data["bucket"] == "main"
        assert "queued_at" in data
        assert "manifest_url" in data
        assert data["manifest_url"] == (
            "https://raw.githubusercontent.com/ScoopInstaller/Main/deadbeef/bucket/curl.json"
        )

    def test_文件名使用双下划线分隔包名和版本(self, tmp_path):
        write_task_file(tmp_path, "7zip", "23.01", "main", "deadbeef")
        assert (tmp_path / "7zip__23.01.json").exists()


class TestRun:
    def test_首次运行时记录head_sha且不创建任务(self, tmp_path, capsys):
        meta = tmp_path / "meta"
        (meta / "queue" / "pending").mkdir(parents=True)

        with patch("watcher.check_updates_scoop.get_head_sha", return_value="head123"):
            run(str(meta), "token")

        state = json.loads((meta / "state.json").read_text())
        assert state == {
            "sources": {
                "scoop-main": {"last_sha": "head123", "packages": {}},
                "winget": {"last_sha": None, "packages": {}},
            }
        }
        assert list((meta / "queue" / "pending").iterdir()) == []
        assert "首次运行：记录 HEAD SHA，本次不创建任务。" in capsys.readouterr().out

    def test_sha未变化时不创建任务(self, tmp_path, capsys):
        meta = tmp_path / "meta"
        (meta / "queue" / "pending").mkdir(parents=True)
        (meta / "state.json").write_text(
            json.dumps(
                {
                    "sources": {
                        "scoop-main": {"last_sha": "same-sha", "packages": {"git": "2.43.0"}},
                        "winget": {"last_sha": None, "packages": {}},
                    }
                }
            )
        )

        with patch("watcher.check_updates_scoop.get_head_sha", return_value="same-sha"):
            run(str(meta), "token")

        state = json.loads((meta / "state.json").read_text())
        assert state == {
            "sources": {
                "scoop-main": {"last_sha": "same-sha", "packages": {"git": "2.43.0"}},
                "winget": {"last_sha": None, "packages": {}},
            }
        }
        assert list((meta / "queue" / "pending").iterdir()) == []
        assert "自上次运行以来无变更。" in capsys.readouterr().out

    def test_发现新版本时写入任务并更新状态(self, tmp_path, capsys):
        meta = tmp_path / "meta"
        (meta / "queue" / "pending").mkdir(parents=True)
        (meta / "state.json").write_text(
            json.dumps(
                {
                    "sources": {
                        "scoop-main": {"last_sha": "old-sha", "packages": {"git": "2.43.0"}},
                        "winget": {"last_sha": None, "packages": {}},
                    }
                }
            )
        )

        with patch("watcher.check_updates_scoop.get_head_sha", return_value="new-sha"), patch(
            "watcher.check_updates_scoop.get_changed_packages",
            return_value={"git": "2.44.0", "curl": "8.5.0"},
        ):
            run(str(meta), "token")

        state = json.loads((meta / "state.json").read_text())
        assert state == {
            "sources": {
                "scoop-main": {
                    "last_sha": "new-sha",
                    "packages": {"git": "2.44.0", "curl": "8.5.0"},
                },
                "winget": {"last_sha": None, "packages": {}},
            }
        }
        pending = sorted(p.name for p in (meta / "queue" / "pending").iterdir())
        assert pending == ["curl__8.5.0.json", "git__2.44.0.json"]
        git_task = json.loads((meta / "queue" / "pending" / "git__2.44.0.json").read_text())
        assert git_task["source"] == "scoop"
        assert git_task["manifest_url"] == (
            "https://raw.githubusercontent.com/ScoopInstaller/Main/new-sha/bucket/git.json"
        )
        output = capsys.readouterr().out
        assert "已入队：git@2.44.0" in output
        assert "已入队：curl@8.5.0" in output
        assert "完成。共入队 2 个任务。" in output
