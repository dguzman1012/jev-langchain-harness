"""Parse files, apply path rules, ask Jev, decide the tier in code."""

from __future__ import annotations

from collections.abc import Callable

from pr_risk.jev import ask_file, build_classifier
from pr_risk.policy import decide
from pr_risk.rules import is_trivial, path_signals, should_skip
from pr_risk.types import ChangedFile, FileState, RiskResult, Signal


def classify_files(
    files: list[ChangedFile],
    *,
    pr_title: str = "",
    pr_body: str = "",
    ask: Callable[[FileState], list[Signal]] | None = None,
) -> RiskResult:
    """Classify a PR. `ask` is injectable so tests never call Jev."""
    ask_fn = ask
    classifier = None
    if ask_fn is None:
        classifier = build_classifier()

        def ask_fn(state: FileState) -> list[Signal]:
            return ask_file(classifier, state)

    signals: list[Signal] = []
    for file in files:
        if should_skip(file):
            continue
        signals.extend(path_signals(file.path))
        if is_trivial(file):
            continue
        state = FileState(
            path=file.path,
            language=file.language,
            patch=file.patch,
            pr_title=pr_title,
            pr_body=pr_body,
        )
        signals.extend(ask_fn(state))
    return decide(signals)
