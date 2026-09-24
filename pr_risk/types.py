"""Named data shapes for PR risk classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Tier = Literal["high", "moderate", "low"]
Kind = Literal["data", "moderate", "low", "scope"]
PathEffect = Literal["raise_data", "raise_moderate", "lower_floor"]


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    additions: int
    deletions: int
    patch: str
    language: str


@dataclass(frozen=True)
class FileState:
    """JSON fields sent to Jev for one file (filter first, then ask)."""

    path: str
    language: str
    patch: str
    pr_title: str
    pr_body: str

    def as_json(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Signal:
    file: str
    name: str
    probability: float
    confidence: float
    kind: Kind


@dataclass(frozen=True)
class RiskReason:
    file: str
    signal: str
    probability: float


@dataclass(frozen=True)
class RiskResult:
    tier: Tier
    reasons: tuple[RiskReason, ...]
    bumped_for_low_confidence: bool = False
