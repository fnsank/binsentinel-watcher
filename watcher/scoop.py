from pathlib import Path

import requests

_HEAD_URL = "https://api.github.com/repos/ScoopInstaller/Main/git/ref/heads/master"
_COMPARE_URL = "https://api.github.com/repos/ScoopInstaller/Main/compare/{base}...{head}"
_RAW_SHA_URL = "https://raw.githubusercontent.com/ScoopInstaller/Main/{sha}/bucket/{pkg}.json"


def get_head_sha(token: str) -> str:
    resp = requests.get(_HEAD_URL, headers=_auth_headers(token))
    resp.raise_for_status()
    return resp.json()["object"]["sha"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def get_changed_packages(base_sha: str, head_sha: str, token: str) -> dict[str, str]:
    url = _COMPARE_URL.format(base=base_sha, head=head_sha)
    resp = requests.get(url, headers=_auth_headers(token))
    resp.raise_for_status()

    result = {}
    for changed_file in resp.json().get("files", []):
        filename = changed_file["filename"]
        if (
            filename.startswith("bucket/")
            and filename.endswith(".json")
            and changed_file["status"] != "removed"
        ):
            pkg = Path(filename).stem
            version = _fetch_manifest_version(pkg, head_sha, token)
            if version:
                result[pkg] = version
    return result


def _fetch_manifest_version(pkg: str, sha: str, token: str) -> str | None:
    resp = requests.get(_RAW_SHA_URL.format(sha=sha, pkg=pkg), headers=_auth_headers(token))
    if resp.status_code == 200:
        return resp.json().get("version")
    return None

