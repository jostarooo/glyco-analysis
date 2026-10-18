"""Create the GitHub repository and mirror the current HEAD through the REST API.

This avoids the unreliable git transport path on this machine. It requires a
classic personal access token with the ``repo`` scope in ``GH_TOKEN``,
``GITHUB_TOKEN``, or ``~/.github-token``.

Usage:
    .venv\\Scripts\\python.exe scripts\\publish_github.py
    .venv\\Scripts\\python.exe scripts\\publish_github.py --repo glyco-analysis --private
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
UA = "glyco-analysis-publish/0.1"


class GitHubError(RuntimeError):
    pass


def git(root: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
    )
    if proc.returncode:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return proc.stdout


def api(
    method: str,
    path: str,
    token: str,
    payload: dict | None = None,
    *,
    allow_404: bool = False,
) -> dict | None:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": UA,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if exc.code == 404 and allow_404:
            return None
        if exc.code == 403 and path == "/user/repos":
            raise GitHubError(
                "POST /user/repos returned 403. Fine-grained tokens cannot create "
                "repositories; use a classic PAT with repo scope."
            ) from exc
        raise GitHubError(f"{method} {path} returned HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"{method} {path} failed: {exc.reason}") from exc


def token_from_environment() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    token_file = Path.home() / ".github-token"
    if token_file.is_file():
        return token_file.read_text(encoding="utf-8").strip()
    raise GitHubError(
        "No GitHub token found. Set GH_TOKEN or create "
        f"{token_file} with a classic PAT that has repo scope."
    )


def tracked_files(root: Path) -> list[dict]:
    records = git(root, "ls-files", "--stage", "-z").split(b"\0")
    files = []
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, local_sha, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise RuntimeError(f"Unmerged index entry: {raw_path!r}")
        if mode not in {"100644", "100755"}:
            raise RuntimeError(f"Unsupported git mode {mode}: {raw_path!r}")
        path = raw_path.decode("utf-8")
        content = git(root, "cat-file", "blob", local_sha)
        files.append(
            {
                "path": path,
                "mode": mode,
                "local_sha": local_sha,
                "content": content,
            }
        )
    return files


def current_state(root: Path) -> tuple[str, str]:
    return (
        git(root, "rev-parse", "HEAD").decode("ascii").strip(),
        git(root, "rev-parse", "HEAD^{tree}").decode("ascii").strip(),
    )


def ensure_repository(
    token: str,
    owner: str,
    repo: str,
    *,
    private: bool,
    description: str,
) -> dict:
    existing = api("GET", f"/repos/{owner}/{repo}", token, allow_404=True)
    if existing:
        print(f"Repository exists: {existing['html_url']}")
        return existing
    created = api(
        "POST",
        "/user/repos",
        token,
        {
            "name": repo,
            "private": private,
            "description": description,
            "auto_init": False,
            "has_wiki": False,
        },
    )
    print(f"Repository created: {created['html_url']}")
    return created


def ensure_empty_branch(token: str, owner: str, repo: str) -> None:
    ref = api(
        "GET",
        f"/repos/{owner}/{repo}/git/ref/heads/main",
        token,
        allow_404=True,
    )
    if ref:
        raise GitHubError(
            "Remote branch main already exists. This script refuses to rewrite it. "
            "Verify the remote tree or choose a new repository name."
        )


def upload_blobs(token: str, owner: str, repo: str, files: list[dict]) -> list[dict]:
    entries = []
    for index, item in enumerate(files, start=1):
        remote = api(
            "POST",
            f"/repos/{owner}/{repo}/git/blobs",
            token,
            {
                "content": base64.b64encode(item["content"]).decode("ascii"),
                "encoding": "base64",
            },
        )
        if remote["sha"] != item["local_sha"]:
            raise GitHubError(
                f"Blob SHA mismatch for {item['path']}: "
                f"local {item['local_sha']}, remote {remote['sha']}"
            )
        entries.append(
            {
                "path": item["path"],
                "mode": item["mode"],
                "type": "blob",
                "sha": remote["sha"],
            }
        )
        print(f"[{index}/{len(files)}] uploaded {item['path']}")
    return entries


def publish(root: Path, token: str, repo_name: str, private: bool) -> str:
    user = api("GET", "/user", token)
    owner = user["login"]
    local_commit, local_tree = current_state(root)
    description = "糖基化分析系统：蛋白质语言模型位点预测 + 糖链图神经网络 + 工具调用智能体"
    repository = ensure_repository(
        token,
        owner,
        repo_name,
        private=private,
        description=description,
    )
    ensure_empty_branch(token, owner, repo_name)

    files = tracked_files(root)
    entries = upload_blobs(token, owner, repo_name, files)
    remote_tree = api(
        "POST",
        f"/repos/{owner}/{repo_name}/git/trees",
        token,
        {"tree": entries},
    )
    if remote_tree["sha"] != local_tree:
        raise GitHubError(
            f"Tree SHA mismatch: local {local_tree}, remote {remote_tree['sha']}"
        )

    message = git(root, "log", "-1", "--format=%B").decode("utf-8").strip()
    remote_commit = api(
        "POST",
        f"/repos/{owner}/{repo_name}/git/commits",
        token,
        {"message": message, "tree": remote_tree["sha"], "parents": []},
    )
    api(
        "POST",
        f"/repos/{owner}/{repo_name}/git/refs",
        token,
        {"ref": "refs/heads/main", "sha": remote_commit["sha"]},
    )

    ref = api("GET", f"/repos/{owner}/{repo_name}/git/ref/heads/main", token)
    commit = api(
        "GET",
        f"/repos/{owner}/{repo_name}/git/commits/{ref['object']['sha']}",
        token,
    )
    if commit["tree"]["sha"] != local_tree:
        raise GitHubError("Post-publish tree verification failed.")
    print(f"Verified local {local_commit} -> remote {commit['sha']} (tree {local_tree})")
    return repository["html_url"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=None, help="Repository name; defaults to folder name")
    parser.add_argument("--private", action="store_true", help="Create a private repository")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    repo_name = args.repo or root.name
    try:
        url = publish(root, token_from_environment(), repo_name, args.private)
    except (GitHubError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
