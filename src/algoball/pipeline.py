"""The daily pre-game pipeline — one run, then exit.

Flow (docs/CONCEPT.md): get today's schedule -> drop started games -> build the
model's own odds (validated runs+prior blend) -> ONE Odds API call -> de-vig +
line-shop -> guardrails -> write public/index.html + data/<date>.json. Pre-game
only; never touches a live game.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from statistics import median
from typing import List, Optional
from zoneinfo import ZoneInfo

from .config import FIP_REGRESS_IP, LEAGUE_FIP_FALLBACK
from .env import get_odds_api_key
from .ingest.mlb import (
    get_pitcher_fip,
    get_team_runs_allowed_per_game,
    get_team_runs_per_game,
    get_todays_games,
)
from .ingest.odds import get_mlb_moneylines
from .ingest.teams import same_team
from .model.calibrate import MAX_SURFACED_PER_DAY, Status, evaluate_game
from .model.devig import (
    DevigResult,
    american_to_implied,
    devig_additive,
    devig_multiplicative,
)
from .model.game import GameInputs, predict_game
from .model.lineshop import BookLine, shop_lines
from .render.renderer import render_html

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_NY = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


# --- small helpers ----------------------------------------------------------
def _et(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=_UTC)
    return dt_utc.astimezone(_NY)


def _fmt_clock(et: datetime) -> str:
    h = et.hour % 12 or 12
    return f"{h}:{et.minute:02d} {'AM' if et.hour < 12 else 'PM'} ET"


def _start_local(iso_utc: Optional[str]) -> str:
    if not iso_utc:
        return ""
    try:
        dt = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_UTC)
    except ValueError:
        return ""
    return _fmt_clock(_et(dt))


def _now_stamp() -> str:
    et = datetime.now(_NY)
    return f"{et.strftime('%b')} {et.day}, {et.year}, {_fmt_clock(et)}"


def _regressed_fip(pid: Optional[int], season: int, league_fip: float) -> float:
    data = get_pitcher_fip(pid, season) if pid else None
    if not data:
        return league_fip
    return (data["ip"] * data["fip"] + FIP_REGRESS_IP * league_fip) / (data["ip"] + FIP_REGRESS_IP)


def _consensus_devig(books: List[dict]) -> DevigResult:
    """De-vig the consensus (average implied across books) -> fair probabilities."""
    imp_home = sum(american_to_implied(b["home_price"]) for b in books) / len(books)
    imp_away = sum(american_to_implied(b["away_price"]) for b in books) / len(books)
    mult_h, mult_a = devig_multiplicative(imp_home, imp_away)
    add_h, _ = devig_additive(imp_home, imp_away)
    return DevigResult(
        fair_home=mult_h, fair_away=mult_a,
        overround=imp_home + imp_away - 1.0,
        method_gap=abs(mult_h - add_h),
    )


# --- the run ----------------------------------------------------------------
def _get_odds(date: str, refresh: bool = False) -> dict:
    """Fetch tonight's moneylines once and cache by date (so re-runs don't burn credits)."""
    path = os.path.join(_PROJECT_ROOT, "data", "cache", f"odds_{date}.json")
    if os.path.exists(path) and not refresh:
        with open(path) as f:
            return json.load(f)
    odds = get_mlb_moneylines(get_odds_api_key())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(odds, f)
    return odds


def run(date: Optional[str] = None, feature_season: Optional[int] = None,
        refresh_odds: bool = False) -> dict:
    date = date or _et(datetime.utcnow()).strftime("%Y-%m-%d")
    # Use CURRENT-season-to-date stats so the model is comparable to today's market
    # (point-in-time: today's games haven't been played, so this is lookahead-free).
    feature_season = feature_season or int(date[:4])

    # 1) today's games, pre-game only
    todays = get_todays_games(date)
    pregame = [g for g in todays if not g["started"]]
    print(f"[1] {date}: {len(todays)} games on the slate, {len(pregame)} still pre-game.")

    if not pregame:
        ctx = {"date": date, "generated_at": _now_stamp(), "n_games": 0, "n_edges": 0, "edges": [], "games": []}
        _write_outputs(date, ctx)
        return ctx

    # 2) team offense (RS/g) + defense (RA/g) + league baseline
    team_ids = {g["home_id"] for g in pregame} | {g["away_id"] for g in pregame}
    rs, ra = {}, {}
    for tid in team_ids:
        v = get_team_runs_per_game(tid, feature_season)
        w = get_team_runs_allowed_per_game(tid, feature_season)
        if v:
            rs[tid] = v
        if w:
            ra[tid] = w
    league_rpg = sum(rs.values()) / len(rs)
    print(f"[2] feature-season ({feature_season}) team rates loaded; league {league_rpg:.2f} R/G.")

    # 3) the model's own odds per game
    predictions = {}
    fip_cache = {}

    def fip_for(pid):
        if pid not in fip_cache:
            fip_cache[pid] = _regressed_fip(pid, feature_season, LEAGUE_FIP_FALLBACK)
        return fip_cache[pid]

    for g in pregame:
        if g["home_id"] not in rs or g["away_id"] not in rs:
            continue
        inp = GameInputs(
            league_rpg=league_rpg,
            home_rs=rs[g["home_id"]], home_ra=ra.get(g["home_id"], league_rpg),
            away_rs=rs[g["away_id"]], away_ra=ra.get(g["away_id"], league_rpg),
            home_starter_fip=fip_for(g["home_sp"]), away_starter_fip=fip_for(g["away_sp"]),
            venue=g["venue"] or "",
        )
        predictions[g["gamePk"]] = predict_game(inp)
    print(f"[3] model generated its own odds for {len(predictions)} games.")

    # 4) ONE Odds API call (cached by date)
    odds = _get_odds(date, refresh=refresh_odds)
    events = odds["events"]
    print(f"[4] Odds API: {len(events)} priced games "
          f"(credits remaining: {odds.get('credits_remaining')}).")

    def find_event(home_name, away_name):
        for ev in events:
            if same_team(ev["home_team"], home_name) and same_team(ev["away_team"], away_name):
                return ev
        return None

    # 5) de-vig + line-shop + guardrails
    games_ctx: List[dict] = []
    edges_ctx: List[dict] = []
    for g in pregame:
        pred = predictions.get(g["gamePk"])
        if pred is None:
            continue
        base = {
            "away": g["away_name"], "home": g["home_name"],
            "start_local": _start_local(g["commence_utc"]),
            "model_prob": pred.p_home, "model_line": pred.home_line,
        }
        ev = find_event(g["home_name"], g["away_name"])
        books = ev["books"] if ev else []
        if not books:
            games_ctx.append({**base, "market_prob": None, "edge_pct": None, "status": "no_market",
                              "best_home_book": None, "best_home_odds": None,
                              "best_away_book": None, "best_away_odds": None})
            continue

        consensus = _consensus_devig(books)
        shop = shop_lines([BookLine(b["book"], b["home_price"], b["away_price"]) for b in books])
        verdict = evaluate_game(pred.p_home, consensus)
        div = verdict.divergence

        games_ctx.append({
            **base,
            "market_prob": consensus.fair_home,
            "edge_pct": div * 100.0,
            "status": verdict.status.value,
            "best_home_book": shop.best_home_book, "best_home_odds": shop.best_home_odds,
            "best_away_book": shop.best_away_book, "best_away_odds": shop.best_away_odds,
        })

        if verdict.status == Status.SURFACED:
            if div > 0:  # edge on home
                edges_ctx.append({
                    "away": g["away_name"], "home": g["home_name"], "side": "home",
                    "start_local": base["start_local"],
                    "model_prob": pred.p_home, "model_line": pred.home_line,
                    "market_prob": consensus.fair_home, "edge_pct": abs(div) * 100.0,
                    "best_book": shop.best_home_book, "best_odds": shop.best_home_odds,
                    "note": verdict.reasons[0],
                })
            else:  # edge on away
                edges_ctx.append({
                    "away": g["away_name"], "home": g["home_name"], "side": "away",
                    "start_local": base["start_local"],
                    "model_prob": 1.0 - pred.p_home, "model_line": pred.away_line,
                    "market_prob": consensus.fair_away, "edge_pct": abs(div) * 100.0,
                    "best_book": shop.best_away_book, "best_odds": shop.best_away_odds,
                    "note": verdict.reasons[0],
                })

    # 6) Honest policy: a simple free model diverges from the sharper market on
    # most games (that is model noise, not 15 edges). Surface ONLY the few largest
    # divergences (MAX_SURFACED_PER_DAY) as a watchlist; demote the rest to no_edge.
    diverged_count = len(edges_ctx)
    edges_ctx.sort(key=lambda e: abs(e["edge_pct"]), reverse=True)
    edges_ctx = edges_ctx[:MAX_SURFACED_PER_DAY]
    kept = {(e["away"], e["home"]) for e in edges_ctx}
    for g in games_ctx:
        if g["status"] == "surfaced" and (g["away"], g["home"]) not in kept:
            g["status"] = "no_edge"

    ctx = {
        "date": date, "generated_at": _now_stamp(),
        "n_games": len(games_ctx), "n_edges": len(edges_ctx),
        "diverged_count": diverged_count,
        "edges": edges_ctx, "games": games_ctx,
    }
    _write_outputs(date, ctx)
    print(f"[5] {len(games_ctx)} games | model diverged >floor on {diverged_count} | "
          f"showing top {len(edges_ctx)} as watchlist.")
    return ctx


def _write_outputs(date: str, ctx: dict) -> None:
    public_dir = os.path.join(_PROJECT_ROOT, "public")
    data_dir = os.path.join(_PROJECT_ROOT, "data")
    os.makedirs(public_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(public_dir, "index.html"), "w") as f:
        f.write(render_html(ctx))
    with open(os.path.join(data_dir, f"{date}.json"), "w") as f:
        json.dump(ctx, f, indent=2)
