"""Expected-runs transform (ARCHITECTURE.md section 5 — the small new math).

Turns simple, free pre-game stats into each side's expected runs, which then
feed the win-probability formula. Every factor is centered on 1.0, so a neutral
matchup (league-average offense vs a league-average starter in a neutral park)
returns the league run rate, and only deviations move the number.

    expected_runs = league_rpg
                    * team_offense_factor          (team runs/game vs league)
                    * opposing_starter_suppression  (their starter's FIP vs league,
                                                      diluted by the bullpen share)
                    * park_factor

The starter only throws ~60% of innings (STARTER_IP_SHARE); the rest is treated
as a league-average bullpen, so even an ace cannot suppress the whole game.
"""
from __future__ import annotations

from ..config import STARTER_IP_SHARE


def starter_suppression(opp_starter_fip: float, league_fip: float) -> float:
    """How much the opposing starter (+ avg bullpen) scales run scoring."""
    starter = opp_starter_fip / league_fip
    return STARTER_IP_SHARE * starter + (1.0 - STARTER_IP_SHARE) * 1.0


def expected_runs(
    league_rpg: float,
    team_offense_factor: float,
    opp_starter_fip: float,
    league_fip: float,
    park: float = 1.0,
) -> float:
    return (
        league_rpg
        * team_offense_factor
        * starter_suppression(opp_starter_fip, league_fip)
        * park
    )
