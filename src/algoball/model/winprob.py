"""Win-probability model (ARCHITECTURE.md section 5).

Deterministic, no random simulation:

    P(home win) = Phi( (E[runs_home] - E[runs_away] + HFA) / SD_DIFF )

where Phi is the standard-normal CDF, SD_DIFF is the standard deviation of a
single MLB game's run differential, and HFA is home-field advantage expressed
as a small run nudge.

SD_DIFF is anchored to the *verified* pooled single-game run variance
(variance/mean ~ 2.1, i.e. overdispersed) and the average margin of victory
(~3.3 runs): SD_DIFF ~= 4.3. Round 2's fact-check corrected an earlier design
that used a far-too-tight spread (variance/mean ~ 1.4); a too-tight spread is
exactly the machinery that turns a small run edge into a fake 81% blowout, so
this constant is load-bearing for calibration.

A deterministic closed form (rather than a 10k-draw Monte Carlo) is chosen on
purpose: identical answers across the day's multiple runs, no RNG seed to
manage, and trivially unit-testable.
"""
from __future__ import annotations

import math

# --- Verified constants (see docs/VERIFICATION.md) ---------------------------
SD_DIFF: float = 4.3
"""Std dev of a single game's (home - away) run differential."""

HFA_RUNS: float = 0.37
"""Home-field advantage as an expected-run-diff nudge (~+3.4pp; Elo ~24 pts)."""


def standard_normal_cdf(x: float) -> float:
    """Phi(x): probability a standard normal draw is <= x."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def win_probability(exp_run_diff: float, sd_diff: float = SD_DIFF) -> float:
    """Home win probability from an expected home-minus-away run differential.

    >>> round(win_probability(0.0), 4)   # even matchup, no HFA baked in here
    0.5
    """
    if sd_diff <= 0:
        raise ValueError("sd_diff must be positive")
    return standard_normal_cdf(exp_run_diff / sd_diff)


def win_probability_from_runs(
    exp_runs_home: float,
    exp_runs_away: float,
    *,
    include_hfa: bool = True,
    sd_diff: float = SD_DIFF,
) -> float:
    """Home win probability from each side's expected runs (HFA optional)."""
    diff = exp_runs_home - exp_runs_away + (HFA_RUNS if include_hfa else 0.0)
    return win_probability(diff, sd_diff)


def run_diff_for_probability(p: float, sd_diff: float = SD_DIFF) -> float:
    """Inverse map: the run differential implied by a win probability.

    Handy for sanity checks — e.g. it shows that an 81% home prob requires a
    ~3.8-run pregame edge, which essentially never exists, which is *why* 0.81
    is treated as a malfunction rather than a real read.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    # Inverse standard-normal CDF via the inverse error function.
    z = math.sqrt(2.0) * _erfinv(2.0 * p - 1.0)
    return z * sd_diff


def _erfinv(y: float) -> float:
    """Inverse error function (Newton refinement on a rational seed)."""
    if y <= -1.0 or y >= 1.0:
        raise ValueError("erfinv domain is (-1, 1)")
    # Winitzki approximation as a seed, then a couple of Newton steps.
    a = 0.147
    ln = math.log(1.0 - y * y)
    t = 2.0 / (math.pi * a) + ln / 2.0
    x = math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), y)
    for _ in range(3):
        x -= (math.erf(x) - y) / (2.0 / math.sqrt(math.pi) * math.exp(-x * x))
    return x
