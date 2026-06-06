"""Experiment: pitcher-depth — improve the STARTER signal.

We keep the rest of AlgoBall's pipeline IDENTICAL to the baseline (team-offense
factor, expected_runs transform, Phi win-prob with SD_DIFF=4.3 / HFA=0.37, park
factors) and ONLY change how a starting pitcher is rated. We compare:

  baseline_repro   single prior-season box-FIP, regress 50 IP to LEAGUE_FIP=4.10
                   -> must reproduce the published 0.2486 Brier / 0.559 acc.
  fip_1yr          single prior-season FIP (API sabermetrics 'fip'), league ref
                   computed from the pool (apples-to-apples control for xfip).
  xfip_1yr         single prior-season xFIP instead of FIP.
  fip_2yr          IP+recency-weighted blend of the two prior seasons' FIP.
  xfip_2yr         IP+recency-weighted blend of the two prior seasons' xFIP.
  blend_2yr        average of fip_2yr and xfip_2yr effective ratings.

WHY xFIP / multi-season: a starter's prior-season FIP is noisy (HR/FB luck,
small samples). xFIP normalizes HR rate to league average and is empirically a
better predictor of a pitcher's NEXT-season run prevention than FIP; blending
two prior seasons (recency-weighted, IP-weighted) further cuts sample noise.

LOOKAHEAD SAFETY: to predict a game in season Y we use ONLY full prior-season
aggregates (Y-1 and Y-2). For Y=2026 that is 2025 + 2024; for Y=2025 it is
2024 + 2023. The league reference for each metric is the IP-weighted mean of
that metric over the (Y-1) starter pool — itself a prior-season aggregate. No
season-Y information and no game result is ever read before predicting that
game. The set of probable starters per game comes from the schedule's
pre-game `probablePitcher` field. Park/HFA/team-offense are unchanged from the
lookahead-safe baseline.

Run:
  PYTHONPATH=src python3 experiments/pitcher-depth.py
"""
from __future__ import annotations

import json
import math
import os
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- read-only imports from the existing project (no shared files edited) ----
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
from algoball.model.runs import expected_runs
from algoball.model.winprob import win_probability_from_runs

# Same cache dir & polite pattern as ingest/mlb.py (additive, read-through).
_BASE = "https://statsapi.mlb.com/api/v1"
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")

REG_IP = 50.0          # innings of league-average metric to regress toward
RECENCY_W_OLD = 0.6    # weight on the Y-2 season relative to Y-1 (=1.0)


