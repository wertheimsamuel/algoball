"""Backtesting harness — grade the model's pre-game predictions against real
historical MLB results, with NO lookahead.

Discipline: to predict a game in season Y, we use only season (Y-1) stats
(prior-season FIP, team runs/game). The model never sees anything that happened
on or after game day. We then score it with proper probabilistic metrics, not
just win/loss, because for a high-variance sport CALIBRATION matters more than
raw accuracy.

Run (from project root):
    PYTHONPATH=src python3 -m algoball.backtest 2026 --end 2026-04-30
    PYTHONPATH=src python3 -m algoball.backtest 2025
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from typing import List, Optional

from .config import LEAGUE_FIP_FALLBACK, FIP_REGRESS_IP, PARK_FACTORS, DEFAULT_PARK
from .ingest.mlb import (
    get_pitcher_fip,
    get_season_schedule,
    get_team_runs_per_game,
)
from .ingest.mlb import get_team_runs_allowed_per_game
from .model.runs import expected_runs
from .model.strength import prior_winprob
from .model.winprob import win_probability_from_runs


@dataclass
class Prediction:
    p_home: float
    home_won: int  # 1 / 0


def build_components(
    predict_season: int,
    feature_season: Optional[int] = None,
    end_date: Optional[str] = None,
    league_fip: float = LEAGUE_FIP_FALLBACK,
) -> List[dict]:
    """Per game, return {p_runs, p_prior, home_won} so any blend weight can be evaluated.

    p_runs reproduces the baseline runs model exactly (so weight 0 == baseline).
    p_prior is the prior-season Pythagorean team-strength prior.
    """
    feature_season = feature_season or (predict_season - 1)
    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    team_ids = {g["home_id"] for g in games} | {g["away_id"] for g in games}
    team_rpg, team_rapg = {}, {}
    for tid in team_ids:
        rs = get_team_runs_per_game(tid, feature_season)
        ra = get_team_runs_allowed_per_game(tid, feature_season)
        if rs:
            team_rpg[tid] = rs
        if ra:
            team_rapg[tid] = ra
    league_rpg = sum(team_rpg.values()) / len(team_rpg)

    comps: List[dict] = []
    fip_cache = {}

    def fip_for(pid):
        if pid not in fip_cache:
            fip_cache[pid] = _regressed_fip(pid, feature_season, league_fip)
        return fip_cache[pid]

    for g in games:
        if g["home_id"] not in team_rpg or g["away_id"] not in team_rpg:
            continue
        if g["home_id"] not in team_rapg or g["away_id"] not in team_rapg:
            continue
        home_off = team_rpg[g["home_id"]] / league_rpg
        away_off = team_rpg[g["away_id"]] / league_rpg
        park = PARK_FACTORS.get(g["venue"], DEFAULT_PARK)
        er_home = expected_runs(league_rpg, home_off, fip_for(g["away_sp"]), league_fip, park)
        er_away = expected_runs(league_rpg, away_off, fip_for(g["home_sp"]), league_fip, park)
        p_runs = win_probability_from_runs(er_home, er_away)
        p_prior = prior_winprob(
            team_rpg[g["home_id"]], team_rapg[g["home_id"]],
            team_rpg[g["away_id"]], team_rapg[g["away_id"]],
        )
        comps.append({"p_runs": p_runs, "p_prior": p_prior, "home_won": 1 if g["home_won"] else 0})
    return comps


def _regressed_fip(pitcher_id: Optional[int], season: int, league_fip: float) -> float:
    data = get_pitcher_fip(pitcher_id, season) if pitcher_id else None
    if not data:
        return league_fip
    ip, fip = data["ip"], data["fip"]
    return (ip * fip + FIP_REGRESS_IP * league_fip) / (ip + FIP_REGRESS_IP)


def build_predictions(
    predict_season: int,
    feature_season: Optional[int] = None,
    end_date: Optional[str] = None,
    league_fip: float = LEAGUE_FIP_FALLBACK,
) -> List[Prediction]:
    feature_season = feature_season or (predict_season - 1)
    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    # Prior-season team run rates + league baseline.
    team_ids = {g["home_id"] for g in games} | {g["away_id"] for g in games}
    team_rpg = {}
    for tid in team_ids:
        rpg = get_team_runs_per_game(tid, feature_season)
        if rpg:
            team_rpg[tid] = rpg
    if not team_rpg:
        raise RuntimeError(f"no prior-season ({feature_season}) team data found")
    league_rpg = sum(team_rpg.values()) / len(team_rpg)

    preds: List[Prediction] = []
    fip_cache = {}
    for g in games:
        if g["home_id"] not in team_rpg or g["away_id"] not in team_rpg:
            continue
        home_off = team_rpg[g["home_id"]] / league_rpg
        away_off = team_rpg[g["away_id"]] / league_rpg

        def fip_for(pid):
            if pid not in fip_cache:
                fip_cache[pid] = _regressed_fip(pid, feature_season, league_fip)
            return fip_cache[pid]

        home_fip = fip_for(g["home_sp"])
        away_fip = fip_for(g["away_sp"])
        park = PARK_FACTORS.get(g["venue"], DEFAULT_PARK)

        er_home = expected_runs(league_rpg, home_off, away_fip, league_fip, park)
        er_away = expected_runs(league_rpg, away_off, home_fip, league_fip, park)
        p_home = win_probability_from_runs(er_home, er_away)
        preds.append(Prediction(p_home=p_home, home_won=1 if g["home_won"] else 0))
    return preds


# --- metrics ----------------------------------------------------------------
def _brier(preds: List[Prediction]) -> float:
    return sum((p.p_home - p.home_won) ** 2 for p in preds) / len(preds)


def _log_loss(preds: List[Prediction]) -> float:
    eps = 1e-6
    total = 0.0
    for p in preds:
        q = min(1 - eps, max(eps, p.p_home))
        total += -(p.home_won * math.log(q) + (1 - p.home_won) * math.log(1 - q))
    return total / len(preds)


def _accuracy(preds: List[Prediction]) -> float:
    return sum((p.p_home >= 0.5) == bool(p.home_won) for p in preds) / len(preds)


def _calibration_table(preds: List[Prediction], bins: int = 10) -> List[tuple]:
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        grp = [p for p in preds if (lo <= p.p_home < hi) or (b == bins - 1 and p.p_home == 1.0)]
        if not grp:
            continue
        avg_pred = sum(p.p_home for p in grp) / len(grp)
        actual = sum(p.home_won for p in grp) / len(grp)
        rows.append((lo, hi, len(grp), avg_pred, actual))
    return rows


def report(predict_season: int, end_date: Optional[str] = None) -> dict:
    preds = build_predictions(predict_season, end_date=end_date)
    n = len(preds)
    base_home_rate = sum(p.home_won for p in preds) / n  # always-pick-home accuracy
    # Baseline that "knows" only the league home-win rate, applied to every game:
    base_preds = [Prediction(p_home=base_home_rate, home_won=p.home_won) for p in preds]

    label = f"{predict_season}" + (f" thru {end_date}" if end_date else " (full season)")
    print("=" * 64)
    print(f"AlgoBall backtest — predict {label}, features from {predict_season - 1}")
    print("=" * 64)
    print(f"games graded:           {n}")
    print(f"home win rate (actual): {base_home_rate:.3f}")
    print("-" * 64)
    print(f"{'':22}{'MODEL':>12}{'always-home':>14}{'base-rate':>12}")
    print(f"{'accuracy':22}{_accuracy(preds):>12.3f}{base_home_rate:>14.3f}{'-':>12}")
    print(f"{'Brier (lower=better)':22}{_brier(preds):>12.4f}{_brier([Prediction(1.0,p.home_won) for p in preds]):>14.4f}{_brier(base_preds):>12.4f}")
    print(f"{'log loss (lower=better)':22}{_log_loss(preds):>12.4f}{'-':>14}{_log_loss(base_preds):>12.4f}")
    print("-" * 64)
    print("calibration (predicted -> actual home win rate):")
    print(f"  {'bucket':14}{'n':>6}{'pred':>9}{'actual':>9}")
    for lo, hi, cnt, avg_pred, actual in _calibration_table(preds):
        print(f"  {f'{lo:.2f}-{hi:.2f}':14}{cnt:>6}{avg_pred:>9.3f}{actual:>9.3f}")
    print("=" * 64)
    return {
        "n": n,
        "accuracy": _accuracy(preds),
        "brier": _brier(preds),
        "log_loss": _log_loss(preds),
        "base_home_rate": base_home_rate,
        "base_rate_brier": _brier(base_preds),
    }


def main(argv: Optional[List[str]] = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m algoball.backtest <season> [--end YYYY-MM-DD]")
        return
    season = int(argv[0])
    end_date = None
    if "--end" in argv:
        end_date = argv[argv.index("--end") + 1]
    report(season, end_date=end_date)


if __name__ == "__main__":
    main()
