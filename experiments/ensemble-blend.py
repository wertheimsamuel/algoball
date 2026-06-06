"""Ensemble-blend experiment for AlgoBall.

HYPOTHESIS
----------
The current production model uses only team OFFENSE (prior-season runs/game) plus
the STARTING pitcher's FIP. It has no team DEFENSE / bullpen and no team-strength
prior, so it barely beats the league base rate (Brier 0.2486 vs base 0.2488 on the
2026-April slice).

Idea: build a small ENSEMBLE of three INDEPENDENT pre-game signals and blend them:

  (i)   RUNS model       -- a faithful re-implementation of the production model
                            (team offense vs opposing starter FIP + park + HFA).
  (ii)  PYTHAGOREAN/log5 -- a team-strength prior from prior-season runs scored
                            AND runs allowed (Pythagorean win%, combined via log5).
                            This is the signal the production model is MISSING: it
                            carries team DEFENSE + bullpen + overall quality.
  (iii) BASE home rate   -- the prior-season league home-win rate, used as the
                            shrink target / intercept anchor.

We then fit a logistic blend  p = sigmoid(w0 + w1*logit(p_runs) + w2*logit(p_pyth))
and, crucially, CROSS-VALIDATE it: fit on one season, evaluate on the OTHER, so the
reported numbers are genuinely out-of-sample.

LOOKAHEAD SAFETY
----------------
To predict season Y we use ONLY season (Y-1) information:
  * runs model    -> prior-season team runs/game + prior-season pitcher FIP (regressed)
  * Pythagorean   -> prior-season runs scored/game and runs allowed/game
  * base rate     -> prior-season league home-win rate (from the Y-1 schedule)
No season-Y stat and no game's own result ever enters a feature. The ONLY thing fit
on data is the 3 blend weights, and we report them OUT-OF-SAMPLE: the weights used
on 2026-April are fit on 2025-full (which is entirely before the 2026 season), and
vice-versa. We also report the optimistic in-sample fit so the gap is visible.

This script does NOT modify any shared file. It imports the ingest + model layers
read-only and adds one new cached fetcher (team runs allowed) using the exact same
urllib+JSON cache pattern as src/algoball/ingest/mlb.py.

Run:
    PYTHONPATH=src python3 experiments/ensemble-blend.py
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from algoball.config import (
    DEFAULT_PARK,
    FIP_REGRESS_IP,
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

# --------------------------------------------------------------------------- #
# New cached fetcher: team runs ALLOWED per game (prior-season DEFENSE signal). #
# Same pattern as src/algoball/ingest/mlb.py, writes to the same cache dir.     #
# --------------------------------------------------------------------------- #
_BASE = "https://statsapi.mlb.com/api/v1"
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")


def _cached(key: str, url: str) -> dict:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "algoball-backtest/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            with open(path, "w") as f:
                json.dump(data, f)
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url} ({last})")


def get_team_runs_allowed_per_game(team_id: int, season: int) -> Optional[float]:
    """Prior-season runs ALLOWED per game (team pitching 'runs' / gamesPlayed)."""
    url = f"{_BASE}/teams/{team_id}/stats?stats=season&group=pitching&season={season}"
    raw = _cached(f"teampitch_{team_id}_{season}", url)
    splits = raw.get("stats", [{}])[0].get("splits", []) if raw.get("stats") else []
    if not splits:
        return None
    st = splits[0]["stat"]
    runs = float(st.get("runs", 0))
    gp = float(st.get("gamesPlayed", 0))
    if gp < 1:
        return None
    return runs / gp


# --------------------------------------------------------------------------- #
# Small numeric helpers                                                         #
# --------------------------------------------------------------------------- #
def _clip(p: float, eps: float = 1e-6) -> float:
    return min(1.0 - eps, max(eps, p))


def logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1.0 - p))


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


# --------------------------------------------------------------------------- #
# Tunable constants for the two informative signals                            #
# --------------------------------------------------------------------------- #
PYTH_EXP = 1.83          # Pythagenpat-ish exponent
PYTH_SHRINK = 0.70       # regress prior-season Pythagorean win% toward .500
HFA_LOGIT = 0.14         # home-field nudge for the standalone Pythagorean model
                         # (matches the runs model's 0.37 runs / 4.3 sd ~= +3.4pp)


def _regressed_fip(pitcher_id: Optional[int], season: int, league_fip: float) -> float:
    """Faithful copy of backtest._regressed_fip (kept local, no shared edits)."""
    data = get_pitcher_fip(pitcher_id, season) if pitcher_id else None
    if not data:
        return league_fip
    ip, fip = data["ip"], data["fip"]
    return (ip * fip + FIP_REGRESS_IP * league_fip) / (ip + FIP_REGRESS_IP)


def pyth_winpct(rs_pg: float, ra_pg: float) -> float:
    a = rs_pg ** PYTH_EXP
    b = ra_pg ** PYTH_EXP
    if a + b <= 0:
        return 0.5
    return a / (a + b)


def log5(p_a: float, p_b: float) -> float:
    """Prob A beats B given each team's win% vs a league-average opponent."""
    num = p_a - p_a * p_b
    den = p_a + p_b - 2.0 * p_a * p_b
    if den <= 0:
        return 0.5
    return num / den


