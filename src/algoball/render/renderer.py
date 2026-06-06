"""Dark-themed static dashboard renderer for AlgoBall.

Pure Python standard library only: the HTML is assembled with f-strings and
plain string concatenation (no Jinja2 / no third-party templating). The single
public function :func:`render_html` accepts a prepared context dict and returns
a self-contained HTML document (inline ``<style>``, no external assets) suitable
for writing to a file and serving statically.

The renderer is deliberately defensive: every field is accessed with ``.get``
and missing / ``None`` values degrade to a neutral em-dash so a malformed game
can never crash the nightly build.
"""
from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

# --- status presentation -------------------------------------------------

# label + css class for each game status; unknown statuses fall back to "no_edge".
_STATUS_META = {
    "surfaced": ("Edge", "st-edge"),
    "no_edge": ("No edge", "st-none"),
    "suppressed_bug": ("Suppressed (data)", "st-bug"),
    "suppressed_fragile": ("Suppressed (fragile)", "st-fragile"),
    "no_market": ("No market", "st-nomkt"),
}

_ABOUT = (
    "AlgoBall builds its own pre-game MLB moneyline odds, compares them with "
    "Vegas books after removing vig, and highlights only the clearest "
    "model-vs-market edges."
)

_RISK_NOTICE = (
    "Not financial advice. Not betting advice. Gambling involves risk, and you "
    "can lose money. Odds and model outputs are estimates for research and "
    "entertainment only; never bet more than you can afford to lose."
)


# --- small formatting helpers --------------------------------------------

def _esc(value: Any) -> str:
    """HTML-escape any value, mapping ``None`` to an em-dash placeholder."""
    if value is None:
        return "&mdash;"
    return html.escape(str(value))


def _fmt_pct(prob: Optional[float]) -> str:
    """Format a 0..1 probability as a one-decimal percentage (``56.1%``)."""
    if prob is None:
        return "&mdash;"
    try:
        return "{:.1f}%".format(float(prob) * 100.0)
    except (TypeError, ValueError):
        return "&mdash;"


def _fmt_odds(odds: Optional[float]) -> str:
    """Format American odds with an explicit sign (``+110`` / ``-128``)."""
    if odds is None:
        return "&mdash;"
    try:
        value = int(round(float(odds)))
    except (TypeError, ValueError):
        return "&mdash;"
    return "+{}".format(value) if value > 0 else str(value)


def _fmt_edge(edge: Optional[float], signed: bool = False) -> str:
    """Format an edge percentage (already in percent units, e.g. ``3.8``)."""
    if edge is None:
        return "&mdash;"
    try:
        value = float(edge)
    except (TypeError, ValueError):
        return "&mdash;"
    return ("{:+.1f}%" if signed else "{:.1f}%").format(value)


def _fmt_rate(rate: Optional[float]) -> str:
    if rate is None:
        return "&mdash;"
    try:
        return "{:.1f}%".format(float(rate) * 100.0)
    except (TypeError, ValueError):
        return "&mdash;"


def _book_price(book: Any, odds: Optional[float]) -> str:
    """Render a "best price" cell as ``-120 DraftKings`` (price first, then book)."""
    price = _fmt_odds(odds)
    if book:
        return '<span class="price">{}</span> <span class="book">{}</span>'.format(
            price, _esc(book)
        )
    return '<span class="price">{}</span>'.format(price)


# --- section builders -----------------------------------------------------

