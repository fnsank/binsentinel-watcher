import json
from pathlib import Path

import pytest

from scripts.queue_winget_dir import collect_version_dirs
from scripts.queue_winget_dir import find_main_manifest
from scripts.queue_winget_dir import load_existing_task_keys
from scripts.queue_winget_dir import queue_manifest_root


def write_manifest(path: Path, content: str = "PackageIdentifier: x\nPackageVersion: 1.0.0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestCollectVersionDirs:
    def test_包根目录返回所有版本子目录(self, tmp_path):
        root = tmp_path / "manifests" / "1" / "123" / "123pan"
        (root / "1.0.0").mkdir(parents=True)
        (root / "1.1.0").mkdir()

        result = collect_version_dirs(root)

        assert [path.name for path in result] == ["1.0.0", "1.1.0"]

    def test_单版本目录直接返回自身(self, tmp_path):
        version_dir = tmp_path / "manifests" / "1" / "123" / "123pan" / "1.0.0"
        write_manifest(version_dir / "123.123pan.yaml")

        result = collect_version_dirs(version_dir)

        assert result == [version_dir]

    def test_不存在目录时报错(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            collect_version_dirs(tmp_path / "missing")


class TestFindMainManifest:
    def test_忽略installer和locale文件(self, tmp_path):
        version_dir = tmp_path / "1.0.0"
        write_manifest(version_dir / "123.123pan.installer.yaml")
        write_manifest(version_dir / "123.123pan.locale.zh-CN.yaml")
        write_manifest(version_dir / "123.123pan.yaml")

        result = find_main_manifest(version_dir)

        assert result is not None
        assert result.name == "123.123pan.yaml"


class TestLoadExistingTaskKeys:
    def test_从三个队列目录收集已有任务(self, tmp_path):
        for subdir in ("pending", "processing", "done"):
            task_dir = tmp_path / "queue" / subdir
            task_dir.mkdir(parents=True)
            (task_dir / "123.123pan__1.0.0.json").write_text("{}")

        result = load_existing_task_keys(tmp_path)

        assert "123.123pan__1.0.0" in result


class TestQueueManifestRoot:
    def test_从包根目录写入多个版本任务(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        root = winget / "manifests" / "1" / "123" / "123pan"

        write_manifest(root / "1.0.0" / "123.123pan.yaml")
        write_manifest(root / "1.0.0" / "123.123pan.locale.zh-CN.yaml")
        write_manifest(root / "1.1.0" / "123.123pan.yaml")

        queued = queue_manifest_root(meta, winget, "manifests/1/123/123pan", "deadbeef")

        assert queued == 2
        data = json.loads((meta / "queue" / "pending" / "123.123pan__1.1.0.json").read_text())
        assert data["source"] == "winget"
        assert data["package"] == "123.123pan"
        assert data["version"] == "1.1.0"
        assert data["manifest_url"] == (
            "https://raw.githubusercontent.com/microsoft/winget-pkgs/deadbeef/"
            "manifests/1/123/123pan/1.1.0/123.123pan.yaml"
        )

    def test_单版本目录输入也能写任务(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        version_dir = winget / "manifests" / "1" / "123" / "123pan" / "1.0.0"
        write_manifest(version_dir / "123.123pan.yaml")

        queued = queue_manifest_root(meta, winget, "manifests/1/123/123pan/1.0.0", "deadbeef")

        assert queued == 1
        assert (meta / "queue" / "pending" / "123.123pan__1.0.0.json").exists()

    def test_跳过已存在任务(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        root = winget / "manifests" / "1" / "123" / "123pan"

        write_manifest(root / "1.0.0" / "123.123pan.yaml")
        existing_dir = meta / "queue" / "done"
        existing_dir.mkdir(parents=True)
        (existing_dir / "123.123pan__1.0.0.json").write_text("{}")

        queued = queue_manifest_root(meta, winget, "manifests/1/123/123pan", "deadbeef")

        assert queued == 0
