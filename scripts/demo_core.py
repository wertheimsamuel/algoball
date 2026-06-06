"""Zero-install demonstration of AlgoBall's modeling core.

Run from the project root with:

    PYTHONPATH=src python3 scripts/demo_core.py

It uses only the standard library, so it works before any dependencies or APIs
are set up. It shows the three things that matter:
  1) the old +34% / 81% bug is now structurally caught (suppressed + alarmed),
  2) a small, sane divergence is surfaced honestly,
  3) line shopping finds the best price and flags a soft book.
"""
from __future__ import annotations

from algoball.model.calibrate import Status, evaluate_game
from algoball.model.devig import devig_moneyline
from algoball.model.lineshop import BookLine, shop_lines
from algoball.model.winprob import run_diff_for_probability, win_probability_from_runs

LINE = "-" * 70


def show_verdict(title: str, p_model: float, home_odds: int, away_odds: int) -> None:
    dv = devig_moneyline(home_odds, away_odds)
    v = evaluate_game(p_model, dv)
    print(f"\n{title}")
    print(f"  market: home {home_odds:+d} / away {away_odds:+d}   (vig {dv.vig_pct:.1f}%)")
    print(f"  fair market (de-vigged): home {dv.fair_home:.3f}")
    print(f"  model win prob:          home {p_model:.3f}")
    print(f"  divergence (model - market): {v.edge_pct:+.1f}pp")
    flag = "  [ALARM]" if v.alarm else ("  [soft favorite]" if v.soft_flag else "")
    print(f"  -> {v.status.value.upper()}{flag}")
    print(f"     {v.reasons[0]}")


def main() -> None:
    print(LINE)
    print("AlgoBall modeling core — live demonstration")
    print(LINE)

    # The win-prob map, sanity-checked: what run edge does 81% even require?
    rd = run_diff_for_probability(0.812)
    print(f"\nSanity check: an 81.2% home win prob implies a ~{rd:.1f}-run pregame edge.")
    print("A real MLB pregame edge is a fraction of a run, so 0.812 is a broken number.")

    print("\n" + LINE)
    print("CALIBRATION GUARDRAILS")
    print(LINE)

    # 1) The historical bug: model 81.2% vs a market that says 46.8%.
    #    Astros -550 / underdog +380 de-vigs to roughly 46-48% on this side in
    #    the original report; here we use a market around that level.
    show_verdict(
        "1) The old bug (Astros: model 81.2% vs market ~47%) — must be killed",
        p_model=0.812, home_odds=-110, away_odds=-110,
    )

    # 2) A realistic, surfaced divergence: model 55% vs fair ~52%.
    show_verdict(
        "2) A sane ~3pp divergence — surfaced honestly",
        p_model=0.55, home_odds=-120, away_odds=+100,
    )

    # 3) The common, correct result: basically agrees with the market.
    show_verdict(
        "3) The normal case — no qualifying edge (this is most games)",
        p_model=0.535, home_odds=-130, away_odds=+110,
    )

    # 4) A legitimate heavy favorite, surfaced (not suppressed) with a soft flag.
    show_verdict(
        "4) A legitimate heavy favorite — surfaced with a soft flag",
        p_model=0.74, home_odds=-230, away_odds=+190,
    )

    # An example built from baseball inputs rather than a hand-set probability.
    print("\n" + LINE)
    print("FROM BASEBALL INPUTS")
    print(LINE)
    p = win_probability_from_runs(exp_runs_home=4.6, exp_runs_away=4.3)
    print(f"\nHome expects 4.6 runs, away 4.3 (plus home-field): model home win prob = {p:.3f}")
    print("Note how a 0.3-run edge maps to only a few points of win probability — by design.")

    print("\n" + LINE)
    print("LINE SHOPPING / SOFT-LINE DETECTION  (the honest 'beat the book' edge)")
    print(LINE)
    lines = [
        BookLine("SharpBook", home_odds=-150, away_odds=+135),
        BookLine("BigBook",   home_odds=-145, away_odds=+125),
        BookLine("SoftBook",  home_odds=-120, away_odds=+105),  # stale, generous on home
    ]
    res = shop_lines(lines)
    print(f"\nConsensus fair: home {res.consensus_fair_home:.3f} / away {res.consensus_fair_away:.3f}")
    print(f"Best home price: {res.best_home_odds:+d} at {res.best_home_book}")
    print(f"Best away price: {res.best_away_odds:+d} at {res.best_away_book}")
    if res.soft_flags:
        for f in res.soft_flags:
            print(f"  SOFT LINE: {f.book} {f.side} {f.offered_odds:+d} "
                  f"(implied {f.offered_implied:.3f} vs consensus {f.consensus_fair:.3f}, "
                  f"{f.softness * 100:.1f}pp soft)")
    else:
        print("  no soft lines this game")

    print("\n" + LINE)
    print("Summary: the bug is caught at the source, sane edges surface, the common")
    print("case is 'no edge', and a real (soft-line) edge is detectable. Core works.")
    print(LINE)


if __name__ == "__main__":
    main()