def _edge_card(edge: Dict[str, Any]) -> str:
    """Build one highlighted edge card."""
    away = _esc(edge.get("away"))
    home = _esc(edge.get("home"))
    start = _esc(edge.get("start_local"))
    side = edge.get("side")
    side_team = edge.get(side) if side in ("home", "away") else None
    side_label = _esc(side_team) if side_team else _esc(side)

    model_prob = _fmt_pct(edge.get("model_prob"))
    model_line = _fmt_odds(edge.get("model_line"))
    market_prob = _fmt_pct(edge.get("market_prob"))
    edge_pct = _fmt_edge(edge.get("edge_pct"), signed=True)
    best = _book_price(edge.get("best_book"), edge.get("best_odds"))
    return (
        '<article class="edge-card">'
        '<div class="card-top">'
        '<div class="matchup">'
        '<span class="team away">{away}</span>'
        '<span class="at">@</span>'
        '<span class="team home">{home}</span>'
        "</div>"
        '<div class="start">{start}</div>'
        "</div>"
        '<div class="suggested-label">Suggested bet</div>'
        '<div class="suggested-bet">Take <strong>{side_label} moneyline</strong></div>'
        '<div class="suggested-price">Best available: {best}</div>'
        '<div class="card-grid">'
        '<div class="cell"><span class="k">Model win chance</span>'
        '<span class="v">{model_prob} <span class="sub">({model_line})</span></span></div>'
        '<div class="cell"><span class="k">Market chance</span>'
        '<span class="v">{market_prob}</span></div>'
        '<div class="cell"><span class="k">Model edge</span>'
        '<span class="v edge-val">{edge_pct}</span></div>'
        '<div class="cell"><span class="k">Best price</span>'
        '<span class="v">{best}</span></div>'
        "</div>"
        "</article>"
    ).format(
        away=away,
        home=home,
        start=start,
        side_label=side_label,
        model_prob=model_prob,
        model_line=model_line,
        market_prob=market_prob,
        edge_pct=edge_pct,
        best=best,
    )


def _edges_section(edges: List[Dict[str, Any]], n_edges: int) -> str:
    """Build the suggested-bets section (cards or a calm empty state)."""
    if not edges or n_edges == 0:
        body = (
            '<div class="empty-state">'
            '<div class="empty-title">No suggested bets tonight.</div>'
            '<div class="empty-sub">The model did not find a big enough '
            "pre-game moneyline edge. That is a normal result.</div>"
            "</div>"
        )
    else:
        cards = "".join(_edge_card(e) for e in edges)
        body = '<div class="edge-grid">{}</div>'.format(cards)

    return (
        '<section class="section">'
        '<h2 class="section-title">Tonight\'s Suggested Bets</h2>'
        "{body}"
        "</section>"
    ).format(body=body)


def _result_badge(won: Any) -> str:
    if won is True:
        return '<span class="result-badge res-win">Win</span>'
    if won is False:
        return '<span class="result-badge res-loss">Loss</span>'
    return '<span class="result-badge res-pending">Pending</span>'


def _recent_pick_row(pick: Dict[str, Any]) -> str:
    matchup = "{} @ {}".format(_esc(pick.get("away")), _esc(pick.get("home")))
    return (
        "<tr>"
        "<td>{date}</td>"
        "<td>{pick}</td>"
        "<td>{matchup}</td>"
        '<td class="num">{edge}</td>'
        "<td>{result}</td>"
        "</tr>"
    ).format(
        date=_esc(pick.get("date")),
        pick=_esc(pick.get("pick")),
        matchup=matchup,
        edge=_fmt_edge(pick.get("edge_pct"), signed=True),
        result=_result_badge(pick.get("won")),
    )


