import pytest
from unittest.mock import MagicMock, patch

from watcher.winget import _parse_manifest_path
from watcher.winget import get_changed_package_details
from watcher.winget import get_changed_packages
from watcher.winget import get_head_sha


class TestGetHeadSha:
    def test_从API返回正确的SHA(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"object": {"sha": "winget-head"}}
        mock_resp.raise_for_status.return_value = None

        with patch("watcher.winget.requests.get", return_value=mock_resp) as mock_get:
            result = get_head_sha("test-token")

        assert result == "winget-head"
        assert mock_get.call_args.args[0].endswith("/microsoft/winget-pkgs/git/ref/heads/master")


class TestParseManifestPath:
    def test_解析主manifest路径(self):
        assert _parse_manifest_path("manifests/g/Git/Git/2.44.0/Git.Git.yaml") == (
            "Git.Git",
            "2.44.0",
        )

    def test_忽略installer清单(self):
        assert _parse_manifest_path("manifests/g/Git/Git/2.44.0/Git.Git.installer.yaml") == (
            None,
            None,
        )

    def test_忽略locale清单(self):
        assert _parse_manifest_path("manifests/g/Git/Git/2.44.0/Git.Git.locale.en-US.yaml") == (
            None,
            None,
        )

    def test_忽略非manifest路径(self):
        assert _parse_manifest_path("README.md") == (None, None)


class TestGetChangedPackages:
    def _compare_resp(self, files, truncated=False, commits=None):
        resp = MagicMock()
        resp.json.return_value = {
            "files": files,
            "truncated": truncated,
            "commits": commits or [],
        }
        resp.raise_for_status.return_value = None
        return resp

    def test_返回package_id到version映射(self):
        compare = self._compare_resp(
            [
                {
                    "filename": "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
                    "status": "added",
                },
                {
                    "filename": "manifests/g/Git/Git/2.44.0/Git.Git.locale.en-US.yaml",
                    "status": "modified",
                },
            ]
        )
        with patch("watcher.winget.requests.get", return_value=compare):
            result = get_changed_packages("base", "head", "token")

        assert result == {"Git.Git": "2.44.0"}

    def test_返回manifest路径明细(self):
        compare = self._compare_resp(
            [
                {
                    "filename": "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
                    "status": "added",
                }
            ]
        )
        with patch("watcher.winget.requests.get", return_value=compare):
            result = get_changed_package_details("base", "head", "token")

        assert result == {
            "Git.Git": {
                "version": "2.44.0",
                "path": "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
            }
        }

    def test_忽略removed文件(self):
        compare = self._compare_resp(
            [
                {
                    "filename": "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
                    "status": "removed",
                }
            ]
        )
        with patch("watcher.winget.requests.get", return_value=compare):
            result = get_changed_packages("base", "head", "token")

        assert result == {}

    def test_truncated时递归拆分区间(self):
        top = self._compare_resp(
            [],
            truncated=True,
            commits=[{"sha": "c1"}, {"sha": "mid"}, {"sha": "head"}],
        )
        left = self._compare_resp(
            [
                {
                    "filename": "manifests/g/Git/Git/2.43.0/Git.Git.yaml",
                    "status": "added",
                }
            ]
        )
        right = self._compare_resp(
            [
                {
                    "filename": "manifests/g/Git/Git/2.44.0/Git.Git.yaml",
                    "status": "added",
                }
            ]
        )
        with patch("watcher.winget.requests.get") as mock_get:
            mock_get.side_effect = [top, left, right]
            result = get_changed_packages("base", "head", "token")

        assert result == {"Git.Git": "2.44.0"}
        called_urls = [call.args[0] for call in mock_get.call_args_list]
        assert called_urls == [
            "https://api.github.com/repos/microsoft/winget-pkgs/compare/base...head",
            "https://api.github.com/repos/microsoft/winget-pkgs/compare/base...mid",
            "https://api.github.com/repos/microsoft/winget-pkgs/compare/mid...head",
        ]

    def test_truncated缺少commits时抛错(self):
        top = self._compare_resp([], truncated=True, commits=[])
        with patch("watcher.winget.requests.get", return_value=top):
            with pytest.raises(RuntimeError, match="unable to split"):
                get_changed_packages("base", "head", "token")
