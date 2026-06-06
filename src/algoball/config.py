"""Model constants and park factors (kept in one place, hardcoded for v1).

These are the few magic numbers the model needs. Backtesting tunes them; until
then they are sensible league-average defaults. Park factors are run-scoring
multipliers centered on 1.0 (>1 = hitter-friendly), keyed by venue name; unknown
venues fall back to neutral.
"""
from __future__ import annotations

# --- expected-runs transform ---
STARTER_IP_SHARE: float = 0.60
"""Share of a game's innings thrown by the starter; the rest is league-average bullpen."""

FIP_REGRESS_IP: float = 50.0
"""Innings of league-average FIP to regress a pitcher's prior-season FIP toward (small-sample guard)."""

LEAGUE_FIP_FALLBACK: float = 4.10
"""League-average FIP used as the constant and as a fallback for pitchers with no prior data."""

FIP_CONSTANT: float = 3.10
"""cFIP in FIP = (13*HR + 3*(BB+HBP) - 2*K)/IP + cFIP (computed ourselves from one API call)."""

PRIOR_BLEND_W: float = 0.60
"""Weight on the prior-season team-strength (Pythagorean) prior when blended with the
runs model: p_final = (1-W)*p_runs + W*p_prior. Chosen by multi-season backtest
(2023/2024/2025/2026, 7,757 games) as the robust, net-positive-everywhere value; see
src/algoball/model/strength.py and scripts/validate_improved.py."""

# --- park factors (run multipliers, 1.0 = neutral), by venue name ---
PARK_FACTORS = {
    "Coors Field": 1.12,
    "Fenway Park": 1.04,
    "Great American Ball Park": 1.04,
    "Chase Field": 1.03,
    "Globe Life Field": 1.02,
    "Oriole Park at Camden Yards": 1.01,
    "Wrigley Field": 1.01,
    "Yankee Stadium": 1.01,
    "Citizens Bank Park": 1.01,
    "Rate Field": 1.01,
    "Guaranteed Rate Field": 1.01,
    "Kauffman Stadium": 1.00,
    "Truist Park": 1.00,
    "Nationals Park": 1.00,
    "Target Field": 1.00,
    "Rogers Centre": 1.00,
    "American Family Field": 1.00,
    "Dodger Stadium": 0.99,
    "Busch Stadium": 0.99,
    "Comerica Park": 0.99,
    "Angel Stadium": 0.99,
    "Daikin Park": 0.99,
    "Minute Maid Park": 0.99,
    "Progressive Field": 0.99,
    "PNC Park": 0.98,
    "Citi Field": 0.98,
    "Citizens Bank": 1.01,
    "loanDepot park": 0.97,
    "Oracle Park": 0.97,
    "Petco Park": 0.96,
    "T-Mobile Park": 0.95,
    "Sutter Health Park": 0.99,
    "George M. Steinbrenner Field": 1.02,
}
DEFAULT_PARK: float = 1.00
