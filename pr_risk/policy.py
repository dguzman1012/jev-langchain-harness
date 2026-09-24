"""Risk policy in code. Thresholds are named constants; Jev does not pick the tier."""

from __future__ import annotations

from pr_risk.types import RiskReason, RiskResult, Signal, Tier

# A data Noul at or above this fires high. Missing a query/model change is
# expensive, so the bar is below 0.5 + a small margin rather than 0.9.
HIGH_SIGNAL_THRESHOLD = 0.55
MODERATE_SIGNAL_THRESHOLD = 0.55

# Noul has no separate confidence (docs: the probability is the certainty).
# We treat 2 * |noul - 0.5| as confidence. Score uses the API's confidence.
LOW_CONFIDENCE = 0.40

MAX_REASONS = 8

_BUMP: dict[Tier, Tier] = {
    "low": "moderate",
    "moderate": "high",
    "high": "high",
}

REVIEW_MEANING: dict[Tier, str] = {
    "high": "Blocked until someone from the data team reviews this PR.",
    "moderate": "Needs 2 approvals from engineers.",
    "low": "Ready to merge after a light review.",
}


def noul_confidence(probability: float) -> float:
    return abs(probability - 0.5) * 2.0


def decide(signals: list[Signal]) -> RiskResult:
    fired_data = [
        s
        for s in signals
        if s.kind == "data" and s.probability >= HIGH_SIGNAL_THRESHOLD
    ]
    fired_moderate = [
        s
        for s in signals
        if s.kind == "moderate" and s.probability >= MODERATE_SIGNAL_THRESHOLD
    ]

    if fired_data:
        tier: Tier = "high"
        deciding = fired_data
    elif fired_moderate:
        tier = "moderate"
        deciding = fired_moderate
    else:
        tier = "low"
        deciding = [s for s in signals if s.kind in ("data", "moderate")]

    bumped = any(s.confidence < LOW_CONFIDENCE for s in deciding)
    if bumped:
        tier = _BUMP[tier]

    reasons = _reasons(signals, tier, deciding, bumped)
    return RiskResult(
        tier=tier, reasons=tuple(reasons), bumped_for_low_confidence=bumped
    )


def _reasons(
    signals: list[Signal],
    tier: Tier,
    deciding: list[Signal],
    bumped: bool,
) -> list[RiskReason]:
    ranked = sorted(
        deciding or signals,
        key=lambda s: (s.probability, s.confidence),
        reverse=True,
    )
    if bumped:
        uncertain = [s for s in deciding if s.confidence < LOW_CONFIDENCE]
        ranked = uncertain + [s for s in ranked if s not in uncertain]
    seen: set[tuple[str, str]] = set()
    out: list[RiskReason] = []
    for signal in ranked:
        key = (signal.file, signal.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            RiskReason(
                file=signal.file,
                signal=signal.name,
                probability=signal.probability,
            )
        )
        if len(out) >= MAX_REASONS:
            break
    if not out and tier == "low":
        out.append(
            RiskReason(
                file="(none)",
                signal="no_reviewable_signals",
                probability=0.0,
            )
        )
    return out
