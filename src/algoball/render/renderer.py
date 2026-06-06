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

_DISCLAIMER = (
    "Analytical content, not betting advice. The model generates its own "
    "pre-game odds; most nights it finds 0-3 edges, often none - that is correct."
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
    note = edge.get("note")

    note_html = ""
    if note:
        note_html = '<p class="card-note">{}</p>'.format(_esc(note))

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
        '<div class="edge-pick">Edge: <strong>{side_label}</strong></div>'
        '<div class="card-grid">'
        '<div class="cell"><span class="k">Model</span>'
        '<span class="v">{model_prob} <span class="sub">({model_line})</span></span></div>'
        '<div class="cell"><span class="k">Market</span>'
        '<span class="v">{market_prob}</span></div>'
        '<div class="cell"><span class="k">Edge</span>'
        '<span class="v edge-val">{edge_pct}</span></div>'
        '<div class="cell"><span class="k">Best price</span>'
        '<span class="v">{best}</span></div>'
        "</div>"
        "{note_html}"
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
        note_html=note_html,
    )


def _edges_section(edges: List[Dict[str, Any]], n_edges: int) -> str:
    """Build the "Tonight's Edges" section (cards or a calm empty state)."""
    if not edges or n_edges == 0:
        body = (
            '<div class="empty-state">'
            '<div class="empty-title">No qualifying edges tonight.</div>'
            '<div class="empty-sub">The model agrees with the market - '
            "that's the honest, common result.</div>"
            "</div>"
        )
    else:
        cards = "".join(_edge_card(e) for e in edges)
        body = '<div class="edge-grid">{}</div>'.format(cards)

    return (
        '<section class="section">'
        '<h2 class="section-title">Tonight\'s Edges</h2>'
        "{body}"
        "</section>"
    ).format(body=body)


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
        '<h2 class="section-title">All Games</h2>'
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

    edge_word = "edge" if n_edges == 1 else "edges"
    game_word = "game" if n_games == 1 else "games"

    edges_html = _edges_section(edges, n_edges)
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
        '<p class="disclaimer">{disclaimer}</p>\n'
        "</header>\n"
        "{edges_html}\n"
        "{games_html}\n"
        '<footer class="site-footer">'
        "AlgoBall &middot; model-vs-market, measured. Not betting advice."
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
        disclaimer=html.escape(_DISCLAIMER),
        edges_html=edges_html,
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
.disclaimer {
  margin: 14px 0 0;
  font-size: 13px;
  color: #768089;
  line-height: 1.45;
  max-width: 760px;
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
.edge-pick {
  margin-top: 10px;
  font-size: 13.5px;
  color: #adbac7;
}
.edge-pick strong { color: #3fb950; }
.card-grid {
  margin-top: 14px;
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
.card-note {
  margin: 14px 0 0;
  padding-top: 12px;
  border-top: 1px solid #1c2329;
  font-size: 12.5px;
  color: #8b949e;
}

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
}
"""
