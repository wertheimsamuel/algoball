"""Unit tests for the modeling core (run: `pytest`, or see scripts/demo_core.py).

These tests encode the verified design decisions as executable guarantees. The
most important is the golden regression test: the old +34% / 81% bug MUST be
suppressed. If a future change ever lets it through, this test fails.
"""
from __future__ import annotations

import json
import math

import pytest

from algoball import pipeline
from algoball import tracker
from algoball.model.calibrate import (
    EDGE_FLOOR,
    MAX_RAW_DIVERGENCE,
    PROB_OOD_BAND,
    Status,
    evaluate_game,
)
from algoball.model.devig import (
    american_to_decimal,
    american_to_implied,
    devig_moneyline,
)
from algoball.model.lineshop import BookLine, shop_lines
from algoball.model.winprob import (
    run_diff_for_probability,
    win_probability,
    win_probability_from_runs,
)
from algoball.render.renderer import render_html


# --- odds / de-vig -----------------------------------------------------------
def test_american_to_implied_basic():
    assert american_to_implied(+100) == pytest.approx(0.5)
    assert american_to_implied(-110) == pytest.approx(110 / 210)
    assert american_to_implied(+200) == pytest.approx(1 / 3)


def test_american_to_decimal_basic():
    assert american_to_decimal(+100) == pytest.approx(2.0)
    assert american_to_decimal(-200) == pytest.approx(1.5)


def test_devig_sums_to_one_and_has_positive_vig():
    dv = devig_moneyline(-110, -110)
    assert dv.fair_home + dv.fair_away == pytest.approx(1.0)
    assert dv.overround > 0  # the book always has vig
    assert dv.fair_home == pytest.approx(0.5)


# --- win probability ---------------------------------------------------------
def test_even_matchup_is_half():
    assert win_probability(0.0) == pytest.approx(0.5)


def test_win_probability_is_monotonic():
    assert win_probability(-2) < win_probability(0) < win_probability(2)


def test_hfa_helps_the_home_team():
    no_hfa = win_probability_from_runs(4.5, 4.5, include_hfa=False)
    with_hfa = win_probability_from_runs(4.5, 4.5, include_hfa=True)
    assert no_hfa == pytest.approx(0.5)
    assert with_hfa > 0.5


def test_81pct_requires_an_absurd_run_edge():
    # The whole reason 0.81 is treated as a bug: it needs a multi-run pregame edge.
    rd = run_diff_for_probability(0.812)
    assert rd > 3.0
    # round-trip sanity
    assert win_probability(rd) == pytest.approx(0.812, abs=1e-6)


# --- calibration guardrails (the heart) --------------------------------------
def test_golden_the_old_bug_is_suppressed():
    """Model 81.2% vs a ~47% market must be killed and alarmed."""
    dv = devig_moneyline(-110, -110)  # fair home 0.5; pair with a wild model
    v = evaluate_game(0.812, dv)
    assert v.status == Status.SUPPRESSED_BUG
    assert v.alarm is True


def test_raw_ood_high_is_suppressed():
    dv = devig_moneyline(-110, -110)
    assert evaluate_game(PROB_OOD_BAND[1] + 0.01, dv).status == Status.SUPPRESSED_BUG


def test_large_divergence_is_suppressed_even_inside_ood_band():
    # p_model 0.62 is inside the OOD band, but vs a 0.47 market the 15pp
    # divergence must still be suppressed as a likely bug.
    dv = devig_moneyline(+120, -140)  # home underdog, fair home < 0.5
    v = evaluate_game(0.62, dv)
    assert abs(v.divergence) > MAX_RAW_DIVERGENCE
    assert v.status == Status.SUPPRESSED_BUG


def test_sane_divergence_is_surfaced():
    dv = devig_moneyline(-120, +100)  # fair home ~0.53
    v = evaluate_game(dv.fair_home + 0.03, dv)
    assert v.status == Status.SURFACED
    assert EDGE_FLOOR <= abs(v.divergence) <= MAX_RAW_DIVERGENCE
    assert v.alarm is False


def test_tiny_divergence_is_no_edge():
    dv = devig_moneyline(-130, +110)
    v = evaluate_game(dv.fair_home + 0.005, dv)
    assert v.status == Status.NO_EDGE


def test_final_prob_is_market_anchored_in_v1():
    # SHRINK_W == 0, so the decision prob equals the fair market prob.
    dv = devig_moneyline(-120, +100)
    v = evaluate_game(dv.fair_home + 0.03, dv)
    assert v.p_final == pytest.approx(dv.fair_home)


