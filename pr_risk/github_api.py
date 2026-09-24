"""GitHub API: PR files, risk labels, and one sticky comment."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from pr_risk.parse import changed_file_from_github
from pr_risk.policy import REVIEW_MEANING
from pr_risk.types import ChangedFile, RiskResult, Tier

GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
STICKY_MARKER = "<!-- pr-risk-classifier -->"
RISK_LABELS: dict[Tier, tuple[str, str]] = {
    "high": ("B60205", "Must not merge without data-team review."),
    "moderate": ("D93F0B", "Needs 2 engineer approvals."),
    "low": ("0E8A16", "Ready to merge after a light review."),
}
PR_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


class GitHubError(RuntimeError):
    pass


def parse_pr_url(url: str) -> tuple[str, str, int]:
    match = PR_URL_RE.fullmatch(url.strip().rstrip("/"))
    if match is None:
        raise SystemExit(f"Not a GitHub pull request URL: {url}")
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pr-risk-classifier",
    }


def fetch_pr_files(
    owner: str, repo: str, number: int, token: str
) -> tuple[str, str, list[ChangedFile]]:
    session = requests.Session()
    session.headers.update(_headers(token))
    pr = _get(session, f"/repos/{owner}/{repo}/pulls/{number}")
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    files: list[ChangedFile] = []
    page = 1
    while True:
        batch = _get(
            session,
            f"/repos/{owner}/{repo}/pulls/{number}/files",
            params={"per_page": 100, "page": page},
        )
        if not isinstance(batch, list) or not batch:
            break
        files.extend(changed_file_from_github(item) for item in batch)
        if len(batch) < 100:
            break
        page += 1
    return title, body, files


def apply_result(
    owner: str, repo: str, number: int, token: str, result: RiskResult
) -> None:
    session = requests.Session()
    session.headers.update(_headers(token))
    _ensure_labels(session, owner, repo)
    _set_risk_label(session, owner, repo, number, result.tier)
    _upsert_comment(session, owner, repo, number, result)


def _ensure_labels(session: requests.Session, owner: str, repo: str) -> None:
    for tier, (color, description) in RISK_LABELS.items():
        name = f"risk:{tier}"
        encoded = quote(name, safe="")
        url = f"{GITHUB_API}/repos/{owner}/{repo}/labels/{encoded}"
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            continue
        if response.status_code != 404:
            raise GitHubError(f"GET {url} -> {response.status_code} {response.text}")
        created = session.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/labels",
            json={"name": name, "color": color, "description": description},
            timeout=30,
        )
        if created.status_code not in (200, 201):
            raise GitHubError(
                f"create label {name} -> {created.status_code} {created.text}"
            )


def _set_risk_label(
    session: requests.Session, owner: str, repo: str, number: int, tier: Tier
) -> None:
    issue = _get(session, f"/repos/{owner}/{repo}/issues/{number}")
    current = [str(label["name"]) for label in issue.get("labels", [])]
    stale = [name for name in current if name.startswith("risk:") and name != f"risk:{tier}"]
    for name in stale:
        encoded = quote(name, safe="")
        deleted = session.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}/labels/{encoded}",
            timeout=30,
        )
        if deleted.status_code not in (200, 204):
            raise GitHubError(
                f"remove label {name} -> {deleted.status_code} {deleted.text}"
            )
    wanted = f"risk:{tier}"
    if wanted not in current:
        added = session.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}/labels",
            json={"labels": [wanted]},
            timeout=30,
        )
        if added.status_code not in (200, 201):
            raise GitHubError(
                f"add label {wanted} -> {added.status_code} {added.text}"
            )


def _upsert_comment(
    session: requests.Session, owner: str, repo: str, number: int, result: RiskResult
) -> None:
    comments = _list_issue_comments(session, owner, repo, number)
    body = format_comment(result)
    existing = next(
        (c for c in comments if STICKY_MARKER in str(c.get("body") or "")),
        None,
    )
    if existing is None:
        created = session.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}/comments",
            json={"body": body},
            timeout=30,
        )
        if created.status_code not in (200, 201):
            raise GitHubError(
                f"create comment -> {created.status_code} {created.text}"
            )
        return
    updated = session.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{existing['id']}",
        json={"body": body},
        timeout=30,
    )
    if updated.status_code != 200:
        raise GitHubError(
            f"update comment -> {updated.status_code} {updated.text}"
        )


def _list_issue_comments(
    session: requests.Session, owner: str, repo: str, number: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _get(
            session,
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            params={"per_page": 100, "page": page},
        )
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def format_comment(result: RiskResult) -> str:
    lines = [
        STICKY_MARKER,
        f"## PR risk: `{result.tier}`",
        "",
        REVIEW_MEANING[result.tier],
        "",
    ]
    if result.bumped_for_low_confidence:
        lines.append(
            "Tier was raised one step because a deciding signal had low confidence."
        )
        lines.append("")
    lines.append("### Why")
    lines.append("")
    if not result.reasons:
        lines.append("No reviewable signals.")
    else:
        for reason in result.reasons:
            lines.append(
                f"- `{reason.file}` — `{reason.signal}` "
                f"(p={reason.probability:.3f})"
            )
    lines.append("")
    lines.append(
        "_Classified by TypeSafe Jev. Re-runs update this comment in place._"
    )
    return "\n".join(lines)


def load_github_event(path: str) -> tuple[str, str, int, str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    owner = (repo.get("owner") or {}).get("login") or ""
    name = repo.get("name") or ""
    number = int(pr.get("number") or 0)
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    if not owner or not name or not number:
        raise SystemExit("GITHUB_EVENT_PATH is missing pull_request or repository.")
    return owner, name, number, title, body


def _get(
    session: requests.Session, path: str, params: dict[str, Any] | None = None
) -> Any:
    url = f"{GITHUB_API}{path}"
    response = session.get(url, params=params, timeout=30)
    if response.status_code != 200:
        raise GitHubError(f"GET {url} -> {response.status_code} {response.text}")
    return response.json()
