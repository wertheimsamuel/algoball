"""Confidence index for surfaced watchlist picks.

This is deliberately conservative. It is NOT "how excited should I be?" and it
is NOT a guarantee of profit. It is a 0-100 readability layer over the math:

- model hit probability for the picked side (most important),
- size of the model-vs-market edge,
- number of books supporting the consensus,
- de-vig method stability.

That means a +EV underdog can show a strong edge but only a modest confidence
index, because it is still more likely to lose than win. That is the honest
distinction a betting dashboard needs.
"""
from __future__ import annotations

from dataclasses import dataclass

from .calibrate import EDGE_FLOOR, MAX_RAW_DIVERGENCE, METHOD_GAP_MAX


@dataclass(frozen=True)
class Confidence:
    index: int
    label: str
    explanation: str


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def confidence_index(
    *,
    pick_prob: float,
    edge_abs: float,
    book_count: int,
    method_gap: float,
    soft_flag: bool = False,
) -> Confidence:
    """Return a conservative 0-100 confidence score for a watchlist pick.

    Parameters
    ----------
    pick_prob:
        The model's estimated probability that the picked side wins.
    edge_abs:
        Absolute model-vs-market divergence, as a probability (0.035 = 3.5pp).
    book_count:
        Number of sportsbook prices in the consensus.
    method_gap:
        Difference between multiplicative and additive de-vig estimates.
    soft_flag:
        True when the raw model probability is outside the soft OOD band.
    """
    hit_score = _clamp(pick_prob)
    edge_score = _clamp((edge_abs - EDGE_FLOOR) / (MAX_RAW_DIVERGENCE - EDGE_FLOOR))
    depth_score = _clamp(book_count / 8.0)
    stability_score = 1.0 - _clamp(method_gap / METHOD_GAP_MAX)

    raw = (
        0.55 * hit_score
        + 0.30 * edge_score
        + 0.10 * depth_score
        + 0.05 * stability_score
    )
    if soft_flag:
        raw -= 0.05

    index = int(round(_clamp(raw) * 100))
    if index >= 72:
        label = "High"
    elif index >= 58:
        label = "Medium"
    elif index >= 45:
        label = "Watch"
    else:
        label = "Longshot"

    explanation = (
        f"{pick_prob * 100:.1f}% model hit probability; "
        f"{edge_abs * 100:.1f}pp market gap; "
        f"{book_count} books in consensus"
    )
    return Confidence(index=index, label=label, explanation=explanation)