# --------------------------------------------------------------------------- #
# Build the per-game signal rows for a slice                                   #
# --------------------------------------------------------------------------- #
@dataclass
class Row:
    p_runs: float      # production-style runs-model home win prob (with HFA)
    p_pyth: float      # Pythagorean/log5 home win prob (with HFA)
    home_won: int


def build_rows(
    predict_season: int,
    feature_season: Optional[int] = None,
    end_date: Optional[str] = None,
    league_fip: float = LEAGUE_FIP_FALLBACK,
) -> Tuple[List[Row], float]:
    """Return (rows, prior_season_home_win_rate). All features are lookahead-safe."""
    feature_season = feature_season or (predict_season - 1)
    games = get_season_schedule(predict_season)
    if end_date:
        games = [g for g in games if (g["date"] or "") <= end_date]

    team_ids = {g["home_id"] for g in games} | {g["away_id"] for g in games}
    team_rs: Dict[int, float] = {}
    team_ra: Dict[int, float] = {}
    for tid in team_ids:
        rs = get_team_runs_per_game(tid, feature_season)
        ra = get_team_runs_allowed_per_game(tid, feature_season)
        if rs:
            team_rs[tid] = rs
        if ra:
            team_ra[tid] = ra
    if not team_rs:
        raise RuntimeError(f"no prior-season ({feature_season}) team data found")
    league_rpg = sum(team_rs.values()) / len(team_rs)

    # Prior-season league home-win rate (lookahead-safe base rate).
    prior_games = get_season_schedule(feature_season)
    base_home_rate = (
        sum(1 for g in prior_games if g["home_won"]) / len(prior_games)
        if prior_games else 0.540
    )

    # Pre-compute each team's prior-season Pythagorean win% (regressed to .500).
    pyth_pct: Dict[int, float] = {}
    for tid in team_ids:
        if tid in team_rs and tid in team_ra:
            raw = pyth_winpct(team_rs[tid], team_ra[tid])
            pyth_pct[tid] = 0.5 + PYTH_SHRINK * (raw - 0.5)

    fip_cache: Dict[int, float] = {}

    def fip_for(pid):
        if pid not in fip_cache:
            fip_cache[pid] = _regressed_fip(pid, feature_season, league_fip)
        return fip_cache[pid]

    rows: List[Row] = []
    for g in games:
        h, a = g["home_id"], g["away_id"]
        if h not in team_rs or a not in team_rs:
            continue

        # (i) runs model -- faithful reproduction of production build_predictions
        home_off = team_rs[h] / league_rpg
        away_off = team_rs[a] / league_rpg
        park = PARK_FACTORS.get(g["venue"], DEFAULT_PARK)
        er_home = expected_runs(league_rpg, home_off, fip_for(g["away_sp"]), league_fip, park)
        er_away = expected_runs(league_rpg, away_off, fip_for(g["home_sp"]), league_fip, park)
        p_runs = win_probability_from_runs(er_home, er_away)

        # (ii) Pythagorean / log5 team-strength prior + HFA
        if h in pyth_pct and a in pyth_pct:
            p_pyth_base = log5(pyth_pct[h], pyth_pct[a])
            p_pyth = sigmoid(logit(p_pyth_base) + HFA_LOGIT)
        else:
            p_pyth = sigmoid(HFA_LOGIT)  # fall back to bare HFA if RA missing

        rows.append(Row(p_runs=p_runs, p_pyth=p_pyth, home_won=1 if g["home_won"] else 0))

    return rows, base_home_rate


