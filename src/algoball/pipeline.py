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
from .model.calibrate import Status, evaluate_game
from .model.devig import (
    DevigResult,
    american_to_implied,
    devig_additive,
    devig_multiplicative,
)
from .model.game import GameInputs, predict_game
from .model.lineshop import BookLine, shop_lines
from .render.renderer import render_html
from .tracker import build_tracker, historical_daily_archive, record_live_suggestions

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_NY = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


# --- small helpers ----------------------------------------------------------
def _data_dir() -> str:
    return os.environ.get("ALGOBALL_DATA_DIR") or os.path.join(_PROJECT_ROOT, "data")


def snapshot_path(date: str) -> str:
    return os.path.join(_data_dir(), f"{date}.json")


def load_snapshot(date: str) -> Optional[dict]:
    path = snapshot_path(date)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_public_html(ctx: dict) -> None:
    public_dir = os.path.join(_PROJECT_ROOT, "public")
    os.makedirs(public_dir, exist_ok=True)
    with open(os.path.join(public_dir, "index.html"), "w") as f:
        f.write(render_html(ctx))


def hydrate_snapshot(date: str, ctx: dict) -> dict:
    """Add current derived website sections to an older saved snapshot."""
    hydrated = dict(ctx)
    hydrated = _fill_missing_schedule_games(date, hydrated)
    hydrated["tracker"] = build_tracker(int(date[:4]))
    hydrated["archive"] = _build_archive(date, hydrated)
    return hydrated


def _fill_missing_schedule_games(date: str, ctx: dict) -> dict:
    """Keep the displayed full slate complete even if an older snapshot was partial."""
    games = list(ctx.get("games") or [])
    seen = {g.get("gamePk") for g in games if g.get("gamePk") is not None}
    try:
        scheduled = get_todays_games(date)
    except Exception:  # noqa: BLE001 - snapshot hydration should not fail render
        scheduled = []
    for g in scheduled:
        if g.get("gamePk") in seen:
            continue
        games.append({
            "date": date,
            "gamePk": g.get("gamePk"),
            "away": g.get("away_name"),
            "home": g.get("home_name"),
            "start_local": _start_local(g.get("commence_utc")),
            "model_prob": None,
            "model_line": None,
            "market_prob": None,
            "edge_pct": None,
            "status": "no_market",
            "best_home_book": None,
            "best_home_odds": None,
            "best_away_book": None,
            "best_away_odds": None,
        })
        seen.add(g.get("gamePk"))
    hydrated = dict(ctx)
    hydrated["games"] = games
    hydrated["n_games"] = len(games)
    return hydrated


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
    path = os.path.join(_data_dir(), "cache", f"odds_{date}.json")
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

    existing = load_snapshot(date)
    if existing and len(pregame) < len(todays):
        print(f"[1b] restoring saved full-day snapshot for {date}; games already started.")
        existing = hydrate_snapshot(date, existing)
        write_public_html(existing)
        return existing

    if not pregame:
        games_ctx = []
        for g in todays:
            games_ctx.append({
                "date": date,
                "gamePk": g.get("gamePk"),
                "away": g.get("away_name"),
                "home": g.get("home_name"),
                "start_local": _start_local(g.get("commence_utc")),
                "model_prob": None,
                "model_line": None,
                "market_prob": None,
                "edge_pct": None,
                "status": "no_market",
                "best_home_book": None,
                "best_home_odds": None,
                "best_away_book": None,
                "best_away_odds": None,
            })
        ctx = {
            "date": date,
            "generated_at": _now_stamp(),
            "n_games": len(games_ctx),
            "n_edges": 0,
            "edges": [],
            "games": games_ctx,
            "tracker": build_tracker(int(date[:4])),
        }
        ctx["archive"] = _build_archive(date, ctx)
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
            "date": date, "gamePk": g["gamePk"],
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
                    "date": date, "gamePk": g["gamePk"],
                    "away": g["away_name"], "home": g["home_name"], "side": "home",
                    "start_local": base["start_local"],
                    "model_prob": pred.p_home, "model_line": pred.home_line,
                    "market_prob": consensus.fair_home, "edge_pct": abs(div) * 100.0,
                    "best_book": shop.best_home_book, "best_odds": shop.best_home_odds,
                    "note": verdict.reasons[0],
                })
            else:  # edge on away
                edges_ctx.append({
                    "date": date, "gamePk": g["gamePk"],
                    "away": g["away_name"], "home": g["home_name"], "side": "away",
                    "start_local": base["start_local"],
                    "model_prob": 1.0 - pred.p_home, "model_line": pred.away_line,
                    "market_prob": consensus.fair_away, "edge_pct": abs(div) * 100.0,
                    "best_book": shop.best_away_book, "best_odds": shop.best_away_odds,
                    "note": verdict.reasons[0],
                })

    # 6) Surface every game that passes the model's guardrails. The guards still
    # suppress absurd outputs; we no longer apply an arbitrary top-3 display cap.
    diverged_count = len(edges_ctx)
    edges_ctx.sort(key=lambda e: abs(e["edge_pct"]), reverse=True)

    record_live_suggestions(date, edges_ctx)
    ctx = {
        "date": date, "generated_at": _now_stamp(),
        "n_games": len(games_ctx), "n_edges": len(edges_ctx),
        "diverged_count": diverged_count,
        "edges": edges_ctx, "games": games_ctx,
        "tracker": build_tracker(int(date[:4])),
    }
    ctx["archive"] = _build_archive(date, ctx)
    _write_outputs(date, ctx)
    print(f"[5] {len(games_ctx)} games | model diverged >floor on {diverged_count} | "
          f"showing {len(edges_ctx)} supported suggested bets.")
    return ctx


def _archive_day(snapshot: dict) -> dict:
    return {
        "date": snapshot.get("date"),
        "generated_at": snapshot.get("generated_at"),
        "n_edges": int(snapshot.get("n_edges") or 0),
        "edges": snapshot.get("edges") or [],
        "games": snapshot.get("games") or [],
        "source": snapshot.get("source") or "live_snapshot",
    }


def _build_archive(current_date: str, current_ctx: dict) -> List[dict]:
    """Collect saved daily snapshots for the website's date picker."""
    data_dir = _data_dir()
    by_date = {
        day["date"]: day
        for day in historical_daily_archive(2023, int(current_date[:4]))
        if day.get("date")
    }
    if os.path.isdir(data_dir):
        for name in os.listdir(data_dir):
            if not (len(name) == 15 and name.endswith(".json")):
                continue
            day = name[:-5]
            if len(day) != 10 or day[4] != "-" or day[7] != "-":
                continue
            try:
                with open(os.path.join(data_dir, name)) as f:
                    snapshot = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if snapshot.get("date"):
                by_date[snapshot["date"]] = _archive_day(snapshot)
    by_date[current_date] = _archive_day(current_ctx)
    return [by_date[day] for day in sorted(by_date.keys(), reverse=True)]


def _write_outputs(date: str, ctx: dict) -> None:
    data_dir = _data_dir()
    os.makedirs(data_dir, exist_ok=True)
    write_public_html(ctx)
    with open(snapshot_path(date), "w") as f:
        json.dump(ctx, f, indent=2)