def _tracker_section(tracker: Dict[str, Any]) -> str:
    tracker = tracker or {}
    current = tracker.get("current") or {}
    live = tracker.get("live") or {}
    history = tracker.get("history") or []

    recent = live.get("recent") or []
    if recent:
        recent_rows = "".join(_recent_pick_row(p) for p in reversed(recent))
        recent_html = (
            '<div class="table-wrap compact">'
            '<table class="games-table tracker-table">'
            "<thead><tr><th>Date</th><th>Pick</th><th>Game</th>"
            '<th class="num">Edge</th><th>Result</th></tr></thead>'
            f"<tbody>{recent_rows}</tbody></table></div>"
        )
    else:
        recent_html = (
            '<div class="empty-state small">'
            '<div class="empty-title">No tracked suggestions yet.</div>'
            '<div class="empty-sub">The live record starts from saved daily snapshots.</div>'
            "</div>"
        )

    history_rows = []
    for row in history:
        history_rows.append(
            "<tr>"
            "<td>{season}</td>"
            '<td class="num">{graded}</td>'
            '<td class="num">{wins}</td>'
            '<td class="num">{losses}</td>'
            '<td class="num strong">{rate}</td>'
            "<td>{period}</td>"
            "</tr>".format(
                season=_esc(row.get("season")),
                graded=_esc(row.get("graded")),
                wins=_esc(row.get("wins")),
                losses=_esc(row.get("losses")),
                rate=_fmt_rate(row.get("win_rate")),
                period=_esc(row.get("period")),
            )
        )
    history_html = (
        '<div class="table-wrap compact">'
        '<table class="games-table tracker-table">'
        "<thead><tr><th>Season</th><th class=\"num\">Picks</th>"
        '<th class="num">Wins</th><th class="num">Losses</th>'
        '<th class="num">Win rate</th><th>Period</th></tr></thead>'
        "<tbody>{}</tbody></table></div>".format("".join(history_rows))
        if history_rows
        else '<div class="empty-state small"><div class="empty-title">No history available.</div></div>'
    )

    return (
        '<section class="section tracker-section">'
        '<h2 class="section-title">Performance Tracker</h2>'
        '<div class="tracker-tabs">'
        '<input class="tab-radio" type="radio" name="tracker-tab" id="tab-current" checked>'
        '<input class="tab-radio" type="radio" name="tracker-tab" id="tab-history">'
        '<div class="tab-labels">'
        '<label for="tab-current">Current Season</label>'
        '<label for="tab-history">Season History</label>'
        "</div>"
        '<div class="tab-panels">'
        '<div class="tab-panel current-panel">'
        '<div class="tracker-card">'
        '<div><div class="tracker-kicker">{season} season model tracker</div>'
        '<div class="tracker-record">{wins}-{losses}</div>'
        '<div class="tracker-sub">{graded} graded picks &middot; {period}</div></div>'
        '<div class="tracker-rate"><span>{rate}</span><small>win rate</small></div>'
        "</div>"
        '<p class="tracker-note">{basis}. This resets by season automatically. Latest live site suggestions are listed below and move from pending to win/loss once MLB posts final scores.</p>'
        "{recent_html}"
        "</div>"
        '<div class="tab-panel history-panel">'
        '<p class="tracker-note">Historical table uses the fast team-strength model back to 2023 and grades the top daily model picks against final MLB results. It does not claim historical Vegas edge because v1 does not include a paid historical odds feed.</p>'
        "{history_html}"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
    ).format(
        season=_esc(current.get("season") or live.get("season")),
        wins=_esc(current.get("wins", 0)),
        losses=_esc(current.get("losses", 0)),
        graded=_esc(current.get("graded", 0)),
        period=_esc(current.get("period")),
        rate=_fmt_rate(current.get("win_rate")),
        basis=_esc(current.get("basis")),
        recent_html=recent_html,
        history_html=history_html,
    )


def _game_row(game: Dict[str, Any]) -> str:
    """Build one row of the all-games table."""
    away = _esc(game.get("away"))
    home = _esc(game.get("home"))
    start = _esc(game.get("start_local"))

    status = game.get("status")
    label, css = _STATUS_META.get(status, _STATUS_META["no_edge"])

    edge_cls = "edge-cell"
    if status == "surfaced":
        edge_cls += " edge-pos"
    edge_txt = _fmt_edge(game.get("edge_pct"), signed=(status == "surfaced"))

    away_best = _book_price(game.get("best_away_book"), game.get("best_away_odds"))
    home_best = _book_price(game.get("best_home_book"), game.get("best_home_odds"))

    return (
        "<tr>"
        '<td class="matchup-cell">'
        '<span class="row-away">{away}</span>'
        '<span class="row-at"> @ </span>'
        '<span class="row-home">{home}</span>'
        '<div class="row-start">{start}</div>'
        "</td>"
        '<td class="num">{model_prob}</td>'
        '<td class="num">{model_line}</td>'
        '<td class="num">{market_prob}</td>'
        '<td class="num {edge_cls}">{edge_txt}</td>'
        '<td><span class="status-badge {css}">{label}</span></td>'
        '<td class="best-cell">{away_best}</td>'
        '<td class="best-cell">{home_best}</td>'
        "</tr>"
    ).format(
        away=away,
        home=home,
        start=start,
        model_prob=_fmt_pct(game.get("model_prob")),
        model_line=_fmt_odds(game.get("model_line")),
        market_prob=_fmt_pct(game.get("market_prob")),
        edge_cls=edge_cls,
        edge_txt=edge_txt,
        css=css,
        label=label,
        away_best=away_best,
        home_best=home_best,
    )