def _cached(key: str, url: str) -> dict:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    req = urllib.request.Request(url, headers={"User-Agent": "algoball-backtest/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def _ip_to_float(ip) -> float:
    if not ip:
        return 0.0
    whole, _, frac = str(ip).partition(".")
    return int(whole or 0) + (int(frac or 0) / 3.0)


def get_pitcher_saber(pid: int, season: int) -> Optional[Dict[str, float]]:
    """Prior-season FIP & xFIP from the API sabermetrics group (+ IP from the
    standard pitching line). Returns None if the pitcher has no usable line."""
    if not pid:
        return None
    # IP and box-FIP come from the existing helper (already cached as pit_*).
    box = get_pitcher_fip(pid, season)
    ip = box["ip"] if box else 0.0
    url = f"{_BASE}/people/{pid}/stats?stats=sabermetrics&group=pitching&season={season}"
    raw = _cached(f"saber_{pid}_{season}", url)
    stats = raw.get("stats") or []
    splits = stats[0].get("splits") if stats else None
    if not splits:
        return None
    st = splits[0]["stat"]
    fip = st.get("fip")
    xfip = st.get("xfip")
    if fip is None:
        return None
    if ip <= 0.0:
        # Fall back to innings the sabermetrics endpoint implies, else skip.
        return None
    if xfip is None:
        xfip = fip
    return {"ip": ip, "fip": float(fip), "xfip": float(xfip)}


# --- pitcher rating -----------------------------------------------------------
@dataclass
class RatingConfig:
    metric: str            # 'fip' or 'xfip'
    n_seasons: int         # 1 or 2 prior seasons
    use_box_fip: bool = False  # baseline path: use get_pitcher_fip's box FIP
    blend_with: Optional[str] = None  # if set, average this metric in too


def _season_value(pid: int, season: int, metric: str, use_box: bool
                  ) -> Optional[Tuple[float, float]]:
    """(ip, value) for one pitcher-season, or None."""
    if use_box:
        d = get_pitcher_fip(pid, season)
        if not d:
            return None
        return d["ip"], d["fip"]
    d = get_pitcher_saber(pid, season)
    if not d:
        return None
    return d["ip"], d[metric]


def regressed_rating(pid: Optional[int], feature_season: int, cfg: RatingConfig,
                     league_ref: float) -> float:
    """Effective FIP-like number for a starter, lookahead-safe.

    Recency+IP-weighted blend of up to `n_seasons` prior seasons, regressed
    toward the league reference with REG_IP innings."""
    if not pid:
        return league_ref
    metrics = [cfg.metric] + ([cfg.blend_with] if cfg.blend_with else [])
    blended_vals = []
    eff_ip_for_blend = 0.0
    for m in metrics:
        seasons = [(feature_season, 1.0)]
        if cfg.n_seasons >= 2:
            seasons.append((feature_season - 1, RECENCY_W_OLD))
        num = 0.0
        eff_ip = 0.0
        for s, w in seasons:
            sv = _season_value(pid, s, m, cfg.use_box_fip)
            if not sv:
                continue
            ip, val = sv
            num += w * ip * val
            eff_ip += w * ip
        if eff_ip <= 0.0:
            blended_vals.append((league_ref, 0.0))
            continue
        wmetric = num / eff_ip
        eff_ip_for_blend = max(eff_ip_for_blend, eff_ip)
        blended_vals.append((wmetric, eff_ip))
    # average the (possibly two) metric estimates
    if not blended_vals:
        return league_ref
    avg_val = sum(v for v, _ in blended_vals) / len(blended_vals)
    eff_ip = max((ip for _, ip in blended_vals), default=0.0)
    if eff_ip <= 0.0:
        return league_ref
    return (eff_ip * avg_val + REG_IP * league_ref) / (eff_ip + REG_IP)


# --- league reference per metric (prior-season pool aggregate) ----------------
def league_reference(pitcher_ids, feature_season: int, metric: str, use_box: bool
                     ) -> float:
    num = 0.0
    den = 0.0
    for pid in pitcher_ids:
        sv = _season_value(pid, feature_season, metric, use_box)
        if not sv:
            continue
        ip, val = sv
        num += ip * val
        den += ip
    if den <= 0.0:
        return LEAGUE_FIP_FALLBACK
    return num / den


# --- prediction pipeline (identical to baseline except pitcher rating) --------
@dataclass
class Prediction:
    p_home: float
    home_won: int


def build_predictions(predict_season: int, cfg: RatingConfig,
                      end_date: Optional[str] = None,
                      fixed_league_ref: Optional[float] = None) -> List[Prediction]:
    feature_season = predict_season - 1
    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    team_ids = {g["home_id"] for g in games} | {g["away_id"] for g in games}
    team_rpg = {}
    for tid in team_ids:
        rpg = get_team_runs_per_game(tid, feature_season)
        if rpg:
            team_rpg[tid] = rpg
    league_rpg = sum(team_rpg.values()) / len(team_rpg)

    sp_ids = {g["home_sp"] for g in games if g["home_sp"]} | \
             {g["away_sp"] for g in games if g["away_sp"]}
    if fixed_league_ref is not None:
        league_ref = fixed_league_ref
    else:
        league_ref = league_reference(sp_ids, feature_season, cfg.metric, cfg.use_box_fip)

    rating_cache: Dict[Optional[int], float] = {}

    def rate(pid):
        if pid not in rating_cache:
            rating_cache[pid] = regressed_rating(pid, feature_season, cfg, league_ref)
        return rating_cache[pid]

    preds: List[Prediction] = []
    for g in games:
        if g["home_id"] not in team_rpg or g["away_id"] not in team_rpg:
            continue
        home_off = team_rpg[g["home_id"]] / league_rpg
        away_off = team_rpg[g["away_id"]] / league_rpg
        home_fip = rate(g["home_sp"])
        away_fip = rate(g["away_sp"])
        park = PARK_FACTORS.get(g["venue"], DEFAULT_PARK)
        er_home = expected_runs(league_rpg, home_off, away_fip, league_ref, park)
        er_away = expected_runs(league_rpg, away_off, home_fip, league_ref, park)
        p_home = win_probability_from_runs(er_home, er_away)
        preds.append(Prediction(p_home, 1 if g["home_won"] else 0))
    return preds


# --- metrics ------------------------------------------------------------------
def brier(preds):  return sum((p.p_home - p.home_won) ** 2 for p in preds) / len(preds)
def accuracy(preds): return sum((p.p_home >= 0.5) == bool(p.home_won) for p in preds) / len(preds)
def log_loss(preds):
    eps = 1e-6
    return sum(-(p.home_won * math.log(min(1 - eps, max(eps, p.p_home))) +
                 (1 - p.home_won) * math.log(1 - min(1 - eps, max(eps, p.p_home))))
               for p in preds) / len(preds)


def run_variant(name, predict_season, cfg, end_date=None, fixed_league_ref=None):
    preds = build_predictions(predict_season, cfg, end_date, fixed_league_ref)
    n = len(preds)
    base_rate = sum(p.home_won for p in preds) / n
    base_brier = sum((base_rate - p.home_won) ** 2 for p in preds) / n
    row = dict(name=name, n=n, acc=accuracy(preds), brier=brier(preds),
               logloss=log_loss(preds), base_rate=base_rate, base_brier=base_brier)
    return row, preds


def print_table(title, rows):
    print("=" * 78)
    print(title)
    print("=" * 78)
    print(f"{'variant':18}{'n':>5}{'acc':>8}{'Brier':>9}{'logLoss':>9}"
          f"{'dBrier':>9}{'dLogL':>9}")
    base = rows[0]
    for r in rows:
        dB = r["brier"] - base["brier"]
        dL = r["logloss"] - base["logloss"]
        print(f"{r['name']:18}{r['n']:>5}{r['acc']:>8.3f}{r['brier']:>9.4f}"
              f"{r['logloss']:>9.4f}{dB:>+9.4f}{dL:>+9.4f}")
    b = rows[0]
    print("-" * 78)
    print(f"base home-win rate {b['base_rate']:.3f}  |  base-rate Brier {b['base_brier']:.4f}")
    print("=" * 78)


def main(argv=None):
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    variants = [
        ("baseline_repro", RatingConfig("fip", 1, use_box_fip=True), LEAGUE_FIP_FALLBACK),
        ("fip_1yr",        RatingConfig("fip", 1),  None),
        ("xfip_1yr",       RatingConfig("xfip", 1), None),
        ("fip_2yr",        RatingConfig("fip", 2),  None),
        ("xfip_2yr",       RatingConfig("xfip", 2), None),
        ("blend_2yr",      RatingConfig("fip", 2, blend_with="xfip"), None),
    ]

    all_slices = [(2026, "2026-04-30"), (2025, None)]
    if argv:
        want = set(int(a) for a in argv)
        slices = [s for s in all_slices if s[0] in want]
    else:
        slices = all_slices

    for season, end in slices:
        rows = []
        for name, cfg, lref in variants:
            row, _ = run_variant(name, season, cfg, end_date=end, fixed_league_ref=lref)
            rows.append(row)
        label = f"predict {season}" + (f" thru {end}" if end else " (full season)")
        print_table(f"PITCHER-DEPTH backtest — {label}, prior-season features", rows)
        print()
        sys.stdout.flush()


if __name__ == "__main__":
    main()
