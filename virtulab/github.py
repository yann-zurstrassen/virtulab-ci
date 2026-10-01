"""GitHub Actions integration: annotations, step outputs, job summary, PR comment."""

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def in_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def workspace() -> Path:
    return Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()


def repo_path(root: Path, path: str) -> str:
    """Path relative to the repository checkout, as GitHub annotations expect."""
    absolute = (root / path).resolve()
    try:
        return absolute.relative_to(workspace()).as_posix()
    except ValueError:
        return path


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def annotate(level: str, message: str, file: str | None = None, line: int | None = None,
             title: str | None = None) -> None:
    """Emit an ::error / ::warning workflow command (rendered inline on the PR diff)."""
    props = []
    if file:
        props.append(f"file={_escape_property(file)}")
    if line:
        props.append(f"line={line}")
    if title:
        props.append(f"title={_escape_property(title)}")
    prop_text = (" " + ",".join(props)) if props else ""
    print(f"::{level}{prop_text}::{_escape_data(message)}", flush=True)


def group(title: str) -> None:
    if in_actions():
        print(f"::group::{title}", flush=True)
    else:
        print(f"── {title} " + "─" * max(0, 60 - len(title)), flush=True)


def end_group() -> None:
    if in_actions():
        print("::endgroup::", flush=True)


def set_outputs(outputs: dict[str, object]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in outputs.items():
            text = "" if value is None else str(value)
            delimiter = f"ghadelim_{uuid.uuid4().hex}"
            fh.write(f"{key}<<{delimiter}\n{text}\n{delimiter}\n")


def append_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def pull_request_number() -> int | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).is_file():
        return None
    event = json.loads(Path(event_path).read_text())
    pr = event.get("pull_request")
    return pr.get("number") if pr else None


class GitHubAPI:
    def __init__(self, token: str, repository: str, api_url: str = "https://api.github.com"):
        self.token = token
        self.repository = repository
        self.api_url = api_url.rstrip("/")

    def request(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            f"{self.api_url}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "virtulab-ci",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"null")

    def upsert_comment(self, issue: int, marker: str, body: str) -> str:
        """Update the comment containing `marker`, or create it. Returns its URL."""
        base = f"/repos/{self.repository}/issues"
        page = 1
        while True:
            comments = self.request("GET", f"{base}/{issue}/comments?per_page=100&page={page}")
            for comment in comments:
                if marker in (comment.get("body") or ""):
                    updated = self.request("PATCH", f"{base}/comments/{comment['id']}",
                                           {"body": body})
                    return updated["html_url"]
            if len(comments) < 100:
                break
            page += 1
        created = self.request("POST", f"{base}/{issue}/comments", {"body": body})
        return created["html_url"]


def post_pr_comment(body: str, marker: str, token: str) -> None:
    issue = pull_request_number()
    repository = os.environ.get("GITHUB_REPOSITORY")
    if issue is None or not repository:
        return
    if not token:
        annotate("warning", "No github_token available; skipping the PR comment.")
        return
    api = GitHubAPI(token, repository, os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    try:
        url = api.upsert_comment(issue, marker, body)
        print(f"💬 PR report: {url}", flush=True)
    except urllib.error.HTTPError as exc:
        hint = (" Grant `pull-requests: write` in the workflow (fork PRs get read-only tokens)."
                if exc.code in (403, 404) else "")
        annotate("warning", f"Could not post the PR comment: HTTP {exc.code}.{hint}")
    except urllib.error.URLError as exc:
        annotate("warning", f"Could not post the PR comment: {exc.reason}")
