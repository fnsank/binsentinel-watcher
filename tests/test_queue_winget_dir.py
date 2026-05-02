import json
from pathlib import Path

import pytest

from scripts.queue_winget_dir import collect_version_dirs
from scripts.queue_winget_dir import extract_package_name
from scripts.queue_winget_dir import find_main_manifest
from scripts.queue_winget_dir import load_existing_task_keys
from scripts.queue_winget_dir import normalize_manifest_root
from scripts.queue_winget_dir import queue_manifest_root


def write_manifest(path: Path, content: str = "PackageIdentifier: x\nPackageVersion: 1.0.0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestCollectVersionDirs:
    def test_returns_all_version_subdirs_for_package_root(self, tmp_path):
        root = tmp_path / "manifests" / "1" / "123" / "123pan"
        (root / "1.0.0").mkdir(parents=True)
        (root / "1.1.0").mkdir()

        result = collect_version_dirs(root)

        assert [path.name for path in result] == ["1.0.0", "1.1.0"]

    def test_returns_version_dir_itself_when_manifest_files_exist(self, tmp_path):
        version_dir = tmp_path / "manifests" / "1" / "123" / "123pan" / "1.0.0"
        write_manifest(version_dir / "123.123pan.yaml")

        result = collect_version_dirs(version_dir)

        assert result == [version_dir]

    def test_raises_when_directory_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            collect_version_dirs(tmp_path / "missing")


class TestNormalizeManifestRoot:
    def test_keeps_manifest_path(self):
        assert normalize_manifest_root("manifests/1/123/123pan") == "manifests/1/123/123pan"

    def test_normalizes_github_tree_url(self):
        assert (
            normalize_manifest_root(
                "https://github.com/microsoft/winget-pkgs/tree/master/manifests/0/0-don/clippy"
            )
            == "manifests/0/0-don/clippy"
        )

    def test_rejects_non_manifest_path(self):
        with pytest.raises(ValueError, match="manifests/"):
            normalize_manifest_root("https://github.com/microsoft/winget-pkgs/tree/master/tools/foo")


class TestFindMainManifest:
    def test_ignores_installer_and_locale_files(self, tmp_path):
        version_dir = tmp_path / "1.0.0"
        write_manifest(version_dir / "123.123pan.installer.yaml")
        write_manifest(version_dir / "123.123pan.locale.zh-CN.yaml")
        write_manifest(version_dir / "123.123pan.yaml")

        result = find_main_manifest(version_dir)

        assert result is not None
        assert result.name == "123.123pan.yaml"


class TestLoadExistingTaskKeys:
    def test_collects_existing_tasks_from_all_queue_dirs(self, tmp_path):
        for subdir in ("pending", "processing", "done"):
            task_dir = tmp_path / "queue" / subdir
            task_dir.mkdir(parents=True)
            (task_dir / "123.123pan__1.0.0.json").write_text("{}")

        result = load_existing_task_keys(tmp_path)

        assert "123.123pan__1.0.0" in result


class TestQueueManifestRoot:
    def test_writes_multiple_versions_from_package_root(self, tmp_path):
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

    def test_writes_task_for_single_version_input(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        version_dir = winget / "manifests" / "1" / "123" / "123pan" / "1.0.0"
        write_manifest(version_dir / "123.123pan.yaml")

        queued = queue_manifest_root(meta, winget, "manifests/1/123/123pan/1.0.0", "deadbeef")

        assert queued == 1
        assert (meta / "queue" / "pending" / "123.123pan__1.0.0.json").exists()

    def test_writes_task_for_github_url_input(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        version_dir = winget / "manifests" / "0" / "0-don" / "clippy" / "1.0.0"
        write_manifest(version_dir / "0Don.Clippy.yaml")

        queued = queue_manifest_root(
            meta,
            winget,
            "https://github.com/microsoft/winget-pkgs/tree/master/manifests/0/0-don/clippy",
            "deadbeef",
        )

        assert queued == 1
        assert (meta / "queue" / "pending" / "0Don.Clippy__1.0.0.json").exists()

    def test_writes_name_when_manifest_has_package_name(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        version_dir = winget / "manifests" / "0" / "0-don" / "clippy" / "1.5.12"
        write_manifest(
            version_dir / "0-don.clippy.yaml",
            "PackageIdentifier: 0-don.clippy\nPackageVersion: 1.5.12\nPackageName: Clippy\n",
        )

        queue_manifest_root(meta, winget, "manifests/0/0-don/clippy/1.5.12", "abc123")

        data = json.loads((meta / "queue" / "pending" / "0-don.clippy__1.5.12.json").read_text())
        assert data["name"] == "Clippy"

    def test_omits_name_when_manifest_has_no_package_name(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        version_dir = winget / "manifests" / "1" / "123" / "123pan" / "1.0.0"
        write_manifest(version_dir / "123.123pan.yaml")

        queue_manifest_root(meta, winget, "manifests/1/123/123pan/1.0.0", "abc123")

        data = json.loads((meta / "queue" / "pending" / "123.123pan__1.0.0.json").read_text())
        assert "name" not in data

    def test_skips_existing_task(self, tmp_path):
        meta = tmp_path / "meta"
        winget = tmp_path / "winget-pkgs"
        root = winget / "manifests" / "1" / "123" / "123pan"

        write_manifest(root / "1.0.0" / "123.123pan.yaml")
        existing_dir = meta / "queue" / "done"
        existing_dir.mkdir(parents=True)
        (existing_dir / "123.123pan__1.0.0.json").write_text("{}")

        queued = queue_manifest_root(meta, winget, "manifests/1/123/123pan", "deadbeef")

        assert queued == 0