def _games_section(games: List[Dict[str, Any]]) -> str:
    """Build the "All Games" table section."""
    if not games:
        body = (
            '<div class="empty-state">'
            '<div class="empty-title">No pre-game games scheduled.</div>'
            "</div>"
        )
    else:
        rows = "".join(_game_row(g) for g in games)
        body = (
            '<div class="table-wrap">'
            '<table class="games-table">'
            "<thead><tr>"
            "<th>Matchup</th>"
            '<th class="num">Model %</th>'
            '<th class="num">Model line</th>'
            '<th class="num">Market %</th>'
            '<th class="num">Edge</th>'
            "<th>Status</th>"
            "<th>Best (away)</th>"
            "<th>Best (home)</th>"
            "</tr></thead>"
            "<tbody>{rows}</tbody>"
            "</table>"
            "</div>"
        ).format(rows=rows)

    return (
        '<section class="section">'
        '<h2 class="section-title">Full Slate</h2>'
        "{body}"
        "</section>"
    ).format(body=body)


# --- public entry point ---------------------------------------------------

def render_html(context: dict) -> str:
    """Render the full nightly dashboard as a self-contained HTML string.

    Parameters
    ----------
    context:
        Prepared context dict (see module/project docs). All fields are
        accessed defensively; missing values degrade gracefully.

    Returns
    -------
    str
        A complete, standalone HTML document with an inline dark theme.
    """
    context = context or {}

    date = _esc(context.get("date"))
    generated_at = _esc(context.get("generated_at"))

    try:
        n_games = int(context.get("n_games") or 0)
    except (TypeError, ValueError):
        n_games = 0
    try:
        n_edges = int(context.get("n_edges") or 0)
    except (TypeError, ValueError):
        n_edges = 0

    edges = context.get("edges") or []
    games = context.get("games") or []

    edge_word = "suggested bet" if n_edges == 1 else "suggested bets"
    game_word = "game" if n_games == 1 else "games"

    edges_html = _edges_section(edges, n_edges)
    tracker_html = _tracker_section(context.get("tracker") or {})
    games_html = _games_section(games)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="dark">\n'
        "<title>AlgoBall &middot; {date}</title>\n"
        "<style>{css}</style>\n"
        "</head>\n"
        '<body>\n'
        '<div class="container">\n'
        '<header class="site-header">\n'
        '<div class="brand-row">\n'
        '<span class="brand">AlgoBall</span>\n'
        '<span class="brand-date">{date}</span>\n'
        "</div>\n"
        '<div class="freshness">Pre-game snapshot - as of {generated_at}. '
        "Frozen for the day.</div>\n"
        '<div class="counts">{n_games} {game_word} &middot; '
        '{n_edges} {edge_word}</div>\n'
        '<p class="about">{about}</p>\n'
        '<div class="risk-notice">{risk_notice}</div>\n'
        "</header>\n"
        "{edges_html}\n"
        "{tracker_html}\n"
        "{games_html}\n"
        '<footer class="site-footer">'
        "AlgoBall &middot; model-vs-market, measured. Not financial advice."
        "</footer>\n"
        "</div>\n"
        "</body>\n"
        "</html>\n"
    ).format(
        date=date,
        css=_CSS,
        generated_at=generated_at,
        n_games=n_games,
        game_word=game_word,
        n_edges=n_edges,
        edge_word=edge_word,
        about=html.escape(_ABOUT),
        risk_notice=html.escape(_RISK_NOTICE),
        edges_html=edges_html,
        tracker_html=tracker_html,
        games_html=games_html,
    )