# --- line shopping -----------------------------------------------------------
def test_line_shopping_picks_best_price_and_flags_soft_book():
    lines = [
        BookLine("SharpBook", -150, +135),
        BookLine("BigBook", -145, +125),
        BookLine("SoftBook", -120, +105),  # generous on home -> soft
    ]
    res = shop_lines(lines)
    assert res is not None
    # best home price is the least-juiced (-120 at SoftBook)
    assert res.best_home_book == "SoftBook"
    assert res.best_home_odds == -120
    # the soft book should be flagged on the home side
    assert any(f.book == "SoftBook" and f.side == "home" for f in res.soft_flags)


def test_shop_lines_handles_empty():
    assert shop_lines([]) is None


def test_renderer_uses_date_picker_for_full_slate_without_bottom_duplicate():
    html = render_html({
        "date": "2026-06-07",
        "generated_at": "Jun 7, 2026, 10:30 AM ET",
        "n_games": 1,
        "n_edges": 0,
        "edges": [],
        "games": [{
            "away": "New York Yankees",
            "home": "Boston Red Sox",
            "start_local": "7:10 PM ET",
            "status": "no_edge",
        }],
        "archive": [{
            "date": "2026-06-07",
            "generated_at": "Jun 7, 2026, 10:30 AM ET",
            "n_edges": 0,
            "edges": [],
            "games": [{
                "away": "New York Yankees",
                "home": "Boston Red Sox",
                "start_local": "7:10 PM ET",
                "status": "no_edge",
            }],
        }],
        "tracker": {},
    })
    assert '<h2 class="section-title">Full Slate</h2>' not in html
    assert "Choose any date to see that day's suggested bets and full slate" in html
    assert "Frozen until tomorrow's morning refresh" in html


def test_historical_model_picks_are_not_capped_at_three(monkeypatch):
    games = []
    for idx in range(5):
        games.append({
            "date": "2026-04-01",
            "gamePk": 1000 + idx,
            "home_id": idx + 1,
            "away_id": idx + 101,
            "home_name": f"Home {idx}",
            "away_name": f"Away {idx}",
            "home_won": True,
        })

    probs_by_home_rs = {
        1.0: 0.60,
        2.0: 0.58,
        3.0: 0.56,
        4.0: 0.54,
        5.0: 0.52,
    }

    monkeypatch.setattr(tracker, "get_season_schedule", lambda season: games)
    monkeypatch.setattr(tracker, "get_team_runs_per_game", lambda tid, season: float(tid) if tid < 100 else 4.0)
    monkeypatch.setattr(tracker, "get_team_runs_allowed_per_game", lambda tid, season: 4.0)
    monkeypatch.setattr(
        tracker,
        "prior_winprob",
        lambda home_rs, home_ra, away_rs, away_ra: probs_by_home_rs[home_rs],
    )

    tracker._season_model_picks.cache_clear()
    try:
        picks = tracker._season_model_picks(2026)
    finally:
        tracker._season_model_picks.cache_clear()

    assert len(picks) == 5
    assert all(p["edge_strength"] >= EDGE_FLOOR for p in picks)


def test_archive_payload_preserves_more_than_three_edges():
    edges = []
    games = []
    for idx in range(5):
        edges.append({
            "date": "2026-04-01",
            "gamePk": 2000 + idx,
            "away": f"Away {idx}",
            "home": f"Home {idx}",
            "side": "home",
            "model_prob": 0.55 + idx * 0.01,
            "edge_pct": 5.0 + idx,
        })
        games.append({
            "date": "2026-04-01",
            "gamePk": 2000 + idx,
            "away": f"Away {idx}",
            "home": f"Home {idx}",
            "status": "surfaced",
        })

    html = render_html({
        "date": "2026-04-01",
        "generated_at": "Apr 1, 2026, 10:30 AM ET",
        "n_games": 5,
        "n_edges": 5,
        "edges": edges,
        "games": games,
        "archive": [{
            "date": "2026-04-01",
            "generated_at": "Apr 1, 2026, 10:30 AM ET",
            "n_edges": 5,
            "edges": edges,
            "games": games,
        }],
        "tracker": {},
    })
    payload_text = html.split('id="archive-data">', 1)[1].split("</script>", 1)[0]
    payload = json.loads(payload_text)

    assert "2026-04-01 - 5 picks" in html
    assert payload[0]["nEdges"] == 5
    assert len(payload[0]["edges"]) == 5
    assert len({edge["home"] for edge in payload[0]["edges"]}) == 5


def test_archive_day_preserves_all_snapshot_edges():
    snapshot = {
        "date": "2026-04-01",
        "generated_at": "Apr 1, 2026, 10:30 AM ET",
        "n_edges": 5,
        "edges": [{"gamePk": 3000 + idx} for idx in range(5)],
        "games": [{"gamePk": 3000 + idx} for idx in range(5)],
    }

    archived = pipeline._archive_day(snapshot)

    assert archived["n_edges"] == 5
    assert len(archived["edges"]) == 5
    assert len(archived["games"]) == 5
