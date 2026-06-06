"""Experiment: SEASON-TO-DATE form, blended with the prior season, lookahead-safe.

Hypothesis
----------
The prior-season-only baseline (Brier 0.2486, acc 0.559 on 2026 thru 2026-04-30)
ignores how teams are actually playing *this* year and has NO team-defense /
run-prevention term at all (it assumes a league-average bullpen for the 40% of
innings the starter does not throw). This variant builds each team's offense
(runs scored) and run-prevention (runs allowed) from the *current* season's
games STRICTLY BEFORE the game date D, and shrinks each toward the prior-season
value by sample size (few early games -> mostly prior; later -> more current).

Everything else (the expected-runs -> win-probability map, park factors, the
starter's prior-season regressed FIP) is the existing, unedited model code,
imported read-only.

How it stays lookahead-safe (the cardinal rule)
-----------------------------------------------
* Prior-season tables (RS/game, RA/game per team, league averages) are built
  from the FULL prior season (predict_season - 1). A prior season is always
  entirely in the past relative to any game in predict_season -> safe.
* Season-to-date tables are built by walking the predict-season schedule in
  date order and, for a game on date D, summing ONLY games with date strictly
  < D (a python `<`, not `<=`). Same-day games are excluded entirely, so a game
  can never see its own result nor any other game that finished the same day.
  This is deliberately conservative (it throws away same-day early games) to
  make a leak impossible.
* The label (home_won) is used ONLY for scoring, never as a feature.
* The starter FIP is the prior season's, exactly as the baseline uses it.

Run
---
    PYTHONPATH=src python3 experiments/season-to-date.py

It prints the baseline-comparable slice (2026 thru 2026-04-30), the full 2026,
and full 2025 (prior 2024) for out-of-window validation, plus a small shrinkage
sensitivity sweep and ablations so the contribution of each piece is visible.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- read-only imports from the existing, UNEDITED model/ingest layer --------
from algoball.config import (
    LEAGUE_FIP_FALLBACK,
    FIP_REGRESS_IP,
    STARTER_IP_SHARE,
    PARK_FACTORS,
    DEFAULT_PARK,
)
from algoball.ingest.mlb import get_pitcher_fip, get_season_schedule
from algoball.model.winprob import win_probability_from_runs


# ---------------------------------------------------------------------------
# Prediction container + metrics (self-contained; mirrors backtest.py exactly)
# ---------------------------------------------------------------------------
@dataclass
class Prediction:
    p_home: float
    home_won: int


def brier(preds: List[Prediction]) -> float:
    return sum((p.p_home - p.home_won) ** 2 for p in preds) / len(preds)


def log_loss(preds: List[Prediction]) -> float:
    eps = 1e-6
    tot = 0.0
    for p in preds:
        q = min(1 - eps, max(eps, p.p_home))
        tot += -(p.home_won * math.log(q) + (1 - p.home_won) * math.log(1 - q))
    return tot / len(preds)


def accuracy(preds: List[Prediction]) -> float:
    return sum((p.p_home >= 0.5) == bool(p.home_won) for p in preds) / len(preds)


def calibration_table(preds: List[Prediction], bins: int = 10):
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        grp = [p for p in preds if (lo <= p.p_home < hi) or (b == bins - 1 and p.p_home == 1.0)]
        if not grp:
            continue
        rows.append((lo, hi, len(grp),
                     sum(p.p_home for p in grp) / len(grp),
                     sum(p.home_won for p in grp) / len(grp)))
    return rows


# ---------------------------------------------------------------------------
# Prior-season FIP, regressed exactly like backtest._regressed_fip
# ---------------------------------------------------------------------------
_fip_cache: Dict[Tuple[int, int], float] = {}


def regressed_fip(pid: Optional[int], season: int, league_fip: float) -> float:
    if not pid:
        return league_fip
    key = (pid, season)
    if key not in _fip_cache:
        data = get_pitcher_fip(pid, season)
        if not data:
            _fip_cache[key] = league_fip
        else:
            ip, fip = data["ip"], data["fip"]
            _fip_cache[key] = (ip * fip + FIP_REGRESS_IP * league_fip) / (ip + FIP_REGRESS_IP)
    return _fip_cache[key]


# ---------------------------------------------------------------------------
# Team run tables from a schedule (runs scored / allowed), lookahead-safe
# ---------------------------------------------------------------------------
def prior_team_tables(season: int):
    """Full prior-season per-team RS/game and RA/game + league averages.

    Returns (rs_factor, ra_factor, league_rpg) where the factors are each
    team's rate divided by the league average (so they are centered on 1.0).
    """
    games = get_season_schedule(season)
    rs = defaultdict(float)
    ra = defaultdict(float)
    gp = defaultdict(int)
    for g in games:
        h, a = g["home_id"], g["away_id"]
        hs, as_ = g["home_score"], g["away_score"]
        rs[h] += hs; ra[h] += as_; gp[h] += 1
        rs[a] += as_; ra[a] += hs; gp[a] += 1
    rs_pg = {t: rs[t] / gp[t] for t in gp}
    ra_pg = {t: ra[t] / gp[t] for t in gp}
    league_rpg = sum(rs_pg.values()) / len(rs_pg)
    league_rapg = sum(ra_pg.values()) / len(ra_pg)
    rs_factor = {t: rs_pg[t] / league_rpg for t in rs_pg}
    ra_factor = {t: ra_pg[t] / league_rapg for t in ra_pg}
    return rs_factor, ra_factor, league_rpg


def build_team_game_logs(season: int) -> Dict[int, List[Tuple[str, float, float]]]:
    """Per team, a date-sorted list of (date, runs_scored, runs_allowed) for the
    predict season. Used to accumulate season-to-date stats with a strict date
    cutoff."""
    games = get_season_schedule(season)
    logs: Dict[int, List[Tuple[str, float, float]]] = defaultdict(list)
    for g in games:
        h, a = g["home_id"], g["away_id"]
        hs, as_ = g["home_score"], g["away_score"]
        d = g["date"] or ""
        logs[h].append((d, hs, as_))
        logs[a].append((d, as_, hs))
    for t in logs:
        logs[t].sort(key=lambda x: x[0])
    return logs


def std_to_date(logs: List[Tuple[str, float, float]], cutoff: str):
    """Sum runs scored / allowed and game count over games STRICTLY before
    `cutoff`. Returns (n, rs_per_g, ra_per_g) with None rates when n == 0."""
    n = 0
    rs = 0.0
    ra = 0.0
    for d, s, a in logs:
        if d < cutoff:        # <-- STRICT cutoff: never same-day or later
            n += 1
            rs += s
            ra += a
        else:
            break             # logs are date-sorted, so we can stop
    if n == 0:
        return 0, None, None
    return n, rs / n, ra / n


# ---------------------------------------------------------------------------
# The variant
# ---------------------------------------------------------------------------
def build_predictions(
    predict_season: int,
    end_date: Optional[str] = None,
    *,
    k_off: float = 45.0,
    k_def: float = 45.0,
    use_std_offense: bool = True,
    use_defense: bool = True,
    use_std_defense: bool = True,
    league_fip: float = LEAGUE_FIP_FALLBACK,
    sd_diff: float = 4.3,
) -> List[Prediction]:
    """Build pre-game predictions.

    k_off / k_def : shrinkage strength (games of prior to regress toward).
                    weight on season-to-date = n / (n + k).
    use_std_offense : blend season-to-date offense in (else prior-only offense).
    use_defense     : include a team run-prevention term for the bullpen share
                      (else the baseline's league-average-bullpen assumption).
    use_std_defense : blend season-to-date RA into that prevention term.
    """
    prior = predict_season - 1
    rs_prior, ra_prior, league_rpg = prior_team_tables(prior)
    logs = build_team_game_logs(predict_season)

    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    # Pre-compute a season-to-date LEAGUE average rate per cutoff date so the
    # current-season factors are centred on 1.0 in the *current* run environment.
    # (Built only from games strictly before the date, same cutoff rule.)
    all_logs_flat = []
    for t, lst in logs.items():
        for d, s, a in lst:
            all_logs_flat.append((d, s))
    all_logs_flat.sort(key=lambda x: x[0])

    def league_std_to_date(cutoff: str):
        n = 0
        tot = 0.0
        for d, s in all_logs_flat:
            if d < cutoff:
                n += 1
                tot += s
            else:
                break
        return (tot / n) if n else None

    league_std_cache: Dict[str, Optional[float]] = {}

    def league_std(cutoff: str):
        if cutoff not in league_std_cache:
            league_std_cache[cutoff] = league_std_to_date(cutoff)
        return league_std_cache[cutoff]

    def off_factor(team: int, cutoff: str) -> float:
        prior_f = rs_prior.get(team, 1.0)
        if not use_std_offense:
            return prior_f
        n, rs_pg, _ = std_to_date(logs.get(team, []), cutoff)
        lg = league_std(cutoff)
        if n == 0 or not lg:
            return prior_f
        std_f = rs_pg / lg
        w = n / (n + k_off)
        return w * std_f + (1 - w) * prior_f

    def def_factor(team: int, cutoff: str) -> float:
        """Run-prevention factor (RA relative to league); <1.0 == good pitching."""
        prior_f = ra_prior.get(team, 1.0)
        if not use_std_defense:
            return prior_f
        n, _, ra_pg = std_to_date(logs.get(team, []), cutoff)
        lg = league_std(cutoff)  # same league mean for RS and RA (symmetric)
        if n == 0 or not lg:
            return prior_f
        std_f = ra_pg / lg
        w = n / (n + k_def)
        return w * std_f + (1 - w) * prior_f

    preds: List[Prediction] = []
    for g in games:
        d = g["date"] or ""
        home, away = g["home_id"], g["away_id"]
        park = PARK_FACTORS.get(g["venue"], DEFAULT_PARK)

        home_off = off_factor(home, d)
        away_off = off_factor(away, d)

        home_fip = regressed_fip(g["home_sp"], prior, league_fip)
        away_fip = regressed_fip(g["away_sp"], prior, league_fip)

        if use_defense:
            home_def = def_factor(home, d)
            away_def = def_factor(away, d)
        else:
            home_def = away_def = 1.0   # baseline: league-average bullpen

        # opp run-prevention = starter (share) + team defense (remaining share)
        def prevent(opp_fip: float, opp_def_factor: float) -> float:
            starter = opp_fip / league_fip
            return STARTER_IP_SHARE * starter + (1 - STARTER_IP_SHARE) * opp_def_factor

        er_home = league_rpg * home_off * prevent(away_fip, away_def) * park
        er_away = league_rpg * away_off * prevent(home_fip, home_def) * park
        p_home = win_probability_from_runs(er_home, er_away, sd_diff=sd_diff)
        preds.append(Prediction(p_home=p_home, home_won=1 if g["home_won"] else 0))
    return preds


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def summarize(label: str, preds: List[Prediction], show_calib: bool = False) -> dict:
    n = len(preds)
    base = sum(p.home_won for p in preds) / n
    base_preds = [Prediction(base, p.home_won) for p in preds]
    acc, br, ll = accuracy(preds), brier(preds), log_loss(preds)
    print(f"{label:38} n={n:4d}  acc={acc:.3f}  Brier={br:.4f}  logLoss={ll:.4f}"
          f"  (base-rate Brier={brier(base_preds):.4f})")
    if show_calib:
        print("    calibration (pred -> actual):")
        for lo, hi, cnt, ap, ac in calibration_table(preds):
            print(f"      {lo:.2f}-{hi:.2f}  n={cnt:4d}  pred={ap:.3f}  actual={ac:.3f}")
    return {"n": n, "accuracy": acc, "brier": br, "log_loss": ll,
            "base_home_rate": base, "base_rate_brier": brier(base_preds)}


def main():
    print("=" * 92)
    print("SEASON-TO-DATE blend experiment  (baseline to beat: Brier 0.2486 / acc 0.559"
          " on 2026 thru 04-30)")
    print("=" * 92)

    SLICE = ("2026 thru 2026-04-30", 2026, "2026-04-30")

    # --- ablations on the baseline-comparable slice -------------------------
    print("\n--- ABLATIONS on", SLICE[0], "(prior season 2025) ---")
    season, end = SLICE[1], SLICE[2]
    summarize("A0 prior-only, no defense (==baseline)",
              build_predictions(season, end, use_std_offense=False,
                                 use_defense=False))
    summarize("A1 + season-to-date OFFENSE only",
              build_predictions(season, end, use_std_offense=True,
                                 use_defense=False))
    summarize("A2 + team DEFENSE (prior RA only)",
              build_predictions(season, end, use_std_offense=False,
                                 use_defense=True, use_std_defense=False))
    summarize("A3 + std offense + prior-RA defense",
              build_predictions(season, end, use_std_offense=True,
                                 use_defense=True, use_std_defense=False))
    summarize("A4 FULL: std offense + std+prior defense",
              build_predictions(season, end, use_std_offense=True,
                                 use_defense=True, use_std_defense=True),
              show_calib=True)

    # --- shrinkage sensitivity (full variant) -------------------------------
    print("\n--- shrinkage K sensitivity (full variant, same slice) ---")
    for k in (20.0, 30.0, 45.0, 60.0, 90.0):
        summarize(f"K_off=K_def={k:>4.0f}",
                  build_predictions(season, end, k_off=k, k_def=k,
                                    use_std_offense=True, use_defense=True,
                                    use_std_defense=True))

    # --- headline comparison + other slices ---------------------------------
    print("\n--- HEADLINE: baseline vs full variant ---")
    summarize("baseline   2026 thru 04-30",
              build_predictions(2026, "2026-04-30", use_std_offense=False,
                                use_defense=False))
    summarize("variant    2026 thru 04-30",
              build_predictions(2026, "2026-04-30"))

    print("\n--- out-of-window validation (other slices) ---")
    summarize("baseline   2026 FULL",
              build_predictions(2026, None, use_std_offense=False,
                                use_defense=False))
    summarize("variant    2026 FULL",
              build_predictions(2026, None))
    summarize("baseline   2025 FULL (prior 2024)",
              build_predictions(2025, None, use_std_offense=False,
                                use_defense=False))
    summarize("variant    2025 FULL (prior 2024)",
              build_predictions(2025, None))
    print("=" * 92)


if __name__ == "__main__":
    main()
