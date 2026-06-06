# AlgoBall — Concept (the simple north star)

## The one line

**AlgoBall is an algorithm that builds its OWN before-the-game odds for every MLB
game, then flags any moneyline edges for the night. It refreshes once a day off
that day's schedule, pre-game only. It never runs during a game.**

That is the whole product. Everything below serves this one sentence.

Why MLB first: it has the most and best **free** statistics, so the model can be
honest and complete without paying for data.

---

## How it works (simple steps)

Once a day, in the late morning ET (before the earliest first pitch), one command
runs these steps in order and then exits. Nothing stays running.

1. **Get today's games.** Pull today's MLB schedule from the free MLB Stats API
   (no key). Keep only real regular-season games. Read each game's two teams,
   start time, ballpark, and probable starting pitchers.

2. **Drop anything already started.** Skip any game whose start time has passed.
   This is the hard guarantee that the tool is pre-game only — it is structurally
   incapable of touching a live game.

3. **Build the model's OWN odds.** For each game, turn free stats into each side's
   expected runs (starting-pitcher quality via FIP, team offense via runs/game,
   and an optional ballpark nudge), then push the run difference through the
   already-built win-probability formula to get a home win probability — the
   model's own pre-game number. Convert that to a fair American price. This is
   "the algorithm's own odds," published per game.

4. **Get tonight's moneylines.** One call to The Odds API (1 credit) for tonight's
   MLB moneyline prices across US books.

5. **Strip the vig and compare.** De-vig each book's price to its fair number, take
   the consensus, and compare it to the model's own number. The difference is the
   edge.

6. **Apply the guardrails and publish.** Every game runs through the existing
   calibration guards (which make the old 81% / +34% over-confidence bug
   impossible). Only sane, small divergences survive — typically **0 to 3 a
   night, often none, and that is the correct, honest result.** Write one dated
   snapshot file and one simple page showing the model's fair line per game plus
   any moneyline edges, stamped "pre-game, as of <run time> ET." The page is
   frozen for the day.

**Honest expectation (kept on purpose):** a free pre-game model essentially cannot
beat the sharp closing line. Real MLB moneyline edges are tiny (~1-5%). AlgoBall is
an honest "here are tonight's model-vs-market divergences," self-graded over time —
not a guaranteed money machine. An empty night is the system working.

---

## Owner-intent checklist (does it cover everything you asked?)

| Your words | Covered? | How |
|---|---|---|
| An algorithm that creates its OWN before-the-game odds | YES | Step 3 builds each game's win probability and a fair American line from scratch, independent of the book. |
| Before the game, show any MONEYLINE edges for the night | YES | Steps 4-6 de-vig the market and surface the night's moneyline divergences (0-3 typical, often none). |
| MLB first because it has the most/best free statistics | YES | Every model input comes from the free MLB Stats API (no key). The only paid feed is the odds, on a free tier. |
| Later: HITS or anything else you could bet on with good stats | LATER | Player props (hits + pitcher strikeouts first) are an explicit future phase, off by default, not built in v1. |
| Update EVERY DAY with the day's schedule | YES | The run is keyed to today's date and re-pulls the schedule each morning. |
| Does NOT operate mid-game | YES | Single morning batch before first pitch + a hard "drop already-started games" filter. No live polling. |
| I don't need it that complicated / keep it simple | YES | Four inputs, one formula, one odds call, one page. No servers, no polling, no real-time arbitrage. |

---

## What's already built vs. the small gap

**Already built and proven** (pure Python, 15 passing tests, in `src/algoball/model/`):

- `winprob.py` — the deterministic win-probability formula. This IS the model's
  own odds engine; `win_probability_from_runs(...)` already bakes in home-field
  advantage. Use it as-is.
- `devig.py` — strips the bookmaker margin off the market price.
- `calibrate.py` — the guardrails that make the old 81% / +34% over-confidence
  bug structurally impossible (caps at 0-3 surfaced games a night).
- `lineshop.py` — best price across books, from a single daily pull.

**The small remaining gap** (everything else is plumbing, not new science):

