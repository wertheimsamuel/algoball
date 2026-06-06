"""The Odds API v4 client for MLB moneylines (h2h). Standard library only.

Fetches American-odds head-to-head prices for every upcoming MLB game and folds
each bookmaker's two outcomes back onto the event's home/away teams. The Odds API
reports remaining/used credits in response headers; we surface those so the
controller can keep the user inside the free quota.

This module never calls the API at import time and makes exactly one request per
:func:`get_mlb_moneylines` call.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from . import teams

_BASE = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
_USER_AGENT = "algoball/0.1 (+pre-game MLB model)"
_TIMEOUT = 30
_RETRIES = 3


def _to_int(value: Optional[str]) -> Optional[int]:
    """Parse a header credit count to int, or None if missing/unparseable."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _fetch(url: str) -> Dict[str, object]:
    """GET ``url`` with retries; return body bytes plus credit headers.

    Retries transient failures (network errors, HTTP 429/5xx). Raises a clear
    ``RuntimeError`` that includes the API's error body on non-transient HTTP
    errors (e.g. 401 bad key, 422 bad params) and after retries are exhausted.
    """
    last_err: Optional[str] = None
    for attempt in range(_RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                body = resp.read()
                return {
                    "body": body,
                    "credits_remaining": _to_int(resp.headers.get("x-requests-remaining")),
                    "credits_used": _to_int(resp.headers.get("x-requests-used")),
                }
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", "replace").strip()
            except Exception:  # noqa: BLE001 - error body is best-effort
                err_body = ""
            detail = err_body or getattr(e, "reason", "") or ""
            # Retry only transient server-side / rate-limit responses.
            if e.code == 429 or e.code >= 500:
                last_err = f"HTTP {e.code}: {detail}"
                time.sleep(0.5 * (attempt + 1))
                continue
            raise RuntimeError(f"The Odds API request failed (HTTP {e.code}): {detail}")
        except urllib.error.URLError as e:
            last_err = f"network error: {getattr(e, 'reason', e)}"
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(
        f"The Odds API request failed after {_RETRIES} attempts: {last_err}"
    )


def _match_price(prices: Dict[str, int], team_name: str) -> Optional[int]:
    """Find the American price for ``team_name`` among a book's outcomes.

    Tries an exact outcome-name match first, then falls back to nickname-based
    matching so a stray spelling difference does not drop a book.
    """
    if team_name in prices:
        return prices[team_name]
    for name, price in prices.items():
        if teams.same_team(name, team_name):
            return price
    return None


def get_mlb_moneylines(api_key: str, regions: str = "us") -> dict:
    """Fetch MLB moneylines from The Odds API v4.

    Returns::

        {
          "credits_remaining": int | None,
          "credits_used": int | None,
          "events": [
            {
              "commence_time": str,        # ISO-8601 UTC, e.g. "2026-06-06T23:05:00Z"
              "home_team": str,
              "away_team": str,
              "books": [
                {"book": str, "home_price": int, "away_price": int},
                ...
              ],
            },
            ...
          ],
        }

    A bookmaker is skipped when it lacks a complete h2h market (both the home
    and away price present). ``regions`` follows The Odds API convention
    (e.g. "us", "us2", "uk", or a comma-separated list).
    """
    url = (
        f"{_BASE}?apiKey={api_key}&regions={regions}"
        "&markets=h2h&oddsFormat=american"
    )
    fetched = _fetch(url)

    try:
        raw_events = json.loads(fetched["body"].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise RuntimeError(f"The Odds API returned invalid JSON: {e}")
    if not isinstance(raw_events, list):
        raise RuntimeError(
            f"The Odds API returned unexpected payload (expected list): {raw_events!r}"
        )

    events: List[dict] = []
    for ev in raw_events:
        home = ev.get("home_team")
        away = ev.get("away_team")
        if not home or not away:
            continue

        books: List[dict] = []
        for bk in ev.get("bookmakers", []) or []:
            # Locate this bookmaker's h2h market.
            h2h = None
            for market in bk.get("markets", []) or []:
                if market.get("key") == "h2h":
                    h2h = market
                    break
            if not h2h:
                continue

            prices: Dict[str, int] = {}
            for outcome in h2h.get("outcomes", []) or []:
                name = outcome.get("name")
                price = outcome.get("price")
                if name is None or price is None:
                    continue
                prices[name] = price

            home_price = _match_price(prices, home)
            away_price = _match_price(prices, away)
            if home_price is None or away_price is None:
                continue  # skip books without a complete h2h market

            books.append({
                "book": bk.get("title") or bk.get("key"),
                "home_price": int(home_price),
                "away_price": int(away_price),
            })

        events.append({
            "commence_time": ev.get("commence_time"),
            "home_team": home,
            "away_team": away,
            "books": books,
        })

    return {
        "credits_remaining": fetched["credits_remaining"],
        "credits_used": fetched["credits_used"],
        "events": events,
    }
