"""Line shopping & soft-line detection (ARCHITECTURE.md section 5).

This is the one honest "beat the book" mechanism. A model run near game time
cannot beat the sharp closing price — but slower/softer books do not update
instantly. When the sharp consensus has moved but a soft book has not caught up,
that stale price is a genuine, momentary inefficiency.

Given the SAME game priced by multiple books, we:
  1. compute each book's fair (de-vigged) probability and take the consensus,
  2. find the best available price per side (the highest payout a bettor can get),
  3. flag any book offering a side at a price softer than the consensus fair price
     by more than SOFT_DELTA — i.e. a better-than-fair number that is exploitable
     until that book moves.

Catching these requires continuously-updating odds (the always-on phase), which
is exactly why the hosted design polls books on an interval rather than once a day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .devig import american_to_implied, devig_moneyline

SOFT_DELTA: float = 0.02
"""How far below consensus fair prob a book's implied prob must be to be 'soft'."""


@dataclass(frozen=True)
class BookLine:
    book: str
    home_odds: int
    away_odds: int


@dataclass
class SoftFlag:
    book: str
    side: str          # "home" or "away"
    offered_odds: int
    offered_implied: float
    consensus_fair: float
    softness: float    # consensus_fair - offered_implied (positive = exploitable)


@dataclass
class ShopResult:
    consensus_fair_home: float
    consensus_fair_away: float
    best_home_book: str
    best_home_odds: int
    best_away_book: str
    best_away_odds: int
    soft_flags: List[SoftFlag] = field(default_factory=list)


def _median(values: List[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def shop_lines(lines: List[BookLine], soft_delta: float = SOFT_DELTA) -> Optional[ShopResult]:
    """Find best prices and soft lines across books for one game."""
    if not lines:
        return None

    fair_homes = [devig_moneyline(l.home_odds, l.away_odds).fair_home for l in lines]
    fair_aways = [1.0 - fh for fh in fair_homes]
    consensus_home = _median(fair_homes)
    consensus_away = _median(fair_aways)

    # Best price for the bettor = lowest implied probability = highest payout.
    best_home = min(lines, key=lambda l: american_to_implied(l.home_odds))
    best_away = min(lines, key=lambda l: american_to_implied(l.away_odds))

    soft_flags: List[SoftFlag] = []
    for l in lines:
        imp_home = american_to_implied(l.home_odds)
        if consensus_home - imp_home > soft_delta:
            soft_flags.append(
                SoftFlag(l.book, "home", l.home_odds, imp_home, consensus_home,
                         consensus_home - imp_home)
            )
        imp_away = american_to_implied(l.away_odds)
        if consensus_away - imp_away > soft_delta:
            soft_flags.append(
                SoftFlag(l.book, "away", l.away_odds, imp_away, consensus_away,
                         consensus_away - imp_away)
            )

    return ShopResult(
        consensus_fair_home=consensus_home,
        consensus_fair_away=consensus_away,
        best_home_book=best_home.book,
        best_home_odds=best_home.home_odds,
        best_away_book=best_away.book,
        best_away_odds=best_away.away_odds,
        soft_flags=soft_flags,
    )
