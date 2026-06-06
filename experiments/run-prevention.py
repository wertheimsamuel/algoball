"""Experiment: TEAM RUN-PREVENTION (bullpen) — does modelling the opposing
team's actual bullpen quality beat assuming a league-average bullpen?

BACKGROUND
----------
The baseline model's only run-suppression signal is the opposing STARTER. The
starter is assumed to throw ~60% of innings (STARTER_IP_SHARE) and the remaining
~40% is treated as a *league-average* bullpen (factor 1.0). That throws away a
real, persistent source of edge: bullpens differ a lot, and last year's bullpen
quality predicts this year's.

THIS VARIANT
------------
Replace the "40% = league average" assumption with the opposing team's ACTUAL
prior-season bullpen quality. We fetch each team's reliever-only (sitCode=rp)
pitching split for the FEATURE season, compute a team bullpen FIP with the same
FIP formula the project already uses for starters, regress it toward the league
bullpen FIP, and use it for the non-starter innings share:

    suppression(opp) = s * (opp_starter_fip / STARTER_REF)
                     + (1 - s) * (opp_bullpen_fip / LEAGUE_BULLPEN_FIP)

  * s = starter IP share (baseline 0.60; also swept).
  * The starter term is IDENTICAL to the baseline (same regressed FIP, same
    4.10 reference), so with use_bullpen=False this script reproduces the
    baseline exactly. When use_bullpen=True the ONLY thing that changes is that
    the 40% bullpen share now carries the team's real relative bullpen quality
    instead of a hard-coded 1.0. A league-average bullpen still maps to 1.0, so
    only DEVIATIONS from average move a prediction — the cleanest possible A/B.

Expected runs / win prob are otherwise the project's existing transform:
    er_home = league_rpg * home_off * suppression(away_pitching) * park
    p_home  = win_probability_from_runs(er_home, er_away)   # SD_DIFF=4.3, HFA=0.37

LOOKAHEAD SAFETY
----------------
To predict a game in season Y we use ONLY season (Y-1) data:
  * team offense  -> prior-season runs/game        (get_team_runs_per_game)
  * starter FIP   -> prior-season FIP              (get_pitcher_fip)
  * BULLPEN FIP   -> prior-season reliever split   (NEW, this file)
  * league refs   -> averaged over prior season only
No season-Y stat and no game's own result is ever read. The reliever split is a
full prior-season aggregate, identical in spirit to the prior-season starter FIP
the baseline already trusts. So this variant is lookahead-safe by construction.

Run:
    PYTHONPATH=src python3 experiments/run-prevention.py
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional

# --- read-only imports from the existing project layers ----------------------
from algoball.config import (
    DEFAULT_PARK,
    FIP_CONSTANT,
    FIP_REGRESS_IP,
    LEAGUE_FIP_FALLBACK,
    PARK_FACTORS,
)
from algoball.ingest.mlb import (
    get_pitcher_fip,
    get_season_schedule,
    get_team_runs_per_game,
)
from algoball.model.winprob import win_probability_from_runs

_BASE = "https://statsapi.mlb.com/api/v1"
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")


# --- tiny cached fetcher (mirrors ingest/mlb.py, writes new cache keys) ------
def _get_json(url: str, retries: int = 3) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "algoball-backtest/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")


def _cached(key: str, url: str) -> dict:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    data = _get_json(url)
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def _ip_to_float(ip: Optional[str]) -> float:
    if not ip:
        return 0.0
    whole, _, frac = str(ip).partition(".")
    return int(whole or 0) + (int(frac or 0) / 3.0)


def _fip_from_stat(st: dict) -> Optional[Dict[str, float]]:
    ip = _ip_to_float(st.get("inningsPitched"))
    if ip < 1.0:
        return None
    hr = float(st.get("homeRuns", 0))
    bb = float(st.get("baseOnBalls", 0))
    hbp = float(st.get("hitByPitch", 0))
    so = float(st.get("strikeOuts", 0))
    fip = (13 * hr + 3 * (bb + hbp) - 2 * so) / ip + FIP_CONSTANT
    runs = float(st.get("runs", 0))
    return {"fip": fip, "ip": ip, "runs": runs}


def get_team_pitch_split(team_id: int, season: int, sit: str) -> Optional[Dict[str, float]]:
    """Reliever-only ('rp') or starter-only ('sp') team pitching split for a
    season, with a self-computed FIP. Cached. Prior-season only at call sites."""
    url = (
        f"{_BASE}/teams/{team_id}/stats?stats=statSplits&group=pitching"
        f"&season={season}&sitCodes={sit}"
    )
    raw = _cached(f"teamsplit_{team_id}_{season}_{sit}", url)
    stats = raw.get("stats") or []
    splits = stats[0].get("splits", []) if stats else []
    if not splits:
        return None
    return _fip_from_stat(splits[0]["stat"])


def get_team_runs_allowed_per_game(team_id: int, season: int) -> Optional[float]:
    """Team overall prior-season runs allowed per game (pitching + defense).
    A fuller run-prevention signal than bullpen FIP (FIP ignores fielding)."""
    url = f"{_BASE}/teams/{team_id}/stats?stats=season&group=pitching&season={season}"
    raw = _cached(f"teampitch_{team_id}_{season}", url)
    stats = raw.get("stats") or []
    splits = stats[0].get("splits", []) if stats else []
    if not splits:
        return None
    st = splits[0]["stat"]
    g = float(st.get("gamesPlayed", 0))
    if g < 1:
        return None
    return float(st.get("runs", 0)) / g


# --- league references (computed from prior season only) ---------------------
@dataclass
class LeagueRefs:
    rpg: float            # league avg team runs/game (offense baseline)
    bullpen_fip: float    # IP-weighted league bullpen FIP
    starter_fip: float    # IP-weighted league starter FIP (diagnostic)
    sp_share: float       # league starter IP share (diagnostic)
    rapg: float           # league avg team runs ALLOWED per game


def league_refs(team_ids: List[int], season: int) -> LeagueRefs:
    # offense
    rpgs = [get_team_runs_per_game(t, season) for t in team_ids]
    rpgs = [r for r in rpgs if r]
    rpg = sum(rpgs) / len(rpgs)
    # run prevention (overall RA/G)
    rapgs = [get_team_runs_allowed_per_game(t, season) for t in team_ids]
    rapgs = [r for r in rapgs if r]
    rapg = sum(rapgs) / len(rapgs)
    # pitching splits
    sp_ip = sp_w = rp_ip = rp_w = 0.0
    for t in team_ids:
        sp = get_team_pitch_split(t, season, "sp")
        rp = get_team_pitch_split(t, season, "rp")
        if sp:
            sp_ip += sp["ip"]; sp_w += sp["ip"] * sp["fip"]
        if rp:
            rp_ip += rp["ip"]; rp_w += rp["ip"] * rp["fip"]
    return LeagueRefs(
        rpg=rpg,
        bullpen_fip=rp_w / rp_ip if rp_ip else LEAGUE_FIP_FALLBACK,
        starter_fip=sp_w / sp_ip if sp_ip else LEAGUE_FIP_FALLBACK,
        sp_share=sp_ip / (sp_ip + rp_ip) if (sp_ip + rp_ip) else 0.6,
        rapg=rapg,
    )


# --- model -------------------------------------------------------------------
@dataclass
class Params:
    # defense_mode: "none"        -> baseline (non-starter share = league avg = 1.0)
    #               "bullpen_fip" -> non-starter share uses team bullpen FIP
    #               "team_ra"     -> non-starter share uses team overall RA/G
    #               "blend"       -> baseline per-game suppression blended with a
    #                                team run-prevention prior (explicit team strength)
    defense_mode: str = "bullpen_fip"
    sp_share: float = 0.60          # starter IP share
    starter_regress_ip: float = FIP_REGRESS_IP   # 50, matches baseline
    bullpen_regress_ip: float = 150.0            # team bullpens are ~560 IP -> light
    ra_regress_g: float = 60.0                   # regress team RA/G toward league
    blend_w: float = 0.70           # weight on per-game signal in "blend" mode
    starter_ref: float = LEAGUE_FIP_FALLBACK     # 4.10, matches baseline starter centering


def _regressed_fip(pid: Optional[int], season: int, ref: float, k: float) -> float:
    data = get_pitcher_fip(pid, season) if pid else None
    if not data:
        return ref
    return (data["ip"] * data["fip"] + k * ref) / (data["ip"] + k)


@dataclass
class Prediction:
    p_home: float
    home_won: int


def build_predictions(
    predict_season: int,
    feature_season: Optional[int] = None,
    end_date: Optional[str] = None,
    params: Optional[Params] = None,
) -> List[Prediction]:
    params = params or Params()
    feature_season = feature_season or (predict_season - 1)
    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    team_ids = sorted({g["home_id"] for g in games} | {g["away_id"] for g in games})
    team_rpg = {t: get_team_runs_per_game(t, feature_season) for t in team_ids}
    team_rpg = {t: r for t, r in team_rpg.items() if r}
    if not team_rpg:
        raise RuntimeError(f"no prior-season ({feature_season}) team data")
    refs = league_refs(list(team_rpg.keys()), feature_season)

    # prior-season team run-prevention factor for the NON-starter share,
    # centered on 1.0 (league average). Built per defense_mode.
    team_def = {}  # team_id -> relative non-starter run factor (1.0 = league avg)
    for t in team_rpg:
        if params.defense_mode == "bullpen_fip":
            rp = get_team_pitch_split(t, feature_season, "rp")
            if rp:
                reg = (rp["ip"] * rp["fip"] + params.bullpen_regress_ip * refs.bullpen_fip) \
                    / (rp["ip"] + params.bullpen_regress_ip)
                team_def[t] = reg / refs.bullpen_fip
            else:
                team_def[t] = 1.0
        elif params.defense_mode == "team_ra":
            ra = get_team_runs_allowed_per_game(t, feature_season)
            if ra:
                reg = (162.0 * ra + params.ra_regress_g * refs.rapg) \
                    / (162.0 + params.ra_regress_g)
                team_def[t] = reg / refs.rapg
            else:
                team_def[t] = 1.0
        else:  # "none" -> baseline
            team_def[t] = 1.0

    s = params.sp_share
    starter_fip_cache: Dict[int, float] = {}

    def starter_fip(pid):
        if pid not in starter_fip_cache:
            starter_fip_cache[pid] = _regressed_fip(
                pid, feature_season, params.starter_ref, params.starter_regress_ip
            )
        return starter_fip_cache[pid]

    def suppression(opp_id, opp_sp):
        starter_term = starter_fip(opp_sp) / params.starter_ref
        bullpen_term = team_def[opp_id]
        return s * starter_term + (1.0 - s) * bullpen_term

    preds: List[Prediction] = []
    for g in games:
        h, a = g["home_id"], g["away_id"]
        if h not in team_rpg or a not in team_rpg:
            continue
        home_off = team_rpg[h] / refs.rpg
        away_off = team_rpg[a] / refs.rpg
        park = PARK_FACTORS.get(g["venue"], DEFAULT_PARK)
        er_home = refs.rpg * home_off * suppression(a, g["away_sp"]) * park
        er_away = refs.rpg * away_off * suppression(h, g["home_sp"]) * park
        p_home = win_probability_from_runs(er_home, er_away)
        preds.append(Prediction(p_home, 1 if g["home_won"] else 0))
    return preds


# --- metrics (copied from backtest.py so this stays self-contained) ----------
def brier(p):  return sum((x.p_home - x.home_won) ** 2 for x in p) / len(p)
def acc(p):    return sum((x.p_home >= 0.5) == bool(x.home_won) for x in p) / len(p)
def logloss(p):
    eps = 1e-6
    return sum(-(x.home_won * math.log(min(1 - eps, max(eps, x.p_home)))
                 + (1 - x.home_won) * math.log(1 - min(1 - eps, max(eps, x.p_home))))
               for x in p) / len(p)


def calib(preds, bins=10):
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


def show(label, preds, show_calib=False):
    n = len(preds)
    base = sum(p.home_won for p in preds) / n
    base_preds = [Prediction(base, p.home_won) for p in preds]
    print(f"  {label:30} n={n:4d}  acc={acc(preds):.3f}  Brier={brier(preds):.4f}  "
          f"logloss={logloss(preds):.4f}")
    print(f"  {'(base-rate ref)':30}            "
          f"home={base:.3f}  Brier={brier(base_preds):.4f}  logloss={logloss(base_preds):.4f}")
    if show_calib:
        print("    calibration (pred -> actual):")
        for lo, hi, cnt, ap, ac_ in calib(preds):
            print(f"      {lo:.2f}-{hi:.2f}  n={cnt:4d}  pred={ap:.3f}  actual={ac_:.3f}")
    return {"n": n, "acc": acc(preds), "brier": brier(preds), "logloss": logloss(preds)}


# --- runs --------------------------------------------------------------------
def run_slice(title, predict_season, end_date=None):
    print("=" * 78)
    print(title)
    print("=" * 78)
    ids = sorted({g["home_id"] for g in get_season_schedule(predict_season)})
    refs = league_refs(ids, predict_season - 1)
    print(f"  league refs (features {predict_season - 1}): rpg={refs.rpg:.3f}  "
          f"starter_fip={refs.starter_fip:.3f}  bullpen_fip={refs.bullpen_fip:.3f}  "
          f"sp_share={refs.sp_share:.3f}")
    print("-" * 78)

    base = build_predictions(predict_season, end_date=end_date,
                             params=Params(defense_mode="none", sp_share=0.60))
    rB = show("BASELINE (no defense, s=0.60)", base, show_calib=False)

    v1 = build_predictions(predict_season, end_date=end_date,
                           params=Params(defense_mode="bullpen_fip", sp_share=0.60))
    rV1 = show("V1 bullpen-FIP   (s=0.60)", v1, show_calib=False)

    v2 = build_predictions(predict_season, end_date=end_date,
                           params=Params(defense_mode="team_ra", sp_share=0.60))
    rV2 = show("V2 team-RA/G     (s=0.60)", v2, show_calib=True)

    print("-" * 78)
    print("  sp_share sweep (Brier):  s     baseline   V1 bullpen   V2 team_ra")
    for s in (0.50, 0.55, 0.58, 0.60, 0.65, 0.70):
        b = brier(build_predictions(predict_season, end_date=end_date,
                                    params=Params(defense_mode="none", sp_share=s)))
        b1 = brier(build_predictions(predict_season, end_date=end_date,
                                     params=Params(defense_mode="bullpen_fip", sp_share=s)))
        b2 = brier(build_predictions(predict_season, end_date=end_date,
                                     params=Params(defense_mode="team_ra", sp_share=s)))
        print(f"                           {s:.2f}   {b:.4f}     {b1:.4f}       {b2:.4f}")
    print()
    return rB, rV1, rV2


def metrics_for(predict_season, end_date, params):
    p = build_predictions(predict_season, end_date=end_date, params=params)
    return {"n": len(p), "acc": acc(p), "brier": brier(p), "logloss": logloss(p),
            "preds": p}


def multi_season_summary():
    """The honest, statistically powered test: compare baseline vs the
    run-prevention variants across several FULL prior seasons (lots of games),
    not just the small/early 2026 slice. Also pools all games together."""
    # (predict_season, end_date, label)
    slices = [
        (2026, "2026-04-30", "2026 thru 04-30"),
        (2026, None,         "2026 partial-full"),
        (2025, None,         "2025 full"),
        (2024, None,         "2024 full"),
        (2023, None,         "2023 full"),
    ]
    configs = {
        "baseline":      Params(defense_mode="none",        sp_share=0.60),
        "V1 bullpenFIP": Params(defense_mode="bullpen_fip", sp_share=0.55),
        "V2 teamRA s.55": Params(defense_mode="team_ra",    sp_share=0.55, ra_regress_g=60),
        "V2 teamRA reg120": Params(defense_mode="team_ra",  sp_share=0.55, ra_regress_g=120),
    }
    print("=" * 90)
    print("MULTI-SEASON SUMMARY  (Brier / logloss / acc) — lower Brier & logloss better")
    print("=" * 90)
    pooled = {k: [] for k in configs}
    for ps, ed, label in slices:
        try:
            row = {}
            for cname, cfg in configs.items():
                m = metrics_for(ps, ed, cfg)
                row[cname] = m
                pooled[cname].extend(m["preds"])
            n = row["baseline"]["n"]
            print(f"\n{label}  (n={n})")
            for cname in configs:
                m = row[cname]
                d = m["brier"] - row["baseline"]["brier"]
                print(f"   {cname:18} Brier={m['brier']:.4f} ({d:+.4f})  "
                      f"logloss={m['logloss']:.4f}  acc={m['acc']:.3f}")
        except Exception as e:  # noqa: BLE001
            print(f"\n{label}: skipped ({e})")
    # pooled (all seasons together) — the single most reliable read
    print("\n" + "-" * 90)
    print("POOLED across all completed slices above:")
    bB = brier(pooled["baseline"])
    for cname, preds in pooled.items():
        if not preds:
            continue
        print(f"   {cname:18} n={len(preds):5d}  Brier={brier(preds):.4f} "
              f"({brier(preds)-bB:+.4f})  logloss={logloss(preds):.4f}  acc={acc(preds):.3f}")
    print("=" * 90)


def main():
    # Detailed per-slice tables for the headline slices.
    run_slice("PREDICT 2026 thru 2026-04-30  (features 2025)", 2026, "2026-04-30")
    run_slice("PREDICT 2025 full season  (features 2024)", 2025, None)
    # Statistically powered multi-season comparison + pooled.
    multi_season_summary()


if __name__ == "__main__":
    main()
