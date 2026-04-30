from unittest.mock import patch

from watcher.scoop import _fetch_manifest_version, get_changed_packages


class MockResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def _compare_response(files: list[dict]) -> MockResponse:
    return MockResponse(payload={"files": files})


def _manifest_response(version: str) -> MockResponse:
    return MockResponse(payload={"version": version})


def test_get_changed_packages_fetches_manifest_at_head_sha() -> None:
    compare = _compare_response(
        [{"filename": "bucket/git.json", "status": "modified"}]
    )
    with patch("watcher.scoop.requests.get") as mock_get:
        mock_get.side_effect = [compare, _manifest_response("2.44.0")]

        changed = get_changed_packages("base_sha", "abc123", "token")

    assert changed == {"git": "2.44.0"}
    manifest_call_url = mock_get.call_args_list[1][0][0]
    assert "abc123" in manifest_call_url
    assert "master" not in manifest_call_url


def test_fetch_manifest_version_uses_sha_url() -> None:
    with patch("watcher.scoop.requests.get") as mock_get:
        mock_get.return_value = _manifest_response("24.01")

        version = _fetch_manifest_version("7zip", "deadbeef", "token")

    assert version == "24.01"
    manifest_call_url = mock_get.call_args[0][0]
    assert "deadbeef" in manifest_call_url
    assert "master" not in manifest_call_url
