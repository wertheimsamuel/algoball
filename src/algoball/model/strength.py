"""Team-strength prior (the tournament's winning signal).

The runs model only sees a team's offense and the starting pitcher — it has no
sense of overall team quality or run prevention. This module adds a prior-season
TEAM-STRENGTH estimate from runs scored AND allowed (Pythagorean win expectancy),
turns a matchup into a win probability via log5, and blends it with the runs
model. Verified across 2023-2025 to improve calibration (Brier/log loss) and
accuracy. Lookahead-safe: uses prior-season aggregates only.
"""
from __future__ import annotations

import math

PYTH_EXP: float = 1.83          # Pythagenpat-ish exponent for MLB
G_REGRESS: float = 100.0         # games of .500 to regress team strength toward
HFA_LOGIT: float = 0.145         # home-field nudge in logit space (~0.535 base rate)


def pythagorean(rs_per_game: float, ra_per_game: float, exp: float = PYTH_EXP) -> float:
    if rs_per_game <= 0 and ra_per_game <= 0:
        return 0.5
    rs = rs_per_game ** exp
    ra = ra_per_game ** exp
    return rs / (rs + ra)


def regress_to_500(strength: float, g_reg: float = G_REGRESS, games: float = 162.0) -> float:
    """Shrink a full-season strength toward .500 by adding g_reg average games."""
    return (strength * games + 0.5 * g_reg) / (games + g_reg)


def log5(p_a: float, p_b: float) -> float:
    """Probability A beats B given each side's win expectancy (Bill James log5)."""
    denom = p_a + p_b - 2 * p_a * p_b
    if denom <= 0:
        return 0.5
    return (p_a - p_a * p_b) / denom


def _logit(p: float) -> float:
    p = min(1 - 1e-9, max(1e-9, p))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def prior_winprob(
    home_rs: float, home_ra: float,
    away_rs: float, away_ra: float,
    hfa_logit: float = HFA_LOGIT,
    g_reg: float = G_REGRESS,
) -> float:
    """Home win probability from prior-season team strength alone."""
    sh = regress_to_500(pythagorean(home_rs, home_ra), g_reg)
    sa = regress_to_500(pythagorean(away_rs, away_ra), g_reg)
    base = log5(sh, sa)
    return _sigmoid(_logit(base) + hfa_logit)


def blend(p_runs: float, p_prior: float, w: float) -> float:
    """Blend the runs-model probability with the team-strength prior (w = prior weight)."""
    return (1.0 - w) * p_runs + w * p_prior
