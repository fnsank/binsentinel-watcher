import json
from unittest.mock import patch

from watcher.check_updates_winget import run
from watcher.check_updates_winget import write_task_file


class TestWriteTaskFile:
    def test_写入winget任务文件(self, tmp_path):
        write_task_file(
            tmp_path,
            "Git.Git",
            "2.44.0",
            "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
            "deadbeef",
        )

        data = json.loads((tmp_path / "Git.Git__2.44.0.json").read_text())
        assert data["source"] == "winget"
        assert data["package"] == "Git.Git"
        assert data["version"] == "2.44.0"
        assert "bucket" not in data
        assert data["manifest_url"] == (
            "https://raw.githubusercontent.com/microsoft/winget-pkgs/deadbeef/"
            "manifests/g/Git/Git/2.44.0/Git.Git.yaml"
        )
        assert "name" not in data

    def test_写入winget任务文件带name(self, tmp_path):
        write_task_file(
            tmp_path,
            "Git.Git",
            "2.44.0",
            "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
            "deadbeef",
            name="Git",
        )

        data = json.loads((tmp_path / "Git.Git__2.44.0.json").read_text())
        assert data["name"] == "Git"


class TestRun:
    def test_首次运行仅记录winget_last_sha(self, tmp_path, capsys):
        meta = tmp_path / "meta"
        (meta / "queue" / "pending").mkdir(parents=True)

        with patch("watcher.check_updates_winget.get_head_sha", return_value="winget-head"):
            run(str(meta), "token")

        state = json.loads((meta / "state.json").read_text())
        assert state == {
            "sources": {
                "scoop-main": {"last_sha": None, "packages": {}},
                "winget": {"last_sha": "winget-head", "packages": {}},
            }
        }
        assert list((meta / "queue" / "pending").iterdir()) == []
        assert "首次运行：记录 winget HEAD SHA，本次不创建任务。" in capsys.readouterr().out

    def test_sha未变化时不创建任务(self, tmp_path, capsys):
        meta = tmp_path / "meta"
        (meta / "queue" / "pending").mkdir(parents=True)
        (meta / "state.json").write_text(
            json.dumps(
                {
                    "sources": {
                        "scoop-main": {"last_sha": None, "packages": {}},
                        "winget": {"last_sha": "same-sha", "packages": {"Git.Git": "2.43.0"}},
                    }
                }
            )
        )

        with patch("watcher.check_updates_winget.get_head_sha", return_value="same-sha"):
            run(str(meta), "token")

        assert list((meta / "queue" / "pending").iterdir()) == []
        assert "winget 自上次运行以来无变更。" in capsys.readouterr().out

    def test_发现新版本时写入winget任务并更新状态(self, tmp_path, capsys):
        meta = tmp_path / "meta"
        (meta / "queue" / "pending").mkdir(parents=True)
        (meta / "state.json").write_text(
            json.dumps(
                {
                    "sources": {
                        "scoop-main": {"last_sha": "scoop-sha", "packages": {"git": "2.44.0"}},
                        "winget": {"last_sha": "old-sha", "packages": {"Git.Git": "2.43.0"}},
                    }
                }
            )
        )

        with patch("watcher.check_updates_winget.get_head_sha", return_value="new-sha"), patch(
            "watcher.check_updates_winget.get_changed_package_details",
            return_value={
                "Git.Git": {
                    "version": "2.44.0",
                    "path": "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
                }
            },
        ), patch("watcher.check_updates_winget._fetch_package_name", return_value=None):
            run(str(meta), "token")

        state = json.loads((meta / "state.json").read_text())
        assert state == {
            "sources": {
                "scoop-main": {"last_sha": "scoop-sha", "packages": {"git": "2.44.0"}},
                "winget": {"last_sha": "new-sha", "packages": {"Git.Git": "2.44.0"}},
            }
        }
        pending = sorted(p.name for p in (meta / "queue" / "pending").iterdir())
        assert pending == ["Git.Git__2.44.0.json"]
        task = json.loads((meta / "queue" / "pending" / "Git.Git__2.44.0.json").read_text())
        assert task["source"] == "winget"
        assert task["manifest_url"] == (
            "https://raw.githubusercontent.com/microsoft/winget-pkgs/new-sha/"
            "manifests/g/Git/Git/2.44.0/Git.Git.yaml"
        )
        output = capsys.readouterr().out
        assert "已入队：Git.Git@2.44.0" in output
        assert "完成。winget 共入队 1 个任务。" in output

    def test_发现新版本时name写入任务(self, tmp_path):
        meta = tmp_path / "meta"
        (meta / "queue" / "pending").mkdir(parents=True)
        (meta / "state.json").write_text(
            json.dumps(
                {
                    "sources": {
                        "scoop-main": {"last_sha": "scoop-sha", "packages": {}},
                        "winget": {"last_sha": "old-sha", "packages": {}},
                    }
                }
            )
        )

        with patch("watcher.check_updates_winget.get_head_sha", return_value="new-sha"), patch(
            "watcher.check_updates_winget.get_changed_package_details",
            return_value={
                "0-don.clippy": {
                    "version": "1.5.12",
                    "path": "manifests/0/0-don/clippy/1.5.12/0-don.clippy.yaml",
                }
            },
        ), patch("watcher.check_updates_winget._fetch_package_name", return_value="Clippy"):
            run(str(meta), "token")

        task = json.loads((meta / "queue" / "pending" / "0-don.clippy__1.5.12.json").read_text())
        assert task["name"] == "Clippy"
