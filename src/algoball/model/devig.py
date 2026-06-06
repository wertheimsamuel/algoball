"""American-odds utilities and de-vigging (ARCHITECTURE.md section 6).

The sportsbook's posted prices include the vig (overround) — the two implied
probabilities sum to more than 1. De-vigging recovers the book's *fair* (no-vig)
probability, which is the single best prior we have for a game.

Method: MULTIPLICATIVE (normalization), pinned on principle. MLB moneylines
show no economically meaningful favorite-longshot bias, so multiplicative
performs as well as the fancier Shin method (Berkowitz/Depken/Gandar 2018).
We *also* compute the additive result (which equals Shin for a 2-way market)
and expose the gap between methods, because on very lopsided lines the methods
disagree by ~1pp — the same magnitude as the edges we are trying to measure —
so that gap drives a fragility guard in the calibration layer.
"""
from __future__ import annotations

from dataclasses import dataclass


def american_to_implied(odds: int) -> float:
    """Convert American odds to the implied (vig-included) probability."""
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return (-odds) / ((-odds) + 100.0)


def american_to_decimal(odds: int) -> float:
    """Convert American odds to decimal odds (payout multiple incl. stake)."""
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / (-odds)


def prob_to_american(p: float) -> int:
    """Convert a fair probability to American odds (the model's own published line).

    >>> prob_to_american(0.5)
    100
    >>> prob_to_american(0.6)
    -150
    """
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be strictly between 0 and 1")
    if p > 0.5:
        return -round(100.0 * p / (1.0 - p))
    return round(100.0 * (1.0 - p) / p)


def devig_multiplicative(imp_home: float, imp_away: float) -> tuple:
    total = imp_home + imp_away
    return imp_home / total, imp_away / total


def devig_additive(imp_home: float, imp_away: float) -> tuple:
    overround = imp_home + imp_away - 1.0
    return imp_home - overround / 2.0, imp_away - overround / 2.0


@dataclass(frozen=True)
class DevigResult:
    """Fair (no-vig) probabilities for a two-way moneyline."""

    fair_home: float
    fair_away: float
    overround: float       # the vig: sum of implied probs minus 1
    method_gap: float      # |multiplicative - additive| on the home side

    @property
    def vig_pct(self) -> float:
        return self.overround * 100.0


def devig_moneyline(home_odds: int, away_odds: int) -> DevigResult:
    """De-vig a two-way moneyline using the multiplicative method."""
    imp_home = american_to_implied(home_odds)
    imp_away = american_to_implied(away_odds)
    mult_home, mult_away = devig_multiplicative(imp_home, imp_away)
    add_home, _ = devig_additive(imp_home, imp_away)
    return DevigResult(
        fair_home=mult_home,
        fair_away=mult_away,
        overround=imp_home + imp_away - 1.0,
        method_gap=abs(mult_home - add_home),
    )
