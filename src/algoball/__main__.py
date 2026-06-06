"""AlgoBall daily pre-game run."""
from __future__ import annotations

import argparse

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="algoball",
        description="Generate the daily pre-game MLB moneyline dashboard.",
    )
    parser.add_argument("date_pos", nargs="?", help="Optional date as YYYY-MM-DD.")
    parser.add_argument("--date", dest="date_opt", help="Optional date as YYYY-MM-DD.")
    parser.add_argument(
        "--refresh-odds",
        action="store_true",
        help="Ignore the cached odds snapshot and make a fresh Odds API call.",
    )
    parser.add_argument(
        "--feature-season",
        type=int,
        help="Override the stats season used for features. Defaults to the run date's season.",
    )
    args = parser.parse_args()

    date = args.date_opt or args.date_pos
    ctx = run(date=date, feature_season=args.feature_season, refresh_odds=args.refresh_odds)
    print("-" * 60)
    print(f"AlgoBall: {ctx['n_games']} pre-game games, {ctx['n_edges']} edge(s).")
    print("Output: public/index.html")


if __name__ == "__main__":
    main()