# --- inline stylesheet ----------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: #0b0e11;
  color: #e6edf3;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 28px 20px 64px;
}

/* header */
.site-header { margin-bottom: 28px; }
.brand-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 12px;
}
.brand {
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #fff;
}
.brand-date {
  font-size: 15px;
  color: #8b949e;
  font-variant-numeric: tabular-nums;
}
.freshness {
  margin-top: 12px;
  display: inline-block;
  background: #11271a;
  color: #3fb950;
  border: 1px solid #1f6f3a;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13.5px;
  font-weight: 600;
}
.counts {
  margin-top: 12px;
  font-size: 14px;
  color: #8b949e;
  font-variant-numeric: tabular-nums;
}
.about {
  margin: 14px 0 0;
  font-size: 15px;
  color: #c9d1d9;
  line-height: 1.55;
  max-width: 820px;
}
.risk-notice {
  margin-top: 14px;
  max-width: 860px;
  background: #1f1a10;
  color: #f2cc60;
  border: 1px solid #6e5a1f;
  border-radius: 8px;
  padding: 11px 13px;
  font-size: 13px;
  line-height: 1.45;
}

/* sections */
.section { margin-top: 34px; }
.section-title {
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #8b949e;
  margin: 0 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid #1c2329;
}

/* edge cards */
.edge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
.edge-card {
  background: #11181d;
  border: 1px solid #1f6f3a;
  border-left: 4px solid #3fb950;
  border-radius: 12px;
  padding: 16px 18px;
}
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}
.matchup { font-size: 16px; font-weight: 700; }
.matchup .at { color: #6e7681; margin: 0 6px; font-weight: 400; }
.matchup .home { color: #fff; }
.matchup .away { color: #c9d1d9; }
.start {
  font-size: 12.5px;
  color: #8b949e;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.suggested-label {
  margin-top: 16px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #3fb950;
}
.suggested-bet {
  margin-top: 2px;
  font-size: 24px;
  line-height: 1.15;
  font-weight: 800;
  color: #fff;
}
.suggested-bet strong { color: #fff; }
.suggested-price {
  margin-top: 8px;
  font-size: 14px;
  color: #adbac7;
}
.suggested-price .price {
  color: #3fb950;
  font-weight: 800;
}
.card-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 14px;
}
.cell { display: flex; flex-direction: column; gap: 2px; }
.cell .k {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #6e7681;
}
.cell .v {
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cell .v .sub { color: #8b949e; font-weight: 400; font-size: 13px; }
.edge-val { color: #3fb950; }
/* empty state */
.empty-state {
  background: #11181d;
  border: 1px solid #1c2329;
  border-radius: 12px;
  padding: 26px 22px;
  text-align: center;
}
.empty-title { font-size: 16px; font-weight: 600; color: #c9d1d9; }
.empty-sub { margin-top: 6px; font-size: 13.5px; color: #768089; }
.empty-state.small {
  padding: 18px 16px;
  text-align: left;
}

/* tracker */
.tracker-tabs {
  background: #11181d;
  border: 1px solid #1c2329;
  border-radius: 12px;
  padding: 14px;
}
.tab-radio {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.tab-labels {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: #0b0e11;
  border: 1px solid #1c2329;
  border-radius: 8px;
}
.tab-labels label {
  display: inline-block;
  cursor: pointer;
  border-radius: 6px;
  padding: 7px 12px;
  font-size: 13px;
  font-weight: 700;
  color: #8b949e;
}
#tab-current:checked ~ .tab-labels label[for="tab-current"],
#tab-history:checked ~ .tab-labels label[for="tab-history"] {
  background: #11271a;
  color: #3fb950;
}
.tab-panels { margin-top: 16px; }
.tab-panel { display: none; }
#tab-current:checked ~ .tab-panels .current-panel,
#tab-history:checked ~ .tab-panels .history-panel {
  display: block;
}
.tracker-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 12px;
}
.tracker-kicker {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #8b949e;
}
.tracker-record {
  margin-top: 2px;
  font-size: 34px;
  line-height: 1.05;
  font-weight: 800;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.tracker-sub {
  margin-top: 4px;
  font-size: 13px;
  color: #768089;
}
.tracker-rate {
  min-width: 112px;
  text-align: right;
}
.tracker-rate span {
  display: block;
  font-size: 28px;
  line-height: 1.1;
  font-weight: 800;
  color: #3fb950;
  font-variant-numeric: tabular-nums;
}
.tracker-rate small {
  display: block;
  margin-top: 3px;
  color: #8b949e;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.tracker-note {
  margin: 0 0 14px;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.45;
}
.table-wrap.compact {
  border-radius: 8px;
}
.tracker-table {
  min-width: 620px;
}
.strong {
  color: #e6edf3;
  font-weight: 800;
}
.result-badge {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
}
.res-win { background: #11271a; color: #3fb950; border-color: #1f6f3a; }
.res-loss { background: #2a1416; color: #f85149; border-color: #6e2329; }
.res-pending { background: #161c21; color: #8b949e; border-color: #232a31; }

/* games table */
.table-wrap {
  overflow-x: auto;
  border: 1px solid #1c2329;
  border-radius: 12px;
}
.games-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  min-width: 720px;
}
.games-table thead th {
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #6e7681;
  font-weight: 600;
  padding: 12px 14px;
  background: #0f1418;
  border-bottom: 1px solid #1c2329;
  white-space: nowrap;
}
.games-table tbody td {
  padding: 12px 14px;
  border-bottom: 1px solid #161c21;
  vertical-align: top;
}
.games-table tbody tr:last-child td { border-bottom: none; }
.games-table tbody tr:hover { background: #0f1519; }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.matchup-cell { min-width: 180px; }
.row-home { color: #fff; font-weight: 600; }
.row-away { color: #c9d1d9; }
.row-at { color: #6e7681; }
.row-start {
  margin-top: 3px;
  font-size: 11.5px;
  color: #768089;
  font-variant-numeric: tabular-nums;
}
.edge-cell { color: #8b949e; }
.edge-pos { color: #3fb950; font-weight: 700; }
.best-cell { white-space: nowrap; }
.best-cell .price { font-variant-numeric: tabular-nums; color: #e6edf3; font-weight: 600; }
.best-cell .book { color: #768089; font-size: 12px; }
.price { font-variant-numeric: tabular-nums; }
.book { color: #768089; }

/* status badges */
.status-badge {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 999px;
  white-space: nowrap;
  border: 1px solid transparent;
}
.st-edge { background: #11271a; color: #3fb950; border-color: #1f6f3a; }
.st-none { background: #161c21; color: #8b949e; border-color: #232a31; }
.st-bug { background: #2a1416; color: #f85149; border-color: #6e2329; }
.st-fragile { background: #2a2310; color: #d29922; border-color: #6e5a1f; }
.st-nomkt { background: #161c21; color: #768089; border-color: #232a31; }

/* footer */
.site-footer {
  margin-top: 40px;
  padding-top: 18px;
  border-top: 1px solid #1c2329;
  font-size: 12.5px;
  color: #5c656e;
  text-align: center;
}

/* mobile */
@media (max-width: 600px) {
  .container { padding: 22px 14px 48px; }
  .brand { font-size: 26px; }
  .edge-grid { grid-template-columns: 1fr; }
  .tracker-card { align-items: flex-start; flex-direction: column; }
  .tracker-rate { min-width: 0; text-align: left; }
}
"""
