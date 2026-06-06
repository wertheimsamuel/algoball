"""Production game model — the single function the live pipeline calls.

This reproduces EXACTLY the validated backtest path: the runs model blended with
the prior-season Pythagorean team-strength prior at weight config.PRIOR_BLEND_W.
Keeping live and backtest on the same code is what lets the daily picks inherit
the backtested calibration.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import LEAGUE_FIP_FALLBACK, PARK_FACTORS, DEFAULT_PARK, PRIOR_BLEND_W
from .devig import prob_to_american
from .runs import expected_runs
from .strength import blend, prior_winprob
from .winprob import win_probability_from_runs


@dataclass
class GameInputs:
    league_rpg: float
    home_rs: float          # home team prior-season runs/game (offense)
    home_ra: float          # home team prior-season runs allowed/game (defense)
    away_rs: float
    away_ra: float
    home_starter_fip: float  # regressed prior-season FIP (league avg if unknown)
    away_starter_fip: float
    venue: str = ""


@dataclass
class GamePrediction:
    p_home: float            # blended home win probability (the model's own number)
    home_line: int           # model's own fair American odds for home
    away_line: int           # model's own fair American odds for away
    p_runs: float            # component: runs model
    p_prior: float           # component: team-strength prior


def predict_game(inp: GameInputs, league_fip: float = LEAGUE_FIP_FALLBACK,
                 w: float = PRIOR_BLEND_W) -> GamePrediction:
    home_off = inp.home_rs / inp.league_rpg
    away_off = inp.away_rs / inp.league_rpg
    park = PARK_FACTORS.get(inp.venue, DEFAULT_PARK)

    er_home = expected_runs(inp.league_rpg, home_off, inp.away_starter_fip, league_fip, park)
    er_away = expected_runs(inp.league_rpg, away_off, inp.home_starter_fip, league_fip, park)
    p_runs = win_probability_from_runs(er_home, er_away)
    p_prior = prior_winprob(inp.home_rs, inp.home_ra, inp.away_rs, inp.away_ra)
    p_home = blend(p_runs, p_prior, w)

    return GamePrediction(
        p_home=p_home,
        home_line=prob_to_american(p_home),
        away_line=prob_to_american(1.0 - p_home),
        p_runs=p_runs,
        p_prior=p_prior,
    )
