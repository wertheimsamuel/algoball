"""Calibration guardrails (ARCHITECTURE.md section 6).

This module's only job is to make the old +34.4% edge / 81.2% win-prob / 19
bets-a-day failure *structurally impossible*. No single guard is trusted, and
the most diagnostic guards fire on the RAW model output, at the source, before
anything is blended or displayed.

Decided band (docs/VERIFICATION.md section C):

    PROB_OOD_BAND        = (0.20, 0.80)  hard suppress + alarm on the RAW model prob
    PROB_OOD_SOFT_BAND   = (0.28, 0.72)  non-suppressing investigative flag
    MAX_RAW_DIVERGENCE   = 0.10          PRIMARY catcher (model vs fair market)
    EDGE_FLOOR           = 0.015         below this there is no meaningful edge
    METHOD_GAP_MAX       = 0.01          de-vig fragility guard (lopsided lines)
    SHRINK_W             = 0.0           model weight in the final blend (~0 until proven)
    PROB_CLAMP           = (0.15, 0.85)  backstop clamp on the final blended prob
    MAX_SURFACED_PER_DAY = 3             sanity cap on how many games can surface

Why these specifically:
  - A correctly-calibrated MLB win prob essentially never exceeds ~0.72-0.74,
    so the 0.80 hard ceiling never suppresses a legitimate read yet catches the
    0.81 bug at the source.
  - The old design's bug was a 34-point model-vs-market DIVERGENCE, so the
    divergence guard (>0.10) is the primary catcher, redundant with the OOD band.
  - SHRINK_W is 0 in v1: the model has not yet earned the right to disagree with
    the market, so the final probability used for any decision IS the market.
    Surfaced games are recorded as "model-vs-market divergences" to be graded
    later by closing-line value — they are not presented as confident bets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

from .devig import DevigResult

# --- Constants ---------------------------------------------------------------
PROB_OOD_BAND = (0.20, 0.80)
PROB_OOD_SOFT_BAND = (0.28, 0.72)
MAX_RAW_DIVERGENCE = 0.10
EDGE_FLOOR = 0.015
METHOD_GAP_MAX = 0.01
SHRINK_W = 0.0
PROB_CLAMP = (0.15, 0.85)
MAX_SURFACED_PER_DAY = 3


class Status(str, Enum):
    SURFACED = "surfaced"               # a small, sane divergence worth recording
    NO_EDGE = "no_edge"                 # the normal, common result
    SUPPRESSED_BUG = "suppressed_bug"   # output looks broken -> kill + alarm
    SUPPRESSED_FRAGILE = "suppressed_fragile"  # de-vig unreliable on this line


@dataclass
class GameVerdict:
    status: Status
    p_model: float
    fair_market: float
    divergence: float          # p_model - fair_market
    p_final: float             # market-anchored final prob (what a decision uses)
    soft_flag: bool = False    # legitimate heavy favorite, surfaced not suppressed
    alarm: bool = False        # something looked broken; a human should look
    reasons: List[str] = field(default_factory=list)

    @property
    def edge_pct(self) -> float:
        return self.divergence * 100.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def evaluate_game(p_model: float, devig: DevigResult, *, side: str = "home") -> GameVerdict:
    """Run a single game through the full guardrail stack.

    `side` selects which side's fair market prob the model is compared against.
    """
    fair = devig.fair_home if side == "home" else devig.fair_away
    divergence = p_model - fair
    p_final = _clamp(SHRINK_W * p_model + (1.0 - SHRINK_W) * fair, *PROB_CLAMP)

    def verdict(status: Status, reason: str, *, alarm: bool = False, soft: bool = False) -> GameVerdict:
        return GameVerdict(
            status=status,
            p_model=p_model,
            fair_market=fair,
            divergence=divergence,
            p_final=p_final,
            soft_flag=soft,
            alarm=alarm,
            reasons=[reason],
        )

    # 1) Raw out-of-distribution guard — fires at the source, before anything else.
    lo, hi = PROB_OOD_BAND
    if not (lo <= p_model <= hi):
        return verdict(
            Status.SUPPRESSED_BUG,
            f"raw model prob {p_model:.3f} is outside the hard OOD band {PROB_OOD_BAND}; "
            f"a calibrated MLB win prob never legitimately reaches this — treated as a malfunction",
            alarm=True,
        )

    # 2) Model-vs-market divergence guard — the primary bug-catcher.
    if abs(divergence) > MAX_RAW_DIVERGENCE:
        return verdict(
            Status.SUPPRESSED_BUG,
            f"model-vs-market divergence {divergence:+.3f} exceeds +/-{MAX_RAW_DIVERGENCE:.2f}; "
            f"a free-data model that disagrees with the market this much is wrong, not right",
            alarm=True,
        )

    # 3) De-vig fragility guard — the line is too steep to de-vig reliably.
    if devig.method_gap > METHOD_GAP_MAX:
        return verdict(
            Status.SUPPRESSED_FRAGILE,
            f"de-vig methods disagree by {devig.method_gap:.3f} (> {METHOD_GAP_MAX}); "
            f"the fair price on this lopsided line is too uncertain to trust",
        )

    # 4) Edge floor — below this the disagreement is noise (the common case).
    if abs(divergence) < EDGE_FLOOR:
        return verdict(
            Status.NO_EDGE,
            f"divergence {divergence:+.3f} is below the {EDGE_FLOOR:.3f} edge floor — no qualifying edge",
        )

    # 5) Surface it, with a soft flag if it is a legitimate heavy favorite.
    s_lo, s_hi = PROB_OOD_SOFT_BAND
    soft = not (s_lo <= p_model <= s_hi)
    reason = (
        f"sane divergence {divergence:+.3f} ({divergence * 100:+.1f}pp) within bounds — "
        f"recorded as a model-vs-market divergence to be graded by CLV"
    )
    if soft:
        reason += "; raw prob outside soft band (heavy favorite) — surfaced, not suppressed"
    v = verdict(Status.SURFACED, reason, soft=soft)
    return v
