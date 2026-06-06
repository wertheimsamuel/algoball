"""Experiment: TEAM-STRENGTH PRIOR blended into the runs model.

Hypothesis
----------
The baseline AlgoBall model uses only team OFFENSE (prior-season runs/game) and
the STARTING pitcher's FIP. It has no notion of overall team quality -- nothing
about run PREVENTION (defense + bullpen) or a stable team-strength prior. We add
a prior-season TEAM-STRENGTH PRIOR built from runs scored AND runs allowed:

    pyth = RS^E / (RS^E + RA^E)              (Pythagorean win expectation, E=1.83)

regressed toward .500 by adding G_REG "league-average" games, converted into a
matchup win probability via log5, given a home-field nudge in logit space, and
finally BLENDED with the existing runs-model probability:

    p_final = W * p_prior + (1 - W) * p_runs   (linear blend in probability space)

We grid-search the blend weight W and the regression strength, and also try
prior-season actual win% as an alternative strength estimate.

NO LOOKAHEAD
------------
To predict a season-Y game we use ONLY season (Y-1) full-season team stats
(runs scored, runs allowed, win%) and (Y-1) pitcher FIP -- exactly the same
point-in-time discipline the baseline harness already uses. The prior is a
PRIOR-SEASON aggregate; nothing from season Y (and certainly not the game's own
result) ever enters a prediction. This is identical in spirit to the existing
backtest, just with an extra prior-season feature (runs allowed / win%).

This script edits NOTHING in src/; it imports the ingest + model layers
read-only and re-implements the prediction loop locally so the baseline and the
variant are computed side-by-side on the same games.

Run:
    PYTHONPATH=src python3 experiments/team-strength-prior.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- read-only imports from the existing project ----------------------------
from algoball.config import LEAGUE_FIP_FALLBACK, FIP_REGRESS_IP, PARK_FACTORS, DEFAULT_PARK
from algoball.ingest.mlb import (
    _BASE,
    _cached,
    get_pitcher_fip,
    get_season_schedule,
    get_team_runs_per_game,
)
from algoball.model.runs import expected_runs
from algoball.model.winprob import win_probability_from_runs

PYTH_EXP = 1.83


# --- extra cached fetchers (same urllib/cache pattern as ingest.mlb) ---------
def get_team_runs_allowed_per_game(team_id: int, season: int) -> Optional[float]:
    """Prior-season runs ALLOWED per game (pitching group). Lookahead-safe when
    season is the prior season."""
    url = f"{_BASE}/teams/{team_id}/stats?stats=season&group=pitching&season={season}"
    raw = _cached(f"teampit_{team_id}_{season}", url)
    splits = raw.get("stats", [{}])[0].get("splits", []) if raw.get("stats") else []
    if not splits:
        return None
    st = splits[0]["stat"]
    runs = float(st.get("runs", 0))
    gp = float(st.get("gamesPlayed", 0))
    if gp < 1:
        return None
    return runs / gp


def get_team_winpct(season: int) -> Dict[int, float]:
    """Prior-season actual winning percentage for every team (from standings)."""
    url = f"{_BASE}/standings?leagueId=103,104&season={season}"
    raw = _cached(f"standings_{season}", url)
    out: Dict[int, float] = {}
    for rec in raw.get("records", []):
        for tr in rec.get("teamRecords", []):
            tid = tr["team"]["id"]
            w, l = float(tr.get("wins", 0)), float(tr.get("losses", 0))
            if w + l >= 1:
                out[tid] = w / (w + l)
    return out


# --- strength prior math ----------------------------------------------------
def pythagorean(rs_pg: float, ra_pg: float) -> float:
    """Pythagorean win expectation from runs scored/allowed per game."""
    num = rs_pg ** PYTH_EXP
    return num / (num + ra_pg ** PYTH_EXP)


def regress_to_500(strength: float, n_games: float, g_reg: float) -> float:
    """Regress a team strength toward .500 by adding g_reg average games."""
    return (strength * n_games + 0.500 * g_reg) / (n_games + g_reg)


def log5(p_home: float, p_away: float) -> float:
    """log5: probability home (strength p_home) beats away (strength p_away),
    neutral site."""
    denom = p_home + p_away - 2 * p_home * p_away
    if denom <= 0:
        return 0.5
    return (p_home - p_home * p_away) / denom


def _logit(p: float) -> float:
    p = min(1 - 1e-9, max(1e-9, p))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# --- prediction container + raw per-game decomposition ----------------------
@dataclass
class Row:
    p_runs: float          # baseline runs-model probability (HFA baked in)
    prior_home: float      # home team prior-season strength (regressed)
    prior_away: float      # away team prior-season strength (regressed)
    home_won: int


# HFA in logit space (~ matches the league home win rate of ~0.535 for even teams)
HFA_LOGIT = 0.145


def prior_prob(prior_home: float, prior_away: float) -> float:
    """log5 matchup prob with a home-field nudge in logit space."""
    p = log5(prior_home, prior_away)
    return _sigmoid(_logit(p) + HFA_LOGIT)


def blend(p_runs: float, p_prior: float, w: float, in_logit: bool) -> float:
    if in_logit:
        return _sigmoid((1 - w) * _logit(p_runs) + w * _logit(p_prior))
    return (1 - w) * p_runs + w * p_prior


# --- build the per-game rows (runs baseline + strength prior) ----------------
def build_rows(
    predict_season: int,
    feature_season: Optional[int] = None,
    end_date: Optional[str] = None,
    strength: str = "pyth",   # "pyth" | "winpct"
    g_reg: float = 50.0,
    league_fip: float = LEAGUE_FIP_FALLBACK,
) -> List[Row]:
    feature_season = feature_season or (predict_season - 1)
    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    team_ids = {g["home_id"] for g in games} | {g["away_id"] for g in games}

    # prior-season offense (runs scored) -- reused for both baseline + league avg
    team_rpg: Dict[int, float] = {}
    team_rapg: Dict[int, float] = {}
    for tid in team_ids:
        rpg = get_team_runs_per_game(tid, feature_season)
        if rpg:
            team_rpg[tid] = rpg
        rapg = get_team_runs_allowed_per_game(tid, feature_season)
        if rapg:
            team_rapg[tid] = rapg
    if not team_rpg:
        raise RuntimeError(f"no prior-season ({feature_season}) team data")
    league_rpg = sum(team_rpg.values()) / len(team_rpg)

    winpct = get_team_winpct(feature_season) if strength == "winpct" else {}

    # prior-season strength per team (regressed toward .500)
    strength_of: Dict[int, float] = {}
    for tid in team_ids:
        if strength == "winpct":
            raw = winpct.get(tid)
            n = 162.0
        else:
            rs, ra = team_rpg.get(tid), team_rapg.get(tid)
            raw = pythagorean(rs, ra) if (rs and ra) else None
            n = 162.0
        strength_of[tid] = regress_to_500(raw, n, g_reg) if raw is not None else 0.5

    rows: List[Row] = []
    fip_cache: Dict[int, float] = {}

    def fip_for(pid: Optional[int]) -> float:
        if pid not in fip_cache:
            data = get_pitcher_fip(pid, feature_season) if pid else None
            if not data:
                fip_cache[pid] = league_fip
            else:
                ip, fip = data["ip"], data["fip"]
                fip_cache[pid] = (ip * fip + FIP_REGRESS_IP * league_fip) / (ip + FIP_REGRESS_IP)
        return fip_cache[pid]

    for g in games:
        if g["home_id"] not in team_rpg or g["away_id"] not in team_rpg:
            continue
        home_off = team_rpg[g["home_id"]] / league_rpg
        away_off = team_rpg[g["away_id"]] / league_rpg
        home_fip = fip_for(g["home_sp"])
        away_fip = fip_for(g["away_sp"])
        park = PARK_FACTORS.get(g["venue"], DEFAULT_PARK)
        er_home = expected_runs(league_rpg, home_off, away_fip, league_fip, park)
        er_away = expected_runs(league_rpg, away_off, home_fip, league_fip, park)
        p_runs = win_probability_from_runs(er_home, er_away)
        rows.append(Row(
            p_runs=p_runs,
            prior_home=strength_of[g["home_id"]],
            prior_away=strength_of[g["away_id"]],
            home_won=1 if g["home_won"] else 0,
        ))
    return rows


# --- metrics ----------------------------------------------------------------
def brier(ps: List[float], ys: List[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def log_loss(ps: List[float], ys: List[int]) -> float:
    eps = 1e-6
    tot = 0.0
    for p, y in zip(ps, ys):
        q = min(1 - eps, max(eps, p))
        tot += -(y * math.log(q) + (1 - y) * math.log(1 - q))
    return tot / len(ps)


def accuracy(ps: List[float], ys: List[int]) -> float:
    return sum((p >= 0.5) == bool(y) for p, y in zip(ps, ys)) / len(ps)


def calibration(ps: List[float], ys: List[int], bins: int = 10) -> List[tuple]:
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(ps)
               if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        if not idx:
            continue
        avg_pred = sum(ps[i] for i in idx) / len(idx)
        actual = sum(ys[i] for i in idx) / len(idx)
        rows.append((lo, hi, len(idx), avg_pred, actual))
    return rows


# --- evaluation drivers -----------------------------------------------------
def eval_variant(rows: List[Row], w: float, in_logit: bool) -> Tuple[float, float, float]:
    ys = [r.home_won for r in rows]
    ps = [blend(r.p_runs, prior_prob(r.prior_home, r.prior_away), w, in_logit) for r in rows]
    return accuracy(ps, ys), brier(ps, ys), log_loss(ps, ys)


def metrics_line(name: str, acc: float, br: float, ll: float) -> str:
    return f"  {name:34}acc {acc:.3f}  Brier {br:.4f}  logLoss {ll:.4f}"


def run_slice(label: str, predict_season: int, end_date: Optional[str],
              strength: str = "pyth", g_reg: float = 50.0,
              weights: Optional[List[float]] = None) -> dict:
    weights = weights or [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    rows = build_rows(predict_season, end_date=end_date, strength=strength, g_reg=g_reg)
    ys = [r.home_won for r in rows]
    n = len(rows)
    base_home_rate = sum(ys) / n

    print("=" * 78)
    print(f"{label}  (strength={strength}, g_reg={g_reg})  games={n}  home win rate={base_home_rate:.3f}")
    print("=" * 78)

    # runs-only baseline (w=0) -- should match the reported AlgoBall baseline
    p_runs = [r.p_runs for r in rows]
    print(metrics_line("runs-model baseline (w=0)",
                        accuracy(p_runs, ys), brier(p_runs, ys), log_loss(p_runs, ys)))
    # pure prior (w=1) for reference
    p_pri = [prior_prob(r.prior_home, r.prior_away) for r in rows]
    print(metrics_line("pure team-strength prior (w=1)",
                        accuracy(p_pri, ys), brier(p_pri, ys), log_loss(p_pri, ys)))
    print("-" * 78)

    best = None
    for in_logit in (False, True):
        tag = "logit-blend" if in_logit else "prob-blend "
        for w in weights:
            acc, br, ll = eval_variant(rows, w, in_logit)
            print(metrics_line(f"{tag} w={w:.2f}", acc, br, ll))
            if best is None or br < best["brier"]:
                best = {"w": w, "in_logit": in_logit, "acc": acc, "brier": br, "log_loss": ll}
        print("-" * 78)

    print(f"BEST on {label}: {'logit' if best['in_logit'] else 'prob'}-blend "
          f"w={best['w']:.2f} -> acc {best['acc']:.3f}  Brier {best['brier']:.4f}  "
          f"logLoss {best['log_loss']:.4f}")
    # calibration of the best blend
    ps_best = [blend(r.p_runs, prior_prob(r.prior_home, r.prior_away),
                     best["w"], best["in_logit"]) for r in rows]
    print("calibration of BEST (pred -> actual):")
    for lo, hi, cnt, avg_pred, actual in calibration(ps_best, ys):
        print(f"  {f'{lo:.2f}-{hi:.2f}':12}n={cnt:<5}pred={avg_pred:.3f}  actual={actual:.3f}")
    print()
    best["n"] = n
    best["base_home_rate"] = base_home_rate
    best["runs_brier"] = brier(p_runs, ys)
    best["runs_acc"] = accuracy(p_runs, ys)
    best["runs_logloss"] = log_loss(p_runs, ys)
    return best


def main() -> None:
    # ---- primary comparable slice: predict 2026 thru 2026-04-30 ----
    print("\n########## PYTHAGOREAN PRIOR ##########\n")
    b2026 = run_slice("predict 2026 thru 2026-04-30", 2026, "2026-04-30",
                      strength="pyth", g_reg=50.0)

    # sensitivity on regression strength for the 2026 slice (pyth)
    print("\n--- regression-strength sweep (2026 slice, pyth, prob-blend) ---")
    for g_reg in (0.0, 25.0, 50.0, 75.0, 100.0):
        rows = build_rows(2026, end_date="2026-04-30", strength="pyth", g_reg=g_reg)
        best_w, best = None, None
        for w in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            acc, br, ll = eval_variant(rows, w, in_logit=False)
            if best is None or br < best[1]:
                best, best_w = (acc, br, ll), w
        print(f"  g_reg={g_reg:5.0f}  best w={best_w:.2f}  acc {best[0]:.3f}  "
              f"Brier {best[1]:.4f}  logLoss {best[2]:.4f}")

    # ---- actual win% prior on the 2026 slice ----
    print("\n########## ACTUAL WIN% PRIOR ##########\n")
    run_slice("predict 2026 thru 2026-04-30 (winpct prior)", 2026, "2026-04-30",
              strength="winpct", g_reg=50.0)

    # ---- larger sample: predict 2025 full season ----
    print("\n########## PYTHAGOREAN PRIOR -- 2025 FULL SEASON ##########\n")
    b2025 = run_slice("predict 2025 (full season)", 2025, None,
                      strength="pyth", g_reg=50.0)

    print("\n=== SUMMARY ===")
    print(f"2026 slice: runs-only Brier {b2026['runs_brier']:.4f} acc {b2026['runs_acc']:.3f} "
          f"-> best blend Brier {b2026['brier']:.4f} acc {b2026['acc']:.3f} "
          f"(w={b2026['w']:.2f}, {'logit' if b2026['in_logit'] else 'prob'})")
    print(f"2025 full : runs-only Brier {b2025['runs_brier']:.4f} acc {b2025['runs_acc']:.3f} "
          f"-> best blend Brier {b2025['brier']:.4f} acc {b2025['acc']:.3f} "
          f"(w={b2025['w']:.2f}, {'logit' if b2025['in_logit'] else 'prob'})")


if __name__ == "__main__":
    main()