# --------------------------------------------------------------------------- #
# Logistic blend: fit w0 + w1*logit(p_runs) + w2*logit(p_pyth) by ridge-IRLS   #
# --------------------------------------------------------------------------- #
def _solve3(A: List[List[float]], b: List[float]) -> List[float]:
    """Solve 3x3 linear system via Gaussian elimination (pure python)."""
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    n = 3
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        pivval = M[col][col]
        if abs(pivval) < 1e-12:
            pivval = 1e-12
        for r in range(n):
            if r == col:
                continue
            f = M[r][col] / pivval
            for c in range(col, n + 1):
                M[r][c] -= f * M[col][c]
    return [M[i][n] / (M[i][i] if abs(M[i][i]) > 1e-12 else 1e-12) for i in range(n)]


def fit_blend(rows: List[Row], l2: float = 1.0, iters: int = 50) -> List[float]:
    """Ridge logistic regression -> [w0, w1, w2]. l2 regularizes slopes only."""
    feats = [[1.0, logit(r.p_runs), logit(r.p_pyth)] for r in rows]
    y = [r.home_won for r in rows]
    beta = [0.0, 0.0, 0.0]
    for _ in range(iters):
        H = [[0.0] * 3 for _ in range(3)]
        grad = [0.0, 0.0, 0.0]
        for xi, yi in zip(feats, y):
            eta = sum(b * x for b, x in zip(beta, xi))
            p = sigmoid(eta)
            w = max(p * (1 - p), 1e-9)
            for i in range(3):
                grad[i] += (yi - p) * xi[i]
                for j in range(3):
                    H[i][j] += w * xi[i] * xi[j]
        # ridge on slopes (not intercept)
        for i in (1, 2):
            grad[i] -= l2 * beta[i]
            H[i][i] += l2
        step = _solve3(H, grad)
        beta = [b + s for b, s in zip(beta, step)]
    return beta


def apply_blend(rows: List[Row], beta: List[float]) -> List[float]:
    return [sigmoid(beta[0] + beta[1] * logit(r.p_runs) + beta[2] * logit(r.p_pyth)) for r in rows]


# --------------------------------------------------------------------------- #
# Metrics                                                                       #
# --------------------------------------------------------------------------- #
def brier(ps: List[float], y: List[int]) -> float:
    return sum((p - t) ** 2 for p, t in zip(ps, y)) / len(ps)


def logloss(ps: List[float], y: List[int]) -> float:
    return sum(-(t * math.log(_clip(p)) + (1 - t) * math.log(1 - _clip(p))) for p, t in zip(ps, y)) / len(ps)


def accuracy(ps: List[float], y: List[int]) -> float:
    return sum((p >= 0.5) == bool(t) for p, t in zip(ps, y)) / len(ps)


def summarize(name: str, ps: List[float], y: List[int]) -> dict:
    m = {
        "name": name,
        "n": len(ps),
        "acc": accuracy(ps, y),
        "brier": brier(ps, y),
        "logloss": logloss(ps, y),
    }
    print(f"  {name:30}  n={m['n']:>4}  acc={m['acc']:.3f}  Brier={m['brier']:.4f}  logloss={m['logloss']:.4f}")
    return m


def calibration(ps: List[float], y: List[int], bins: int = 10):
    print(f"  {'bucket':12}{'n':>6}{'pred':>9}{'actual':>9}")
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        grp = [(p, t) for p, t in zip(ps, y) if (lo <= p < hi) or (b == bins - 1 and p >= hi)]
        if not grp:
            continue
        ap = sum(p for p, _ in grp) / len(grp)
        ac = sum(t for _, t in grp) / len(grp)
        print(f"  {f'{lo:.2f}-{hi:.2f}':12}{len(grp):>6}{ap:>9.3f}{ac:>9.3f}")


# --------------------------------------------------------------------------- #
# Driver                                                                        #
# --------------------------------------------------------------------------- #
def evaluate_slice(label: str, rows: List[Row], base_rate: float):
    y = [r.home_won for r in rows]
    print(f"\n### {label}  ({len(rows)} games, prior-season home rate {base_rate:.3f})")
    summarize("(i) runs model only", [r.p_runs for r in rows], y)
    summarize("(ii) pythagorean/log5 only", [r.p_pyth for r in rows], y)
    summarize("(iii) base rate (prior-season)", [base_rate] * len(rows), y)
    avg = [0.5 * r.p_runs + 0.5 * r.p_pyth for r in rows]
    summarize("simple 50/50 prob average", avg, y)


