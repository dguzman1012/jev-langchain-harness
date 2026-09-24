#!/usr/bin/env python3
"""Classify inbound email with Jev (TypeSafe) via TypeSafeClassifier."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_typesafe import Choice, Noul, Score, TypeSafeClassifier

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

SAMPLE_FILES = {
    "outage": SAMPLES_DIR / "urgent_outage.txt",
    "billing": SAMPLES_DIR / "billing_invoice.txt",
    "spam": SAMPLES_DIR / "spam_noise.txt",
    "sales": SAMPLES_DIR / "calm_sales.txt",
}


def build_classifier() -> TypeSafeClassifier:
    return TypeSafeClassifier(
        questions={
            "category": Choice(
                instructions="Which queue should handle this inbound email?",
                criteria={
                    "billing": "Payments, invoices, refunds, and subscription charges.",
                    "support": "Product issues, outages, bugs, and how-to questions.",
                    "sales": "Pricing, demos, procurement, and expansion interest.",
                    "spam_or_noise": "Spam, scams, irrelevant bulk, or non-actionable noise.",
                    "other": "Legitimate mail that does not fit the categories above.",
                },
            ),
            "urgency": Score(
                instructions="How urgently should we respond or escalate?",
                criteria=[
                    "No rush — can wait days.",
                    "Normal priority — respond within business hours.",
                    "Time-sensitive — same-day response expected.",
                    "Escalate now — active incident or severe customer impact.",
                ],
            ),
            "needs_human": Noul(
                instructions="Should a human review this before any automated reply or action?",
                criteria=None,
            ),
            "actionable": Noul(
                instructions="Is there a clear request or issue we should act on?",
                criteria=None,
            ),
        }
    )


def format_urgency_legend(legend: dict[int, object]) -> str:
    parts = [f"{level}={legend[level]!r}" for level in sorted(legend)]
    return "; ".join(parts)


def print_results(response) -> None:
    category = response.choices["category"]
    urgency = response.scores["urgency"]
    needs_human = response.nouls["needs_human"]
    actionable = response.nouls["actionable"]

    print(f"model: {response.model}")
    print(f"request_id: {response.request_id}")
    print()
    print("category:")
    print(f"  choice: {category.choice}")
    print(f"  confidence: {category.confidence:.3f}")
    for label, prob in sorted(category.probabilities.items(), key=lambda x: -x[1]):
        print(f"  P({label}): {prob:.3f}")
    print()
    print("urgency (score):")
    print(f"  score: {urgency.score:.3f}  (legend: {format_urgency_legend(urgency.legend)})")
    print(f"  confidence: {urgency.confidence:.3f}")
    for level, prob in sorted(urgency.probabilities.items()):
        print(f"  P(level {level}): {prob:.3f}")
    print()
    print("needs_human (noul):")
    print(f"  P(yes): {needs_human.noul:.3f}")
    print()
    print("actionable (noul):")
    print(f"  P(yes): {actionable.noul:.3f}")
    if response.usage.input_tokens is not None:
        print()
        print(
            f"usage: in={response.usage.input_tokens} out={response.usage.output_tokens}"
        )


def resolve_text(args: argparse.Namespace) -> str:
    if args.sample:
        path = SAMPLE_FILES.get(args.sample)
        if path is None:
            valid = ", ".join(sorted(SAMPLE_FILES))
            raise SystemExit(f"Unknown --sample '{args.sample}'. Choose: {valid}")
        return path.read_text(encoding="utf-8")
    if args.text:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit(
        "Provide email text via argument, --file, --sample, or stdin "
        "(e.g. --sample outage)."
    )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Email triage with Jev TypeSafeClassifier (one invoke, four questions)."
    )
    parser.add_argument("text", nargs="?", help="Email body text")
    parser.add_argument("--file", "-f", help="Path to a text file containing the email")
    parser.add_argument(
        "--sample",
        choices=sorted(SAMPLE_FILES.keys()),
        help="Use a fixture from samples/",
    )
    args = parser.parse_args()

    if not os.environ.get("TYPESAFE_API_KEY"):
        print(
            "TYPESAFE_API_KEY is required. Export it or add it to .env "
            "(see .env.example).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    email_text = resolve_text(args)
    classifier = build_classifier()
    response = classifier.invoke(email_text)
    print_results(response)


if __name__ == "__main__":
    main()