1. **A tiny expected-runs transform** (~30 lines, `runs.py`): turn pitcher FIP +
   team runs/game (+ optional park) into each side's expected runs to feed
   `winprob.py`. This is the only genuinely new modeling math.
2. **A ~6-line "probability -> American odds" helper** in `devig.py` so the model
   can publish its own fair line (today the file only goes American -> probability).
3. **A thin daily runner**: fetch the schedule + odds, call the existing core,
   write one JSON snapshot and one HTML page. (`ingest/`, `render/`, `storage/`
   folders exist but are empty.)

---

## Simple build plan to a working v1

1. **Add the prob -> American helper** to `devig.py` (~6 lines) so the model can
   publish its own line. Add a unit test.
2. **Write `runs.py`** (~30 lines): `expected_runs = LEAGUE_R x team_offense x
   opposing_starter_factor x park`, every factor centered on 1.0. Sanity test:
   two even teams, neutral starters -> ~0.534 home (the HFA target).
3. **Write the daily runner** (one command, e.g. `python -m algoball`): get
   schedule (free), drop started games, build model odds, get odds (1 call),
   de-vig, run `evaluate_game`, write `data/YYYY-MM-DD.json` + `site/index.html`.
4. **One config file** of constants: `LEAGUE_R ~= 4.5`, `LEAGUE_FIP ~= 4.3`,
   `STARTER_IP_SHARE ~= 0.6`, plus the existing `SD_DIFF = 4.3` / `HFA_RUNS =
   0.37`. Hardcode for v1.
5. **Honest page**: model fair line per game, any edges, a clear empty state, and
   a "pre-game, as of <time> ET" stamp.
6. **(Optional, hands-off)** wrap the same command in ONE GitHub Actions cron
   (timed before first pitch) plus a manual "Run workflow" button, publishing the
   page to GitHub Pages. Still once a day, still pre-game only, no servers.

Quota check: one odds call a day is ~30 credits/month against a free 500. Non-issue.

---

## Later phase: HITS and other props (NOT in v1)

Exactly as you said — "later, hits or anything else with good statistics."

- **Lead with batter hits** (over/under), and ship **pitcher strikeouts**
  alongside it because strikeout rate is the cleanest, fastest-stabilizing free
  stat. Total bases and home runs come after (noisier).
- It reuses the same shape: blend the batter's free rate against the pitcher by
  handedness, estimate at-bats from the lineup slot, push through a simple
  closed-form distribution to get P(over the line), then run the SAME de-vig and
  guardrails. No new infrastructure.
- It stays a later phase: the props switch defaults **OFF** (v1 stays moneyline-
  only and byte-identical), it waits until the moneyline product is shipped and
  self-grading, and it is capped to a few games a day because full-slate props
  would blow the free odds quota. A confirmed lineup is required before a hit prop
  surfaces — which fits the once-a-day pre-game batch perfectly.

---

## What we are trimming (to honor "keep it simple")

Earlier design rounds over-built for a more complex vision. These are now
**out of scope** and should be trimmed from the older docs:

- **Always-on hosting** — no Railway, no Postgres, no S3/object storage, no ORM.
  One local command, one flat JSON file per day. (Use stdlib SQLite only if/when
  you later want season-long self-grading.)
- **Continuous polling / real-time soft-line speed-arbitrage** — dropped.
  `lineshop.py` is kept ONLY as a one-shot best-price lookup on the single daily
  odds pull; ignore its docstring's "always-on, poll on an interval" framing.
- **Two scheduled runs (afternoon + evening) and staggered closing-line capture**
  — collapsed to ONE morning run. The second run only existed to chase late-
  posting lineups, which v1 moneyline does not use (probable pitchers are known
  ahead).
- **Heavy extras left out of v1**: lineup handedness/platoon splits, per-game
  innings modeling, weather, umpire data, recent-form, Monte Carlo simulation,
  the Elo/PythagenPat cross-checks, and the bootstrap/backtester validation stack.
  The closed-form win-prob map plus the existing guards already do the job. These
  are deferred, not deleted.

The footprint of v1 is: a daily script that hits free endpoints, makes one odds
call, writes one JSON file, and renders one page. That is the whole thing.
