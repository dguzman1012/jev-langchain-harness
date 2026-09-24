"""Turn a GitHub file list or a unified diff into ChangedFile rows."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from pr_risk.types import ChangedFile

# Stay well inside jev-1.13's 32k state+question budget (models.md).
MAX_PATCH_CHARS = 12_000

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".sql": "sql",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".html": "html",
    ".md": "markdown",
    ".rst": "rst",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".prisma": "prisma",
}

_GIT_DIFF_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def language_for(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return _LANGUAGE_BY_SUFFIX.get(suffix, "text")


def truncate_patch(patch: str) -> str:
    if len(patch) <= MAX_PATCH_CHARS:
        return patch
    return patch[:MAX_PATCH_CHARS] + "\n… [truncated]\n"


def changed_file_from_github(payload: dict) -> ChangedFile:
    path = str(payload.get("filename") or "")
    patch = truncate_patch(str(payload.get("patch") or ""))
    return ChangedFile(
        path=path,
        status=str(payload.get("status") or "modified"),
        additions=int(payload.get("additions") or 0),
        deletions=int(payload.get("deletions") or 0),
        patch=patch,
        language=language_for(path),
    )


def parse_unified_diff(text: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    current_path: str | None = None
    current_status = "modified"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_path, current_status, current_lines
        if current_path is None:
            return
        patch = truncate_patch("".join(current_lines))
        additions = sum(
            1
            for line in current_lines
            if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1
            for line in current_lines
            if line.startswith("-") and not line.startswith("---")
        )
        files.append(
            ChangedFile(
                path=current_path,
                status=current_status,
                additions=additions,
                deletions=deletions,
                patch=patch,
                language=language_for(current_path),
            )
        )
        current_path = None
        current_status = "modified"
        current_lines = []

    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\n")
        header = _GIT_DIFF_RE.match(line)
        if header:
            flush()
            current_path = header.group(2)
            current_status = "modified"
            current_lines = [raw if raw.endswith("\n") else raw + "\n"]
            continue
        if current_path is None:
            continue
        if line.startswith("new file mode"):
            current_status = "added"
        elif line.startswith("deleted file mode"):
            current_status = "removed"
        elif line.startswith("rename from"):
            current_status = "renamed"
        current_lines.append(raw if raw.endswith("\n") else raw + "\n")

    flush()
    return files
