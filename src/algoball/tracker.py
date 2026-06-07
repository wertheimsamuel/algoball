"""Suggested-bet tracking and historical model-pick backtests.

Two different records are intentionally kept separate:

* live tracked suggestions: actual site suggestions from saved daily snapshots;
* historical model-pick backtest: top model picks by day using MLB results, with
  no historical sportsbook odds claim because we do not have a historical odds
  feed in v1.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

from .ingest.mlb import (
    get_season_schedule,
    get_team_runs_allowed_per_game,
    get_team_runs_per_game,
)
from .ingest.teams import same_team
from .model.calibrate import MAX_SURFACED_PER_DAY
from .model.strength import prior_winprob

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _data_dir() -> str:
    return os.environ.get("ALGOBALL_DATA_DIR") or os.path.join(_PROJECT_ROOT, "data")


def _tracked_path() -> str:
    return os.path.join(_data_dir(), "tracked_suggestions.json")


def _pct(wins: int, losses: int) -> Optional[float]:
    total = wins + losses
    if total == 0:
        return None
    return wins / total


def _record(wins: int, losses: int, pending: int = 0) -> dict:
    return {
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "graded": wins + losses,
        "win_rate": _pct(wins, losses),
    }


@lru_cache(maxsize=None)
def _season_model_picks(season: int, end_date: Optional[str] = None) -> Tuple[dict, ...]:
    """Top model picks per date, graded against final scores.

    This is a no-odds historical backtest. For each date, rank games by the
    model's distance from 50/50 and keep the same max-picks-per-day cap used by
    the live site.
    """
    feature_season = season - 1
    games = get_season_schedule(season)
    if end_date:
        games = [g for g in games if (g.get("date") or "") <= end_date]

    team_ids = {g["home_id"] for g in games} | {g["away_id"] for g in games}
    rs: Dict[int, float] = {}
    ra: Dict[int, float] = {}
    for tid in team_ids:
        v = get_team_runs_per_game(tid, feature_season)
        w = get_team_runs_allowed_per_game(tid, feature_season)
        if v:
            rs[tid] = v
        if w:
            ra[tid] = w
    if not rs:
        return tuple()
    league_rpg = sum(rs.values()) / len(rs)

    by_date: Dict[str, List[dict]] = defaultdict(list)
    for g in games:
        if g["home_id"] not in rs or g["away_id"] not in rs:
            continue
        p_home = prior_winprob(
            rs[g["home_id"]],
            ra.get(g["home_id"], league_rpg),
            rs[g["away_id"]],
            ra.get(g["away_id"], league_rpg),
        )
        pick_side = "home" if p_home >= 0.5 else "away"
        pick_team = g["home_name"] if pick_side == "home" else g["away_name"]
        won = bool(g["home_won"]) if pick_side == "home" else not bool(g["home_won"])
        pick_prob = p_home if pick_side == "home" else 1.0 - p_home
        by_date[g["date"]].append({
            "date": g["date"],
            "gamePk": g["gamePk"],
            "away": g["away_name"],
            "home": g["home_name"],
            "pick": pick_team,
            "side": pick_side,
            "pick_prob": pick_prob,
            "edge_strength": abs(p_home - 0.5),
            "won": won,
        })

    picks: List[dict] = []
    for date, day_games in sorted(by_date.items()):
        ranked = sorted(day_games, key=lambda r: r["edge_strength"], reverse=True)
        picks.extend(ranked[:MAX_SURFACED_PER_DAY])
    return tuple(picks)


def _summarize_picks(season: int, picks: List[dict], *, basis: str, end_date: Optional[str]) -> dict:
    wins = sum(1 for p in picks if p.get("won") is True)
    losses = sum(1 for p in picks if p.get("won") is False)
    return {
        "season": season,
        "basis": basis,
        "period": f"through {end_date}" if end_date else "full regular season",
        **_record(wins, losses, 0),
    }


def historical_summary(start_year: int = 2023, end_year: Optional[int] = None) -> List[dict]:
    """Yearly model-pick win rates back to start_year."""
    end_year = end_year or datetime.now().year
    rows: List[dict] = []
    for season in range(start_year, end_year + 1):
        games = get_season_schedule(season)
        if not games:
            continue
        last_final = max(g["date"] for g in games if g.get("date"))
        end_date = last_final if season == end_year else None
        picks = _season_model_picks(season, end_date=end_date)
        rows.append(_summarize_picks(
            season,
            picks,
            basis="Historical team-strength model backtest; no historical sportsbook odds feed",
            end_date=end_date,
        ))
    return rows


def historical_daily_archive(start_year: int = 2023, end_year: Optional[int] = None) -> List[dict]:
    """Daily model-pick archive for the website date picker.

    These are historical model picks, not archived sportsbook lines. Real saved
    live snapshots are still preferred when available.
    """
    end_year = end_year or datetime.now().year
    days: Dict[str, List[dict]] = defaultdict(list)
    for season in range(start_year, end_year + 1):
        games = get_season_schedule(season)
        if not games:
            continue
        last_final = max(g["date"] for g in games if g.get("date"))
        end_date = last_final if season == end_year else None
        for pick in _season_model_picks(season, end_date=end_date):
            days[pick["date"]].append({
                "date": pick["date"],
                "gamePk": pick.get("gamePk"),
                "away": pick.get("away"),
                "home": pick.get("home"),
                "side": pick.get("side"),
                "model_prob": pick.get("pick_prob"),
                "model_line": None,
                "market_prob": None,
                "edge_pct": (pick.get("edge_strength") or 0.0) * 100.0,
                "best_book": None,
                "best_odds": None,
                "source": "historical_model",
            })

    out = []
    for date, edges in days.items():
        out.append({
            "date": date,
            "generated_at": "historical model backtest",
            "n_edges": len(edges),
            "edges": edges,
            "source": "historical_model",
        })
    return sorted(out, key=lambda row: row["date"], reverse=True)


def _data_snapshots() -> Iterable[Tuple[str, dict]]:
    data_dir = _data_dir()
    if not os.path.isdir(data_dir):
        return []
    out = []
    for name in sorted(os.listdir(data_dir)):
        if not (name.endswith(".json") and len(name) == 15):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path) as f:
                out.append((name[:10], json.load(f)))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _read_tracked() -> List[dict]:
    path = _tracked_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_tracked(rows: List[dict]) -> None:
    path = _tracked_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)


def _pick_key(row: dict) -> str:
    if row.get("gamePk") is not None:
        return "{}:{}:{}".format(row.get("date"), row.get("gamePk"), row.get("side"))
    return "{}:{}:{}:{}".format(
        row.get("date"),
        row.get("away"),
        row.get("home"),
        row.get("side"),
    )


def record_live_suggestions(date: str, edges: List[dict]) -> None:
    """Append current daily suggestions to an on-disk tracking log.

    This prevents a later Railway restart from erasing the original suggestion
    record if the same date's display snapshot is regenerated after some games
    have already started.
    """
    if not edges:
        return
    rows = _read_tracked()
    seen = {_pick_key(r) for r in rows}
    changed = False
    for edge in edges:
        row = {
            "date": edge.get("date") or date,
            "gamePk": edge.get("gamePk"),
            "away": edge.get("away"),
            "home": edge.get("home"),
            "pick": edge.get(edge.get("side")) if edge.get("side") in ("home", "away") else None,
            "side": edge.get("side"),
            "best_odds": edge.get("best_odds"),
            "edge_pct": edge.get("edge_pct"),
        }
        key = _pick_key(row)
        if key in seen:
            continue
        rows.append(row)
        seen.add(key)
        changed = True
    if changed:
        _write_tracked(rows)


def _find_final_game(date: str, edge: dict, schedule_by_year: Dict[int, List[dict]]) -> Optional[dict]:
    season = int(date[:4])
    games = schedule_by_year.setdefault(season, get_season_schedule(season))
    game_pk = edge.get("gamePk")
    if game_pk is not None:
        for g in games:
            if g.get("gamePk") == game_pk:
                return g
    for g in games:
        if g.get("date") != date:
            continue
        if same_team(g["home_name"], edge.get("home", "")) and same_team(g["away_name"], edge.get("away", "")):
            return g
    return None


def live_suggestions_summary(current_year: Optional[int] = None) -> dict:
    """Grade actual saved site suggestions from data/YYYY-MM-DD.json files."""
    current_year = current_year or datetime.now().year
    schedule_by_year: Dict[int, List[dict]] = {}
    picks_by_key: Dict[str, dict] = {}

    for row in _read_tracked():
        if not row.get("date") or int(str(row["date"])[:4]) != current_year:
            continue
        picks_by_key[_pick_key(row)] = dict(row)

    for date, snapshot in _data_snapshots():
        if int(date[:4]) != current_year:
            continue
        for edge in snapshot.get("edges", []) or []:
            pick_side = edge.get("side")
            pick_team = edge.get(pick_side) if pick_side in ("home", "away") else None
            row = {
                "date": date,
                "gamePk": edge.get("gamePk"),
                "away": edge.get("away"),
                "home": edge.get("home"),
                "pick": pick_team,
                "side": pick_side,
                "best_odds": edge.get("best_odds"),
                "edge_pct": edge.get("edge_pct"),
            }
            picks_by_key.setdefault(_pick_key(row), row)

    picks: List[dict] = []
    for row in sorted(picks_by_key.values(), key=lambda r: (r.get("date") or "", str(r.get("gamePk") or ""))):
        final = _find_final_game(row.get("date", ""), row, schedule_by_year)
        won = None
        if final and row.get("side") in ("home", "away"):
            won = bool(final["home_won"]) if row["side"] == "home" else not bool(final["home_won"])
        picks.append({**row, "won": won})

    wins = sum(1 for p in picks if p["won"] is True)
    losses = sum(1 for p in picks if p["won"] is False)
    pending = sum(1 for p in picks if p["won"] is None)
    return {
        "season": current_year,
        "basis": "Actual AlgoBall suggestions collected from daily site snapshots",
        **_record(wins, losses, pending),
        "recent": picks[-12:],
    }


def build_tracker(current_year: Optional[int] = None) -> dict:
    current_year = current_year or datetime.now().year
    history = historical_summary(2023, current_year)
    current = next((row for row in reversed(history) if row.get("season") == current_year), None)
    return {
        "current": current,
        "live": live_suggestions_summary(current_year),
        "history": history,
    }
