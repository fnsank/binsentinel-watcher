import pytest
from unittest.mock import MagicMock, patch

from watcher.scoop import get_changed_packages
from watcher.scoop import get_head_sha


class TestGetHeadSha:
    def test_从API返回正确的SHA(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"object": {"sha": "abc123def456"}}
        mock_resp.raise_for_status.return_value = None

        with patch("watcher.scoop.requests.get", return_value=mock_resp) as mock_get:
            result = get_head_sha("test-token")

        assert result == "abc123def456"
        called_url = mock_get.call_args[0][0]
        assert "ScoopInstaller/Main" in called_url
        assert "heads/master" in called_url
        assert mock_get.call_args.kwargs["headers"] == {
            "Authorization": "token test-token",
            "Accept": "application/vnd.github.v3+json",
        }

    def test_API报错时向上抛出异常(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("API error")

        with patch("watcher.scoop.requests.get", return_value=mock_resp):
            with pytest.raises(Exception, match="API error"):
                get_head_sha("test-token")


class TestGetChangedPackages:
    def _compare_resp(self, files):
        r = MagicMock()
        r.json.return_value = {"files": files}
        r.raise_for_status.return_value = None
        return r

    def _manifest_resp(self, version):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"version": version}
        return r

    def test_返回已修改的bucket包及版本(self):
        compare = self._compare_resp([
            {"filename": "bucket/git.json", "status": "modified"},
            {"filename": "bucket/curl.json", "status": "added"},
        ])
        with patch("watcher.scoop.requests.get") as mock_get:
            mock_get.side_effect = [
                compare,
                self._manifest_resp("2.44.0"),
                self._manifest_resp("8.5.0"),
            ]
            result = get_changed_packages("sha1", "sha2", "token")
        assert result == {"git": "2.44.0", "curl": "8.5.0"}
        called_urls = [call.args[0] for call in mock_get.call_args_list]
        expected_headers = {
            "Authorization": "token token",
            "Accept": "application/vnd.github.v3+json",
        }
        assert called_urls == [
            "https://api.github.com/repos/ScoopInstaller/Main/compare/sha1...sha2",
            "https://raw.githubusercontent.com/ScoopInstaller/Main/sha2/bucket/git.json",
            "https://raw.githubusercontent.com/ScoopInstaller/Main/sha2/bucket/curl.json",
        ]
        assert [call.kwargs["headers"] for call in mock_get.call_args_list] == [
            expected_headers,
            expected_headers,
            expected_headers,
        ]

    def test_manifest请求使用head_sha而非master(self):
        compare = self._compare_resp([
            {"filename": "bucket/git.json", "status": "modified"},
        ])
        with patch("watcher.scoop.requests.get") as mock_get:
            mock_get.side_effect = [compare, self._manifest_resp("2.44.0")]
            get_changed_packages("base-sha", "abc123", "token")

        manifest_call_url = mock_get.call_args_list[1].args[0]
        assert "abc123" in manifest_call_url
        assert "master" not in manifest_call_url

    def test_忽略已删除的文件(self):
        compare = self._compare_resp([
            {"filename": "bucket/old.json", "status": "removed"},
        ])
        with patch("watcher.scoop.requests.get", return_value=compare) as mock_get:
            result = get_changed_packages("sha1", "sha2", "token")
        assert result == {}
        assert mock_get.call_count == 1
        assert mock_get.call_args_list[0].args[0] == (
            "https://api.github.com/repos/ScoopInstaller/Main/compare/sha1...sha2"
        )

    def test_忽略非bucket目录的文件(self):
        compare = self._compare_resp([
            {"filename": "README.md", "status": "modified"},
            {"filename": "scripts/generate.ps1", "status": "modified"},
        ])
        with patch("watcher.scoop.requests.get", return_value=compare) as mock_get:
            result = get_changed_packages("sha1", "sha2", "token")
        assert result == {}
        assert mock_get.call_count == 1
        assert mock_get.call_args_list[0].args[0] == (
            "https://api.github.com/repos/ScoopInstaller/Main/compare/sha1...sha2"
        )

    def test_跳过缺少version字段的manifest(self):
        compare = self._compare_resp([
            {"filename": "bucket/broken.json", "status": "modified"},
        ])
        bad = MagicMock()
        bad.status_code = 200
        bad.json.return_value = {}
        with patch("watcher.scoop.requests.get") as mock_get:
            mock_get.side_effect = [compare, bad]
            result = get_changed_packages("sha1", "sha2", "token")
        assert result == {}

    def test_跳过返回404的manifest(self):
        compare = self._compare_resp([
            {"filename": "bucket/gone.json", "status": "modified"},
        ])
        not_found = MagicMock()
        not_found.status_code = 404
        with patch("watcher.scoop.requests.get") as mock_get:
            mock_get.side_effect = [compare, not_found]
            result = get_changed_packages("sha1", "sha2", "token")
        assert result == {}
