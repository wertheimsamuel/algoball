"""MLB Stats API client (statsapi.mlb.com) — free, no key, standard library only.

Everything is cached to data/cache/*.json so a backtest can be re-run instantly
and we stay polite to the API. Stats are fetched by *season*, which lets the
backtester use PRIOR-season stats as point-in-time, lookahead-free features.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Dict, List, Optional

from ..config import FIP_CONSTANT

_BASE = "https://statsapi.mlb.com/api/v1"
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")


def _cache_path(key: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, key + ".json")


def _get_json(url: str, retries: int = 3) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "algoball-backtest/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - network is best-effort
            last = e
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")


def _cached(key: str, url: str) -> dict:
    path = _cache_path(key)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    data = _get_json(url)
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def _ip_to_float(ip: Optional[str]) -> float:
    """Convert baseball innings notation ('176.1' = 176 1/3) to a float."""
    if not ip:
        return 0.0
    whole, _, frac = str(ip).partition(".")
    return int(whole or 0) + (int(frac or 0) / 3.0)


# --- schedule ---------------------------------------------------------------
def get_season_schedule(season: int) -> List[dict]:
    """All FINAL regular-season games for a season, as flat dicts."""
    url = (
        f"{_BASE}/schedule?sportId=1&startDate={season}-03-01&endDate={season}-11-30"
        f"&gameType=R&hydrate=probablePitcher"
    )
    raw = _cached(f"sched_{season}", url)
    games: List[dict] = []
    for d in raw.get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("detailedState") != "Final":
                continue
            home = g["teams"]["home"]
            away = g["teams"]["away"]
            if home.get("score") is None or away.get("score") is None:
                continue
            games.append({
                "date": d.get("date"),
                "gamePk": g.get("gamePk"),
                "venue": g.get("venue", {}).get("name"),
                "home_id": home["team"]["id"],
                "home_name": home["team"]["name"],
                "home_score": home["score"],
                "home_won": bool(home.get("isWinner")),
                "away_id": away["team"]["id"],
                "away_name": away["team"]["name"],
                "away_score": away["score"],
                "home_sp": (home.get("probablePitcher") or {}).get("id"),
                "away_sp": (away.get("probablePitcher") or {}).get("id"),
            })
    return games


def get_todays_games(date: str) -> List[dict]:
    """Today's games (NOT cached — live state), for the daily pre-game run.

    Each game carries a `started` flag (True once it leaves the 'Preview' state),
    so the pipeline can guarantee it never publishes a live/finished game.
    """
    url = (
        f"{_BASE}/schedule?sportId=1&date={date}&gameType=R"
        f"&hydrate=probablePitcher,team"
    )
    raw = _get_json(url)  # fresh every run
    games: List[dict] = []
    for d in raw.get("dates", []):
        for g in d.get("games", []):
            status = g.get("status", {})
            abstract = status.get("abstractGameState")  # Preview / Live / Final
            home = g["teams"]["home"]
            away = g["teams"]["away"]
            games.append({
                "gamePk": g.get("gamePk"),
                "commence_utc": g.get("gameDate"),
                "abstract_state": abstract,
                "detailed_state": status.get("detailedState"),
                "started": abstract != "Preview",
                "venue": g.get("venue", {}).get("name"),
                "home_id": home["team"]["id"],
                "home_name": home["team"]["name"],
                "away_id": away["team"]["id"],
                "away_name": away["team"]["name"],
                "home_sp": (home.get("probablePitcher") or {}).get("id"),
                "away_sp": (away.get("probablePitcher") or {}).get("id"),
            })
    return games


# --- pitcher FIP (computed ourselves from one call) -------------------------
def get_pitcher_fip(pitcher_id: int, season: int) -> Optional[Dict[str, float]]:
    """Prior-season FIP and innings for a pitcher, or None if no data.

    FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + cFIP, computed from the season line.
    """
    if not pitcher_id:
        return None
    url = f"{_BASE}/people/{pitcher_id}/stats?stats=season&group=pitching&season={season}"
    raw = _cached(f"pit_{pitcher_id}_{season}", url)
    splits = raw.get("stats", [{}])[0].get("splits", []) if raw.get("stats") else []
    if not splits:
        return None
    st = splits[0]["stat"]
    ip = _ip_to_float(st.get("inningsPitched"))
    if ip < 1.0:
        return None
    hr = float(st.get("homeRuns", 0))
    bb = float(st.get("baseOnBalls", 0))
    hbp = float(st.get("hitByPitch", 0))
    so = float(st.get("strikeOuts", 0))
    fip = (13 * hr + 3 * (bb + hbp) - 2 * so) / ip + FIP_CONSTANT
    return {"fip": fip, "ip": ip}


# --- team offense -----------------------------------------------------------
def get_team_runs_per_game(team_id: int, season: int) -> Optional[float]:
    url = f"{_BASE}/teams/{team_id}/stats?stats=season&group=hitting&season={season}"
    raw = _cached(f"team_{team_id}_{season}", url)
    splits = raw.get("stats", [{}])[0].get("splits", []) if raw.get("stats") else []
    if not splits:
        return None
    st = splits[0]["stat"]
    runs = float(st.get("runs", 0))
    gp = float(st.get("gamesPlayed", 0))
    if gp < 1:
        return None
    return runs / gp


def get_team_runs_allowed_per_game(team_id: int, season: int) -> Optional[float]:
    """Prior-season runs ALLOWED per game (team pitching) — for run prevention / Pythagorean."""
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