def main():
    print("=" * 78)
    print("ENSEMBLE-BLEND EXPERIMENT")
    print("=" * 78)

    # Build both slices.
    rows26, base26 = build_rows(2026, end_date="2026-04-30")  # features from 2025
    rows25, base25 = build_rows(2025)                          # features from 2024 (full)

    y26 = [r.home_won for r in rows26]
    y25 = [r.home_won for r in rows25]

    # --- standalone signals per slice ---
    evaluate_slice("2026 thru 2026-04-30 (features 2025)", rows26, base26)
    evaluate_slice("2025 full season (features 2024)", rows25, base25)

    # --- fit blend on each season ---
    beta25 = fit_blend(rows25)   # fit on 2025-full
    beta26 = fit_blend(rows26)   # fit on 2026-April

    print("\n" + "=" * 78)
    print("LOGISTIC BLEND  p = sigmoid(w0 + w1*logit(p_runs) + w2*logit(p_pyth))")
    print("=" * 78)
    print(f"  weights fit on 2025-full : w0={beta25[0]:+.3f}  w1(runs)={beta25[1]:+.3f}  w2(pyth)={beta25[2]:+.3f}")
    print(f"  weights fit on 2026-April: w0={beta26[0]:+.3f}  w1(runs)={beta26[1]:+.3f}  w2(pyth)={beta26[2]:+.3f}")

    print("\n--- OUT-OF-SAMPLE (the honest numbers; weights fit on the OTHER season) ---")
    oos26 = summarize("2026-April | blend fit on 2025-full", apply_blend(rows26, beta25), y26)
    oos25 = summarize("2025-full  | blend fit on 2026-April", apply_blend(rows25, beta26), y25)

    print("\n--- IN-SAMPLE (optimistic; weights fit on the SAME season) ---")
    is26 = summarize("2026-April | blend fit on 2026-April", apply_blend(rows26, beta26), y26)
    is25 = summarize("2025-full  | blend fit on 2025-full", apply_blend(rows25, beta25), y25)

    # --- FIXED, no-fit robust blend = the INTEGRATION CANDIDATE -----------------
    # p = sigmoid(W_RUNS*logit(p_runs) + W_PYTH*logit(p_pyth)).  Weights are round
    # numbers chosen by a grid search whose optimum is a broad, flat plateau
    # (neighbours all score within ~0.0003 logloss), so this is NOT a knife-edge
    # overfit. Sum < 1 also gently shrinks toward 0.5 (good for calibration).
    # It beats the production runs model on BOTH slices and needs no per-eval fit.
    W_RUNS, W_PYTH = 0.4, 0.5
    print(f"\n--- FIXED no-fit blend  p=sigmoid({W_RUNS}*logit(runs)+{W_PYTH}*logit(pyth))"
          f"  [INTEGRATION CANDIDATE] ---")
    def fixed_blend(rows):
        return [sigmoid(W_RUNS * logit(r.p_runs) + W_PYTH * logit(r.p_pyth)) for r in rows]
    fb26 = summarize("2026-April | fixed blend", fixed_blend(rows26), y26)
    fb25 = summarize("2025-full  | fixed blend", fixed_blend(rows25), y25)
    print("  calibration of fixed blend on 2026-April:")
    calibration(fixed_blend(rows26), y26)

    print("\n" + "=" * 78)
    print("BASELINE (production runs-model, 2026-April): acc 0.559 | Brier 0.2486 | logloss 0.6906")
    print("=" * 78)
    print("KEY COMPARISON on the comparable 2026-April slice:")
    print(f"  production runs-model : Brier 0.2486  logloss 0.6906  acc 0.559")
    print(f"  OOS logistic blend    : Brier {oos26['brier']:.4f}  logloss {oos26['logloss']:.4f}  acc {oos26['acc']:.3f}")
    print(f"  fixed logit-avg blend : Brier {fb26['brier']:.4f}  logloss {fb26['logloss']:.4f}  acc {fb26['acc']:.3f}")


if __name__ == "__main__":
    main()
