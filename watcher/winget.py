import re

import requests

_REPO = "microsoft/winget-pkgs"
# Matches locale-specific package ID suffixes like .eu, .de, .en-US, .zh-CN
_LOCALE_PACKAGE_RE = re.compile(r"\.[a-z]{2}(-[A-Z]{2})?$")
_HEAD_URL = f"https://api.github.com/repos/{_REPO}/git/ref/heads/master"
_COMPARE_URL = f"https://api.github.com/repos/{_REPO}/compare/{{base}}...{{head}}"


def get_head_sha(token: str) -> str:
    resp = requests.get(_HEAD_URL, headers=_auth_headers(token))
    resp.raise_for_status()
    return resp.json()["object"]["sha"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def _compare(base_sha: str, head_sha: str, token: str) -> dict:
    resp = requests.get(
        _COMPARE_URL.format(base=base_sha, head=head_sha),
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


def _parse_manifest_path(path: str) -> tuple[str | None, str | None]:
    parts = path.split("/")
    if len(parts) < 6 or parts[0] != "manifests":
        return None, None

    filename = parts[-1]
    if not filename.endswith(".yaml"):
        return None, None

    package_id = filename[:-5]
    if package_id.endswith(".installer") or ".locale." in package_id:
        return None, None
    if _LOCALE_PACKAGE_RE.search(package_id):
        return None, None

    return package_id, parts[-2]


def _get_mid_sha(base_sha: str, head_sha: str, token: str, compare_data: dict | None = None) -> str:
    data = compare_data if compare_data is not None else _compare(base_sha, head_sha, token)
    commits = data.get("commits", [])
    if not commits:
        raise RuntimeError(f"unable to split winget compare range {base_sha}...{head_sha}")

    mid_sha = commits[len(commits) // 2]["sha"]
    if mid_sha in {base_sha, head_sha}:
        raise RuntimeError(f"invalid midpoint {mid_sha} for winget compare range {base_sha}...{head_sha}")
    return mid_sha


def get_changed_package_details(base_sha: str, head_sha: str, token: str) -> dict[str, dict[str, str]]:
    data = _compare(base_sha, head_sha, token)
    if data.get("truncated"):
        mid_sha = _get_mid_sha(base_sha, head_sha, token, data)
        left = get_changed_package_details(base_sha, mid_sha, token)
        right = get_changed_package_details(mid_sha, head_sha, token)
        return {**left, **right}

    result: dict[str, dict[str, str]] = {}
    for changed_file in data.get("files", []):
        if changed_file.get("status") == "removed":
            continue

        filename = changed_file.get("filename", "")
        package_id, version = _parse_manifest_path(filename)
        if package_id and version:
            result[package_id] = {"version": version, "path": filename}
    return result


def get_changed_packages(base_sha: str, head_sha: str, token: str) -> dict[str, str]:
    return {
        package_id: detail["version"]
        for package_id, detail in get_changed_package_details(base_sha, head_sha, token).items()
    }


def extract_package_name(yaml_text: str) -> str | None:
    for line in yaml_text.splitlines():
        if line.startswith("PackageName:"):
            return line.split(":", 1)[1].strip()
    return None


def extract_default_locale(yaml_text: str) -> str | None:
    for line in yaml_text.splitlines():
        if line.startswith("DefaultLocale:"):
            return line.split(":", 1)[1].strip()
    return None
