"""Experiment: pure CALIBRATION param-tuning of the EXISTING AlgoBall model.

Hypothesis: the model architecture (team offense + starting-pitcher FIP, mapped
to a win prob via a normal CDF) is fixed and already well-calibrated; we only
re-tune its four scalar knobs to squeeze out log loss / Brier:

    SD_DIFF          (3.6 .. 5.0)  spread of single-game run differential
    STARTER_IP_SHARE (0.45 .. 0.75) innings share attributed to the starter
    FIP_REGRESS_IP   (20 .. 100)   innings of league FIP to regress a SP toward
    HFA_RUNS         (0.20 .. 0.50) home-field advantage as a run nudge

No new features are added. We re-implement the existing math here (read-only use
of the ingest + config layers) so we never touch src/algoball/model/* .

LOOKAHEAD SAFETY
----------------
Identical discipline to the shipped backtester: to predict a game in season Y we
use only season (Y-1) features (prior-season team runs/game, prior-season pitcher
FIP). No game's own result, no same-season-to-date or full-season-Y stats feed a
prediction. The tunable params are GLOBAL scalars, not per-game fitted values, so
they leak no per-game information. The honesty guard against over-fitting the
467-game April-2026 slice is an OUT-OF-SAMPLE check on the 2025 full season
(features from 2024): we grid-search each dataset independently and also pooled,
then report every chosen param set on BOTH datasets.

Run:
    PYTHONPATH=src python3 experiments/param-tuning.py
    PYTHONPATH=src python3 experiments/param-tuning.py --fast   # skip 2025 fetch
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

from algoball.config import (
    DEFAULT_PARK,
    LEAGUE_FIP_FALLBACK,
    PARK_FACTORS,
)
from algoball.ingest.mlb import (
    get_pitcher_fip,
    get_season_schedule,
    get_team_runs_per_game,
)

# ---- the four knobs we tune, plus the shipped baseline values ---------------
BASELINE = dict(sd_diff=4.3, ip_share=0.60, regress_ip=50.0, hfa=0.37)

SDS = [round(3.6 + 0.1 * i, 2) for i in range(15)]          # 3.6 .. 5.0
IP_SHARES = [round(0.45 + 0.05 * i, 2) for i in range(7)]   # 0.45 .. 0.75
REGRESS_IPS = [float(x) for x in range(20, 101, 10)]        # 20 .. 100
HFAS = [round(0.20 + 0.05 * i, 2) for i in range(7)]        # 0.20 .. 0.50

_SQRT2 = math.sqrt(2.0)


@dataclass
class Rec:
    """Per-game raw inputs that do NOT depend on the tunable params."""
    home_won: int
    home_off: float          # team runs/game vs league (prior season)
    away_off: float
    park: float
    home_raw: Optional[Tuple[float, float]]  # (ip, fip) of home starter, or None
    away_raw: Optional[Tuple[float, float]]


# ---- data gathering (read-only, lookahead-safe; mirrors build_predictions) ---
def gather(
    predict_season: int,
    feature_season: Optional[int] = None,
    end_date: Optional[str] = None,
    league_fip: float = LEAGUE_FIP_FALLBACK,
) -> Tuple[List[Rec], float]:
    feature_season = feature_season or (predict_season - 1)
    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    team_ids = {g["home_id"] for g in games} | {g["away_id"] for g in games}
    team_rpg = {}
    for tid in team_ids:
        rpg = get_team_runs_per_game(tid, feature_season)
        if rpg:
            team_rpg[tid] = rpg
    if not team_rpg:
        raise RuntimeError(f"no prior-season ({feature_season}) team data")
    league_rpg = sum(team_rpg.values()) / len(team_rpg)

    raw_cache = {}

    def pitcher_raw(pid):
        if pid not in raw_cache:
            d = get_pitcher_fip(pid, feature_season) if pid else None
            raw_cache[pid] = (d["ip"], d["fip"]) if d else None
        return raw_cache[pid]

    recs: List[Rec] = []
    for g in games:
        if g["home_id"] not in team_rpg or g["away_id"] not in team_rpg:
            continue
        recs.append(Rec(
            home_won=1 if g["home_won"] else 0,
            home_off=team_rpg[g["home_id"]] / league_rpg,
            away_off=team_rpg[g["away_id"]] / league_rpg,
            park=PARK_FACTORS.get(g["venue"], DEFAULT_PARK),
            home_raw=pitcher_raw(g["home_sp"]),
            away_raw=pitcher_raw(g["away_sp"]),
        ))
    return recs, league_rpg


# ---- the model math, parameterised (re-implemented; src/ untouched) ----------
def _regressed(raw, regress_ip, league_fip):
    if raw is None:
        return league_fip
    ip, fip = raw
    return (ip * fip + regress_ip * league_fip) / (ip + regress_ip)


def _run_diffs(recs, league_rpg, league_fip, ip_share, regress_ip):
    """E[runs_home] - E[runs_away] (no HFA) per game, for fixed offense params."""
    out = []
    for r in recs:
        hf = _regressed(r.home_raw, regress_ip, league_fip)
        af = _regressed(r.away_raw, regress_ip, league_fip)
        supp_away = ip_share * (af / league_fip) + (1.0 - ip_share)
        supp_home = ip_share * (hf / league_fip) + (1.0 - ip_share)
        base = league_rpg * r.park
        er_home = base * r.home_off * supp_away
        er_away = base * r.away_off * supp_home
        out.append(er_home - er_away)
    return out


def _metrics(run_diffs, wons, sd_diff, hfa):
    inv = 1.0 / (sd_diff * _SQRT2)
    eps = 1e-6
    n = len(wons)
    brier = ll = 0.0
    correct = 0
    for rd, w in zip(run_diffs, wons):
        p = 0.5 * (1.0 + math.erf((rd + hfa) * inv))
        brier += (p - w) ** 2
        q = min(1 - eps, max(eps, p))
        ll += -(w * math.log(q) + (1 - w) * math.log(1 - q))
        if (p >= 0.5) == bool(w):
            correct += 1
    return correct / n, brier / n, ll / n


def evaluate(recs, league_rpg, params, league_fip=LEAGUE_FIP_FALLBACK):
    wons = [r.home_won for r in recs]
    rd = _run_diffs(recs, league_rpg, league_fip,
                    params["ip_share"], params["regress_ip"])
    return _metrics(rd, wons, params["sd_diff"], params["hfa"])


def grid_search(recs, league_rpg, league_fip=LEAGUE_FIP_FALLBACK):
    """Minimise log loss over the full 4-D grid. Returns (best_params, best_ll)."""
    wons = [r.home_won for r in recs]
    best = None
    for ip_share in IP_SHARES:
        for regress_ip in REGRESS_IPS:
            rd = _run_diffs(recs, league_rpg, league_fip, ip_share, regress_ip)
            for sd in SDS:
                for hfa in HFAS:
                    _, _, ll = _metrics(rd, wons, sd, hfa)
                    if best is None or ll < best[1]:
                        best = (dict(sd_diff=sd, ip_share=ip_share,
                                     regress_ip=regress_ip, hfa=hfa), ll)
    return best


def grid_search_pooled(datasets):
    """Minimise pooled log loss across multiple (recs, league_rpg) datasets."""
    league_fip = LEAGUE_FIP_FALLBACK
    prepared = [(recs, [r.home_won for r in recs], league_rpg)
                for recs, league_rpg in datasets]
    best = None
    for ip_share in IP_SHARES:
        for regress_ip in REGRESS_IPS:
            rds = [(_run_diffs(recs, lr, league_fip, ip_share, regress_ip), wons)
                   for recs, wons, lr in prepared]
            for sd in SDS:
                for hfa in HFAS:
                    tot_ll = 0.0
                    tot_n = 0
                    for rd, wons in rds:
                        _, _, ll = _metrics(rd, wons, sd, hfa)
                        tot_ll += ll * len(wons)
                        tot_n += len(wons)
                    ll = tot_ll / tot_n
                    if best is None or ll < best[1]:
                        best = (dict(sd_diff=sd, ip_share=ip_share,
                                     regress_ip=regress_ip, hfa=hfa), ll)
    return best


# ---- reporting --------------------------------------------------------------
def _fmt_params(p):
    return (f"SD={p['sd_diff']:.2f} IP={p['ip_share']:.2f} "
            f"R={p['regress_ip']:.0f} HFA={p['hfa']:.2f}")


def _line(label, recs, league_rpg, params):
    acc, brier, ll = evaluate(recs, league_rpg, params)
    print(f"  {label:30}acc {acc:.3f} | Brier {brier:.4f} | logLoss {ll:.4f}")
    return acc, brier, ll


def main():
    fast = "--fast" in sys.argv
    print("Gathering 2026 slice (predict 2026 thru 2026-04-30, features 2025)...")
    recs26, lrpg26 = gather(2026, end_date="2026-04-30")
    print(f"  {len(recs26)} games, league_rpg={lrpg26:.3f}")

    recs25 = lrpg25 = None
    if not fast:
        print("Gathering 2025 full (predict 2025, features 2024) "
              "-- may fetch from API on first run...")
        recs25, lrpg25 = gather(2025)
        print(f"  {len(recs25)} games, league_rpg={lrpg25:.3f}")

    print("\n" + "=" * 70)
    print("BASELINE params  " + _fmt_params(BASELINE))
    print("=" * 70)
    _line("baseline @ 2026 slice", recs26, lrpg26, BASELINE)
    if recs25:
        _line("baseline @ 2025 full", recs25, lrpg25, BASELINE)

    print("\nGrid-searching 2026 slice (min log loss over "
          f"{len(SDS)*len(IP_SHARES)*len(REGRESS_IPS)*len(HFAS)} combos)...")
    best26, ll26 = grid_search(recs26, lrpg26)
    print("  best-on-2026  " + _fmt_params(best26) + f"  (logLoss {ll26:.4f})")

    best25 = bestpool = None
    if recs25:
        print("Grid-searching 2025 full...")
        best25, ll25 = grid_search(recs25, lrpg25)
        print("  best-on-2025  " + _fmt_params(best25) + f"  (logLoss {ll25:.4f})")
        print("Grid-searching POOLED (2026 slice + 2025 full)...")
        bestpool, llp = grid_search_pooled([(recs26, lrpg26), (recs25, lrpg25)])
        print("  best-pooled   " + _fmt_params(bestpool) + f"  (logLoss {llp:.4f})")

    print("\n" + "=" * 70)
    print("CROSS-EVALUATION (each param set on BOTH datasets)")
    print("=" * 70)

    def block(name, params):
        print(f"\n[{name}]  {_fmt_params(params)}")
        _line("@ 2026 slice", recs26, lrpg26, params)
        if recs25:
            _line("@ 2025 full", recs25, lrpg25, params)

    block("baseline", BASELINE)
    block("best-on-2026", best26)
    if best25:
        block("best-on-2025", best25)
    if bestpool:
        block("best-pooled (log-loss optimal, costs accuracy)", bestpool)
    # Conservative recommendation: only retune the two genuine CALIBRATION knobs
    # (sharpness SD_DIFF and home bias HFA_RUNS); leave the offense/pitcher
    # weighting (IP_SHARE, REGRESS_IP) at baseline so accuracy is barely touched.
    block("RECOMMENDED conservative (retune SD+HFA only)",
          dict(sd_diff=4.8, ip_share=0.60, regress_ip=50.0, hfa=0.42))

    print("\n" + "=" * 70)
    print("Baseline reference: 2026 slice acc 0.559 | Brier 0.2486 | logLoss 0.6906")
    print("                    base-rate Brier 0.2488 | base-rate logLoss 0.6906")
    print("=" * 70)


if __name__ == "__main__":
    main()
