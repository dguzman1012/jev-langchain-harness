"""Deterministic path rules. Edit the tables at the top of this module."""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

from pr_risk.types import ChangedFile, PathEffect, Signal

# Skip lockfiles, generated output, and binaries before Jev sees them.
SKIP_PATH_PATTERNS: tuple[str, ...] = (
    "**/uv.lock",
    "**/package-lock.json",
    "**/yarn.lock",
    "**/pnpm-lock.yaml",
    "**/Cargo.lock",
    "**/poetry.lock",
    "**/Gemfile.lock",
    "**/composer.lock",
    "**/go.sum",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    "**/dist/**",
    "**/build/**",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.webp",
    "**/*.ico",
    "**/*.pdf",
    "**/*.woff",
    "**/*.woff2",
    "**/*.ttf",
    "**/*.eot",
    "**/*.zip",
    "**/*.gz",
    "**/*.wasm",
)

BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".zip",
        ".gz",
        ".wasm",
        ".bin",
        ".exe",
        ".dll",
        ".so",
    }
)

# First matching effect wins. raise_data is listed before raise_moderate
# and lower_floor so a migration README still counts as data.
PATH_RULES: tuple[tuple[str, tuple[str, ...], PathEffect], ...] = (
    (
        "migrations",
        ("**/migrations/**", "**/alembic/versions/**"),
        "raise_data",
    ),
    ("sql", ("**/*.sql",), "raise_data"),
    (
        "schema_models",
        (
            "**/models.py",
            "**/models/**",
            "**/schema.py",
            "**/schemas.py",
            "**/schema/**",
            "**/prisma/schema.prisma",
        ),
        "raise_data",
    ),
    (
        "api_routes",
        ("**/api/**", "**/routes/**", "**/endpoints/**", "**/views.py"),
        "raise_moderate",
    ),
    (
        "tests",
        (
            "**/tests/**",
            "**/test_*.py",
            "**/*_test.py",
            "**/*.test.ts",
            "**/*.test.tsx",
            "**/*.spec.ts",
            "**/*.spec.tsx",
        ),
        "lower_floor",
    ),
    ("docs", ("**/*.md", "**/*.rst", "**/docs/**"), "lower_floor"),
    (
        "styles",
        ("**/*.css", "**/*.scss", "**/*.sass", "**/*.less"),
        "lower_floor",
    ),
)

PATH_RULE_PROBABILITY = 1.0
PATH_RULE_CONFIDENCE = 1.0

_EFFECT_KIND = {
    "raise_data": "data",
    "raise_moderate": "moderate",
    "lower_floor": "low",
}


def path_matches(path: str, pattern: str) -> bool:
    """Match repo paths against `**/dir/**` and `**/*.ext` globs.

    pathlib's `**` is too strict on root-level files and nested folders
    (`README.md` vs `**/*.md`, `src/api/routes/x.py` vs `**/api/**`).
    """
    path = path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    rest = pattern[3:] if pattern.startswith("**/") else pattern
    if rest.endswith("/**"):
        folder = rest[:-3]
        return (
            path == folder
            or path.startswith(f"{folder}/")
            or f"/{folder}/" in f"/{path}"
        )
    if "/" in rest:
        return path == rest or path.endswith(f"/{rest}")
    return fnmatch.fnmatch(name, rest) or fnmatch.fnmatch(path, rest)


def matching_rule(path: str) -> tuple[str, PathEffect] | None:
    for name, patterns, effect in PATH_RULES:
        if any(path_matches(path, pattern) for pattern in patterns):
            return name, effect
    return None


def should_skip(file: ChangedFile) -> bool:
    suffix = PurePosixPath(file.path).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return True
    if any(path_matches(file.path, pattern) for pattern in SKIP_PATH_PATTERNS):
        return True
    if "\x00" in file.patch:
        return True
    return False


def is_trivial(file: ChangedFile) -> bool:
    return not file.patch.strip()


def path_signals(path: str) -> list[Signal]:
    match = matching_rule(path)
    if match is None:
        return []
    name, effect = match
    return [
        Signal(
            file=path,
            name=f"path:{name}",
            probability=PATH_RULE_PROBABILITY,
            confidence=PATH_RULE_CONFIDENCE,
            kind=_EFFECT_KIND[effect],  # type: ignore[arg-type]
        )
    ]
