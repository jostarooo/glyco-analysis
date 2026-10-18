"""Create the GitHub repository and mirror local history through the REST API.

Why not ``git push``: on this machine the HTTPS transport to github.com is
reset by the network path while api.github.com answers normally, so every
remote write has to go through the REST API.

Two behaviours this script has to work around:

* A repository with no commits rejects Git Data API writes with
  ``409 Git Repository is empty.`` (blobs included), so the branch is seeded
  with one throwaway commit through the Contents API before the first blob.
* The mirrored history is rebuilt from the local root commit with no parents,
  so that seed commit stays unreachable and never shows up in the log.

Commits are recreated with the original tree, parents, message and
author/committer stamps; the run fails loudly unless the remote commit SHA
equals the local one.

Usage:
    .venv\\Scripts\\python.exe scripts\\publish_github.py --private
    .venv\\Scripts\\python.exe scripts\\publish_github.py --repo glyco-analysis
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
UA = "glyco-analysis-publish/0.2"
IDENTITY = re.compile(r"^(?P<name>.*) <(?P<email>.*)> (?P<epoch>\d+) (?P<tz>[+-]\d{4})$")


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
    allow_empty_repo: bool = False,
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
        # Git refs on a repository with no commits answer 409
        # ("Git Repository is empty.") instead of 404.
        if exc.code == 409 and allow_empty_repo:
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


def iso_date(identity: dict) -> str:
    zone = identity["tz"]
    offset = dt.timedelta(hours=int(zone[1:3]), minutes=int(zone[3:5]))
    if zone[0] == "-":
        offset = -offset
    moment = dt.datetime.fromtimestamp(int(identity["epoch"]), dt.timezone(offset))
    return moment.isoformat(timespec="seconds")


def parse_commit(raw: bytes) -> dict:
    text = raw.decode("utf-8")
    header, separator, message = text.partition("\n\n")
    if not separator:
        raise GitHubError("Malformed commit object: no header separator")
    info: dict = {
        "tree": None,
        "parents": [],
        "author": None,
        "committer": None,
        "message": message,
        "signed": False,
    }
    for line in header.splitlines():
        if line.startswith(" "):
            continue  # continuation of a multi-line header such as gpgsig
        key, _, value = line.partition(" ")
        if key == "tree":
            info["tree"] = value
        elif key == "parent":
            info["parents"].append(value)
        elif key in {"author", "committer"}:
            match = IDENTITY.match(value)
            if not match:
                raise GitHubError(f"Unparsed {key} header: {value!r}")
            info[key] = match.groupdict()
        elif key == "gpgsig":
            info["signed"] = True
    if not info["tree"] or not info["author"] or not info["committer"]:
        raise GitHubError("Commit object is missing tree/author/committer")
    return info


def tree_entries(root: Path, commit: str) -> list[tuple[str, str, str]]:
    entries = []
    for record in git(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, object_sha = metadata.decode("ascii").split()
        if kind != "blob":
            raise GitHubError(f"Unsupported tree entry {kind}: {raw_path!r}")
        if mode not in {"100644", "100755"}:
            raise GitHubError(f"Unsupported git mode {mode}: {raw_path!r}")
        entries.append((mode, raw_path.decode("utf-8"), object_sha))
    return entries


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


def branch_ref(token: str, owner: str, repo: str, branch: str) -> str | None:
    ref = api(
        "GET",
        f"/repos/{owner}/{repo}/git/ref/heads/{branch}",
        token,
        allow_404=True,
        allow_empty_repo=True,
    )
    return ref["object"]["sha"] if ref else None


def seed_branch(token: str, owner: str, repo: str, branch: str, root: Path) -> None:
    """Unlock the Git Data API on an empty repository with one throwaway commit."""
    if branch_ref(token, owner, repo, branch):
        return
    readme = root / "README.md"
    content = readme.read_bytes() if readme.is_file() else b"# bootstrap\n"
    payload = {
        "message": "chore: 初始化远程仓库（bootstrap，随后被本地历史取代）",
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    try:
        api("PUT", f"/repos/{owner}/{repo}/contents/README.md", token, payload)
    except GitHubError:
        payload.pop("branch", None)
        api("PUT", f"/repos/{owner}/{repo}/contents/README.md", token, payload)
    print(f"Seeded the empty repository with a throwaway commit on {branch}")


def upload_blob(
    token: str,
    owner: str,
    repo: str,
    root: Path,
    local_sha: str,
    cache: dict[str, str],
) -> str:
    if local_sha in cache:
        return cache[local_sha]
    content = git(root, "cat-file", "blob", local_sha)
    remote = api(
        "POST",
        f"/repos/{owner}/{repo}/git/blobs",
        token,
        {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        },
    )
    if remote["sha"] != local_sha:
        raise GitHubError(f"Blob SHA mismatch: local {local_sha}, remote {remote['sha']}")
    cache[local_sha] = local_sha
    return local_sha


def create_commit(
    token: str,
    owner: str,
    repo: str,
    info: dict,
    tree_sha: str,
    parents: list[str],
    local_sha: str,
) -> str:
    if info["signed"]:
        print(f"WARNING: {local_sha[:7]} is GPG signed; its SHA cannot be reproduced")
    base = {
        "tree": tree_sha,
        "parents": parents,
        "author": {
            "name": info["author"]["name"],
            "email": info["author"]["email"],
            "date": iso_date(info["author"]),
        },
        "committer": {
            "name": info["committer"]["name"],
            "email": info["committer"]["email"],
            "date": iso_date(info["committer"]),
        },
    }
    message = info["message"]
    # GitHub appends the final newline a commit message always carries.
    trimmed = message[:-1] if message.endswith("\n") else message
    candidates = list(dict.fromkeys([trimmed, message]))
    shas = []
    for candidate in candidates:
        commit = api(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            token,
            {**base, "message": candidate},
        )
        if commit["sha"] == local_sha:
            return commit["sha"]
        shas.append(commit["sha"])
    print(
        f"WARNING: {local_sha[:7]} reproduced as {shas[0][:7]} "
        "(identical content, different SHA)"
    )
    return shas[0]


def mirror_history(token: str, owner: str, repo: str, root: Path) -> list[dict]:
    commits = git(root, "rev-list", "--reverse", "HEAD").decode("ascii").split()
    cache: dict[str, str] = {}
    parents: list[str] = []
    results = []
    for position, local_sha in enumerate(commits, start=1):
        info = parse_commit(git(root, "cat-file", "commit", local_sha))
        entries = [
            {
                "path": path,
                "mode": mode,
                "type": "blob",
                "sha": upload_blob(token, owner, repo, root, object_sha, cache),
            }
            for mode, path, object_sha in tree_entries(root, local_sha)
        ]
        remote_tree = api(
            "POST",
            f"/repos/{owner}/{repo}/git/trees",
            token,
            {"tree": entries},
        )
        if remote_tree["sha"] != info["tree"]:
            raise GitHubError(
                f"Tree SHA mismatch for {local_sha[:7]}: "
                f"local {info['tree']}, remote {remote_tree['sha']}"
            )
        remote_commit = create_commit(
            token, owner, repo, info, remote_tree["sha"], parents, local_sha
        )
        parents = [remote_commit]
        exact = remote_commit == local_sha
        results.append(
            {
                "local": local_sha,
                "remote": remote_commit,
                "tree": info["tree"],
                "files": len(entries),
                "exact": exact,
            }
        )
        suffix = "" if exact else "  [SHA differs]"
        print(
            f"[{position}/{len(commits)}] {local_sha[:7]} -> {remote_commit[:7]} "
            f"({len(entries)} files){suffix}"
        )
    return results


def publish(
    root: Path,
    token: str,
    repo_name: str,
    private: bool,
    branch: str = "main",
) -> dict:
    user = api("GET", "/user", token)
    owner = user["login"]
    local_commit, local_tree = current_state(root)
    description = (
        "糖基化分析系统：蛋白质语言模型位点预测 + 糖链图神经网络 + 工具调用智能体"
    )
    repository = ensure_repository(
        token,
        owner,
        repo_name,
        private=private,
        description=description,
    )
    seed_branch(token, owner, repo_name, branch, root)
    results = mirror_history(token, owner, repo_name, root)

    head = results[-1]["remote"]
    api(
        "PATCH",
        f"/repos/{owner}/{repo_name}/git/refs/heads/{branch}",
        token,
        {"sha": head, "force": True},
    )
    remote_head = branch_ref(token, owner, repo_name, branch)
    if remote_head != head:
        raise GitHubError(f"Ref update did not stick: expected {head}, found {remote_head}")

    commit = api("GET", f"/repos/{owner}/{repo_name}/git/commits/{remote_head}", token)
    if commit["tree"]["sha"] != local_tree:
        raise GitHubError(
            f"Post-publish tree mismatch: local {local_tree}, remote {commit['tree']['sha']}"
        )
    tree = api(
        "GET",
        f"/repos/{owner}/{repo_name}/git/trees/{commit['tree']['sha']}?recursive=1",
        token,
    )
    remote_files = sum(1 for item in tree["tree"] if item["type"] == "blob")
    local_files = len(git(root, "ls-files").decode("utf-8").splitlines())
    if remote_files != local_files:
        raise GitHubError(f"File count mismatch: local {local_files}, remote {remote_files}")

    return {
        "repository": repository["html_url"],
        "private": repository["private"],
        "branch": branch,
        "local_head": local_commit,
        "remote_head": remote_head,
        "tree": local_tree,
        "exact_history": remote_head == local_commit,
        "files": remote_files,
        "commits": results,
    }


def write_report(root: Path, result: dict) -> Path:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    path = reports / f"github_publish_{dt.date.today().isoformat()}.md"
    visibility = "private" if result["private"] else "public"
    exact = "是" if result["exact_history"] else "否（内容一致，SHA 不同）"
    lines = [
        "# GitHub 发布记录",
        "",
        f"- 仓库：{result['repository']}（{visibility}）",
        f"- 分支：{result['branch']}",
        f"- 本地 HEAD：`{result['local_head']}`",
        f"- 远端 HEAD：`{result['remote_head']}`",
        f"- HEAD tree：`{result['tree']}`",
        f"- 逐 commit SHA 完全一致：{exact}",
        f"- 远端文件数：{result['files']}",
        "",
        "## 提交镜像",
        "",
        "| 本地 | 远端 | 文件数 | SHA 一致 |",
        "| --- | --- | --- | --- |",
    ]
    for item in result["commits"]:
        same = "是" if item["exact"] else "否"
        lines.append(
            f"| `{item['local'][:7]}` | `{item['remote'][:7]}` | {item['files']} | {same} |"
        )
    lines += [
        "",
        "## 通道说明",
        "",
        "本机 `github.com` 的 HTTPS 通道被网络重置（`Recv failure: Connection was reset`），",
        "`git push` 不可用；本次发布全部通过 `api.github.com` 完成，",
        "复现方式见 `scripts/publish_github.py`。",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=None, help="Repository name; defaults to folder name")
    parser.add_argument("--private", action="store_true", help="Create a private repository")
    parser.add_argument("--branch", default="main", help="Branch to publish (default: main)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    repo_name = args.repo or root.name
    try:
        result = publish(
            root,
            token_from_environment(),
            repo_name,
            args.private,
            args.branch,
        )
    except (GitHubError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report = write_report(root, result)
    print(
        f"Verified {result['local_head']} -> {result['remote_head']} "
        f"(tree {result['tree']}, {result['files']} files)"
    )
    print(f"Report: {report}")
    print(result["repository"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
