"""Narrow Jev questions for one file. Policy stays in code."""

from __future__ import annotations

from langchain_typesafe import Noul, NoulCriteria, Score, TypeSafeClassifier

from pr_risk.policy import noul_confidence
from pr_risk.types import FileState, Signal

# Pin the version we tuned thresholds against (models.md aliases move).
JEV_MODEL = "jev-1.13.0"

NOUL_QUESTIONS: dict[str, tuple[str, str, str]] = {
    "changes_db_query": (
        "data",
        "Does `patch` add or change a database query in this file?",
        "Raw SQL, an ORM query, a query builder, or a repository method that loads or writes records.",
    ),
    "changes_data_model_or_migration": (
        "data",
        "Does `patch` change a data model, schema, or migration in this file?",
        "Model/schema fields, ORM mappings, or a database migration.",
    ),
    "changes_business_logic": (
        "data",
        "Does `patch` change business logic in this file?",
        "Domain rules, pricing, permissions, eligibility, or calculations that decide what the product does.",
    ),
    "changes_api_endpoint": (
        "moderate",
        "Does `patch` add or change an HTTP API route or endpoint handler in this file?",
        "A new or edited route, controller, or handler that exposes an API.",
    ),
    "only_ui_style_or_copy": (
        "low",
        "Is `patch` only a frontend style, copy, or button-level change?",
        "Colors, spacing, labels, or static UI with no new behavior, queries, or data models.",
    ),
    "only_tests_or_docs": (
        "low",
        "Is `patch` only tests, docs, or comments?",
        "Tests, markdown, or comments with no production runtime behavior change.",
    ),
}

FILE_QUESTIONS = {
    name: Noul(
        instructions=instructions,
        criteria=NoulCriteria(
            true=yes_means,
            false="The patch does not do that.",
        ),
    )
    for name, (_kind, instructions, yes_means) in NOUL_QUESTIONS.items()
}
FILE_QUESTIONS["scope"] = Score(
    instructions="How large is the change in `patch` for this one file?",
    criteria=[
        "Tiny: a few lines and no new behavior.",
        "Small: a localized edit with limited impact.",
        "Moderate: a new flow or several coordinated edits.",
        "Large: a wide refactor or many moving parts.",
    ],
)


def build_classifier() -> TypeSafeClassifier:
    return TypeSafeClassifier(model=JEV_MODEL, questions=FILE_QUESTIONS)


def signals_from_response(path: str, response) -> list[Signal]:
    out: list[Signal] = []
    for name, (_kind, _instructions, _yes) in NOUL_QUESTIONS.items():
        noul = response.nouls[name].noul
        out.append(
            Signal(
                file=path,
                name=name,
                probability=noul,
                confidence=noul_confidence(noul),
                kind=_kind,  # type: ignore[arg-type]
            )
        )
    scope = response.scores["scope"]
    # Normalize the 0–3 score onto 0–1 so reasons stay comparable.
    out.append(
        Signal(
            file=path,
            name="scope",
            probability=scope.score / 3.0,
            confidence=scope.confidence,
            kind="scope",
        )
    )
    return out


def ask_file(classifier: TypeSafeClassifier, state: FileState) -> list[Signal]:
    response = classifier.invoke(state.as_json())
    return signals_from_response(state.path, response)
