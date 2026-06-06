# AlgoBall — Architecture (docs/ARCHITECTURE.md)

> **Status:** FINAL, verified design (round 2). This revision folds in a full fact-check,
> an architecture-alternatives review, and two deep-dives. Every factual correction is
> quoted inline; the companion `VERIFICATION.md` records each claim, verdict, and source.
> Two owner decisions are resolved here: (1) coverage is **BOTH afternoon + evening** (two
> daily prediction runs), and (2) the safety band is set from empirical evidence by the
> senior engineer (below).

## 1. Overview

AlgoBall is a small, layered Python package that runs on a schedule, pulls the MLB slate
plus sportsbook odds from free sources, estimates a single-game home-team win probability
per game, removes the bookmaker vig to get a fair consensus market line, surfaces only
games with a genuine **model-vs-market divergence** (typically 0-3 per day, often none),
and renders a dark static `index.html` auto-published to GitHub Pages.

**Honest framing (resolved this round).** Output is analytical content, **not** betting
advice, and the framing is now explicitly *measurement-first*, not profit-claiming. The
evidence is unambiguous: a free-data, public-input model run after lineups post (i.e. near
the sharpest point of the day) essentially **cannot beat the de-vigged closing line** —
closing lines are among the most efficient prices in sports, and every input we use (FIP,
park factors, platoon splits, handedness) is public and already in that price. AlgoBall is
therefore positioned as a transparent, falsifiable **measurement instrument**: each day it
tests whether a free-data model adds *any* information beyond the de-vigged market, surfaces
specific model-vs-market divergences as analytical content, and keeps a public CLV
scoreboard against the sharpest available close. A surfaced game is a **labeled divergence**,
not a profit claim, until the CLV/incremental-log-loss scoreboard is positive and
significant. See §12 for the value-vs-market verdict.

### The defining constraint: the calibration history

An earlier build emitted an **81.2% home win probability and a +34.4% edge** on the Astros
(model 81.2% vs a de-vigged market of 46.8%) and ~19 "best bets" per day. Genuine MLB edges
run 1-5%, with 6-8% being a strong play. The entire architecture is designed so that failure
mode is **structurally impossible to reproduce**, and so that any future regression toward
it fails CI.

### The single most important fact, stated correctly

The first draft conflated two different distributions. They must be kept separate, because
the safety guards fire on the **model** distribution, not the market distribution:

- **Calibrated predictive MODELS** essentially never exceed **~0.72-0.74** on a single
  game. FiveThirtyEight's pitcher-aware Elo, computed directly from its own
  `mlb_elo_latest.csv` (2023, 2429 rows), had a season-max single-game win probability of
  **74.22%** (HOU vs OAK, Framber Valdez, 2023-05-21) and a 75th percentile of only ~58.7%.
  Our own run-differential model (below) would need a **~3.8-run** expected edge to reach
  0.81 — structurally impossible from regressed FIP/offense inputs.
- **De-vigged MARKETS** reach materially higher, **~0.80-0.82** in the extreme tail. The
  documented record road favorite (Astros -550 / Orioles +380, 2024) de-vigs multiplicatively
  to **exactly 80.2%**; Astros -521 (2019-09-22) with a realistic +400/+420 dog de-vigs to
  ~80.8-81.4%; a ~-600 line de-vigs to ~82.5%. The all-time extreme sits ~82-84%.

**Consequence for the bug framing.** A raw model output of 0.81 is *out-of-distribution for
the model* (~0.74 cap) but *not* for an extreme market favorite (~0.80-0.81). The original
0.81 was a bug **because it occurred on an ordinary game the market priced at 46.8% — a
~34pp model-vs-market divergence**, not because 0.81 is an unreachable number. Therefore the
**model-vs-market divergence guard is the primary, load-bearing catcher** of the bug class;
the absolute raw-probability band is a deliberately redundant secondary catch that fires at
source. The prior draft's claim that "heaviest real de-vigged moneylines sit near 70-74%"
and extremes reach "75-78%" **understated the market right tail by ~6-10pp and is corrected
throughout this document.**

### What the re-derivation changed (resolved contradictions)

- **Old (broken) design:** `p_final = 0.30*p_model + 0.70*p_market`, then a 6% floor on the
  *post-shrink* edge. Because post-shrink edge `= 0.30*(p_model - p_market)`, a 6% floor
  required the raw model to disagree with the market by **0.06/0.30 = 20 percentage points**
  to emit, and the 10% post-shrink ceiling capped divergence at **0.10/0.30 = 33.3pp**. The
  only emittable bets were 20-33pp model-vs-market blowups — *the model's worst errors* —
  while every genuine 1-5% edge was silently discarded. (Both figures verified exactly:
  0.06/0.30 = 0.20, 0.10/0.30 = 0.3333.)
- **New (resolved) design:** guards operate on the **diagnostic raw quantities** (raw
  probability and raw model-vs-market divergence), the emit window is **jointly derived**
  from the shrink weight and floor so it maps to *plausible* divergences (~4.3-10pp), the
  shrink weight `w` is **pinned near 0** until the model demonstrably beats the market
  out-of-sample, and the ill-defined "variance-inflation factor on a Skellam CDF" is
  replaced by a **deterministic, correctly-dispersed** run-differential model with a single
  published parameter.

The stack is deliberately minimal for a non-technical solo owner: one `uv`-managed package,
a small set of GitHub Actions workflows, one HTML file, runnable in CI by a button or
locally with `uv run python -m algoball`.

---

## 2. Design principles

1. **Honesty over output.** 0-3 divergences or NONE is the normal, correct result. A blank
   "no qualifying divergences today" page is the model working. Large green edge numbers are
   the bug, not the goal. A displayed divergence on a surfaced game is ~1.5-3.5%, never +34%.

2. **Measurement, not profit claims.** The homepage headline is the falsifiable question
   *"does a free-data model beat the market?"* and its current answer (incremental
   out-of-sample log-loss vs a market-only baseline, plus a CLV record). Surfaced games are
   labeled **divergences**, not "value bets," until the scoreboard is positive and
   significant.

3. **Calibration is a first-class, tested module.** De-vig, win-prob mapping, the raw-OOD
   guard, the divergence guard, the de-vig-method-fragility guard, the no-market guard,
   shrinkage, clamp, floor, max-bets, and the validation metrics each live as named pure
   functions with unit + golden tests.

4. **No single guard is trusted, and guards fire on the diagnostic quantity.** The 81.2% bug
   sat *under* an 85% cap, so caps alone are necessary-not-sufficient. The **divergence
   guard** is primary; the **raw-OOD band** is a redundant source-level catch; both fire
   *before* shrinkage on the raw quantities.

5. **Never convert a starter's FIP (or any rate stat) directly to a team win probability.** A
   starter throws ~5-6 of 9 innings, is 1 of 9 defenders, and never bats; his regressed edge
   moves expected run differential by a fraction of a run, not a verdict.

6. **Single-game variance is mandatory and correctly specified.** Expected run differential
   is always pushed through a high-variance distribution, because a ~0.5-run pregame edge is
   only **~55%** to win (empirically ~54-56%), not 70%+. The governing parameter is the
   run-differential standard deviation `SD_diff ≈ 4.3`, derived from the empirical
   over-dispersion (variance/mean ≈ 2.0-2.2) and the realized average margin of victory
   (~3.3 runs). To reach 0.81 the model would need a ~3.8-run edge.

7. **The de-vigged market is the best single-game prior that exists.** The model is shrunk
   toward it; the shrink weight is pinned near 0 and the model is **never** trusted to wildly
   diverge from it. The free-tier anchor is **soft US books**, discounted accordingly; the
   **sharp anchor is Pinnacle (eu region)**, used for the divergence reference and CLV.

8. **Validate the model, not the market copy.** Because final probabilities are mostly
   market, raw Brier/CLV will look fine even if the model is pure noise. The primary metric
   is the **model component's incremental out-of-sample log-loss versus a market-only
   baseline**, on **all** games. If the model does not beat market-only, `w -> 0` and nothing
   emits.

9. **The validation loop must be closed.** Nothing is validated unless outcomes are graded. A
   dedicated grading step writes actual win/loss (and a per-game closing line) back into prior
   snapshots. "Graded" is a first-class snapshot state.

10. **Free data only, honestly.** Six of seven wishlist signals have real free feeds; umpires
    do not and remain an explicit hand-filled CSV stub, absent-by-default, near-zero weight,
    clearly labeled non-live.

11. **Fail safe and loud, never silent and confident.** Missing market => suppress to NONE
    (never model-only). Failed runs => notify the owner and still keep the repo alive.

12. **Right-sized for a solo non-technical owner.** No DB server, no microservices, no SSG
    framework, no RNG state to manage. One package; a few small workflows; one command / one
    button. One type system (frozen pydantic v2) end-to-end.

---

## 3. Module breakdown

> **Type system (resolved):** one type system end-to-end — **frozen pydantic v2 models** at
> the boundary *and* internally. The dual pydantic-+-dataclass mirror from the original draft
> is dropped. Pure math functions take frozen models and return frozen models; they are fully
> testable offline. Field-extraction logic lives in a named, tested place: each ingest
> client's `parse.py` / `to_model()`.

### `config`
- **Responsibility:** single typed source of settings/secrets via `pydantic-settings`; every
  calibration constant is a named, overridable field (never a magic number).
- **Inputs:** `.env` (git-ignored) and GitHub Actions env; `.env.example` committed with a
  blank `ODDS_API_KEY`.
- **Outputs:** cached `get_settings()` returning a `Settings(BaseSettings)`.
- **Key decisions:** `odds_api_key: SecretStr`. Calibration constants (final values in §6):
  `PROB_OOD_BAND`, `PROB_OOD_SOFT_BAND`, `MAX_RAW_DIVERGENCE`, `SHRINK_W`, `EDGE_FLOOR`,
  `PROB_CLAMP`, `DEVIG_METHOD_FRAGILE_TOL`, `MAX_BETS_PER_DAY`, `MIN_BOOKS`, `MIN_IP_FOR_FIP`,
  `CFIP_CONSTANT`, `SD_DIFF`, `EXTRA_INNINGS_HOME_WINRATE`, `HFA_RUNS`, `regions`, `markets`,
  `oddsFormat`, `slate_safety_margin_minutes`, `statsapi_cache_ttl`. `@lru_cache` so built
  once. Identical code local and in CI (12-factor).

### `ingest`
- **Responsibility:** all external I/O. One thin client per source, each wrapped with
  `tenacity` retries (timeouts/5xx only, never 4xx), explicit timeouts.
- **Inputs:** The Odds API (`ODDS_API_KEY`), MLB Stats API (no key), Open-Meteo (no key,
  `/v1/forecast`), static park-factor CSV, optional umpire CSV.
- **Outputs:** raw JSON/CSV parsed into frozen pydantic boundary models.
- **Key decisions:**
  - `odds_api.py`: `GET /v4/sports/baseball_mlb/odds?regions=us&markets=h2h&oddsFormat=american`
    costs **exactly 1 credit** (cost = markets × regions = 1 × 1; `oddsFormat` is free).
    Supports `commenceTimeFrom`/`commenceTimeTo` ISO-8601 filtering at **no extra cost**, and
    **empty responses do not count against quota**. Logs `x-requests-remaining` /
    `x-requests-used` / `x-requests-last` every run; fails soft near zero. The free Starter
    tier is **500 credits/month, reset on the 1st of each month**. **Odds are NOT cached** (a
    stale line produces garbage divergences and garbage CLV). The sharp **Pinnacle anchor is
    fetched via `regions=eu`** — note **`regions=us,eu` costs 2 credits** (1 market × 2
    regions), corrected from the prior draft's "still 1 credit" claim.
  - `mlb_statsapi.py`:
    - `schedule?sportId=1&date=...&hydrate=probablePitcher,venue,team` — returns the slate
      under `dates[].games[]`. **Verified live:** `gamePk` (int); `venue` at **game level**
      (`games[].venue.{id,name}`); probable pitchers nested **per side** under
      `games[].teams.home.probablePitcher` / `.away.probablePitcher` (`{id, fullName, link}`)
      — **NOT** a top-level `games[].probablePitcher`. `probablePitcher` is **optional / null
      before MLB announces starters**, so it is re-hydrated on the second daily run. **Filter
      `gameType == "R"`** to exclude All-Star/exhibition games (the slate is not always
      regular-season).
    - `boxscore?hydrate=person` — the `hydrate=person` is **required** to add handedness;
      without it `person` is only `{id, fullName, link, boxscoreName}`. With it, every player's
      `person` gains `batSide` and `pitchHand`, each `{code, description}` (batSide codes
      L/R/S; pitchHand L/R). **Both fields appear on every person (hitter AND pitcher):** the
      platoon model selects `batSide` for hitters and `pitchHand` for the starter; role is
      derived from lineup/position, never from field presence. (Alternative: `GET
      /people/{id}` returns the same fields natively without hydrating the boxscore.)
    - `people/{id}/stats?stats=sabermetrics&group=pitching[&season=YYYY]` — returns a real,
      populated `fip` field (verified live for 2026; also `xfip`, `fipMinus`, `war`). The `fip`
      key lives **only** in the `sabermetrics` group (the standard `season` group has no
      `fip`). **The API imposes no minimum-IP gate** — it returns `fip` for any pitcher with
      ≥1 appearance and an **empty `stats: []` / empty splits** when the player has no pitching
      data (early-season zero-appearance pitcher, or a non-pitcher). The `MIN_IP_FOR_FIP` gate
      and the regressed manual-FIP fallback are therefore **AlgoBall's consumer-side design
      choice**, needed because (a) the group can be empty in March/April and (b) tiny-IP FIP
      is high-variance. The empty case is handled explicitly.
    - `statSplits&sitCodes=vl,vr` for L/R; `lastXGames` for form.
  - `grade.py` (**required**): reads `linescore` / final scores for prior-day `gamePks` and
    writes win/loss outcomes into past snapshots. Without this, no metric in §7 is computable.
  - `park_factors.py` / `umpires.py`: load hand-maintained CSVs from `inputs/`. Umpire is
    absent-by-default.

### `models`
- **Responsibility:** the typed data contract — frozen pydantic v2 at the boundary and
  internally.
- **Outputs:** `RawOddsGame` / `RawSchedule` / `RawBoxscore` (boundary) -> `GameContext`,
  `TeamFeatures`, `PitcherFeatures`, `MarketLine`, `ModelPrediction`, `Divergence`, `Snapshot`
  (internal, all frozen). Every optional signal field is `Optional`.
- **Key decisions:** pydantic gives clear errors when the undocumented, no-SLA MLB Stats API
  drifts. Frozen => modeling/calibration stay pure.

### `transform`
- **Responsibility:** raw stats -> model-ready **regressed** features (input-regression
  Layer 0).
- **Key decisions:**
  - Regress FIP toward league mean by IP (BB/HR stabilize ~120-150 IP; K fastest) **before**
    use, with the `MIN_IP_FOR_FIP` gate. **Manual-FIP fallback** (when sabermetrics FIP is
    empty or below the IP gate) uses the FanGraphs formula:
    `FIP = ((13*HR) + (3*(BB+HBP)) - (2*K)) / IP + cFIP`, with `cFIP ≈ 3.10` (`CFIP_CONSTANT`,
    the league constant set so league FIP ≈ league ERA, ~3.05-3.20), regressed toward
    league-average FIP for low IP.
  - **Platoon regression at the correct level:** individual batter platoon talent needs
    ~1000+ PA and is regressed hard to a league platoon coefficient. **Team** split numbers
    are confounded by lineup composition and opponent quality, so they are **discounted**
    (weak evidence), never taken as talent. Multi-year preferred.
  - Recent form (`lastXGames`) is a small, heavily-regressed nudge, treated as noise unless it
    demonstrably beats a talent-only baseline out-of-sample (v3 gate). Never a driver.
  - Net out double-counting: apply only the delta vs neutral for park/platoon, since team run
    environments already bake some in.

### `model`
- **Responsibility:** the raw single-game home win probability via expected-runs -> a
  high-variance run-difference map, plus a transform sanity cross-check.
- **Outputs:** `ModelPrediction.raw_win_prob` + diagnostic expected runs + a cross-check
  probability + a divergence flag.
- **Key decisions:**
  - `runs.py`: estimate `lambda_home`, `lambda_away` expected runs for **this** game: team
    offense (vs-LHP/RHP split, regressed/discounted) vs the opposing starter's **regressed
    FIP weighted at a per-game-estimated innings share** (not a flat 55%), plus a league/team
    bullpen rate for the remaining innings; park (index/100, roof-gated) and platoon folded in
    at the **rate level** via the odds-ratio / Tango method
    `R = (B*P/L) / (B*P/L + (1-B)*(1-P)/(1-L))`. **Home-field advantage is derived once from
    data and applied inside the run model as a small run nudge (`HFA_RUNS`), not as a flat
    probability add.** Modern MLB HFA is **~.530-.534** (2020s decade = .534, the lowest of
    any Live-Ball decade; corrected from the draft's implied ~58%). For evenly matched teams
    the canonical Elo HFA constant is **24 rating points → P(home)=.5345** — the standard Elo
    model already agrees with ~.534. (The prior draft's "Elo HFA of 55 ≈ .578" is a strawman:
    no standard MLB Elo uses 55.) `.534 = +3.4pp`, so `HFA_RUNS` is sized to ~+3 to +3.5pp on
    an even matchup, not +4pp.
  - `winprob.py` — **v1 engine: deterministic closed-form over-dispersed run-differential map
    (replaces the 10k-draw Monte Carlo).**
    `P(home win) = Phi((lambda_home - lambda_away) / SD_diff)`, with **`SD_diff ≈ 4.3`**
    (`SD_DIFF` config). This is the right engine for v1 moneyline for four reasons:
    1. **Near the coin-flip region, only `E[run diff]` and `SD[run diff]` matter;** the higher
       moments of the run distribution barely touch `P(home > away)`. So one transparent,
       published parameter governs the output.
    2. **`SD_diff ≈ 4.3` is doubly anchored:** (a) empirical over-dispersion variance/mean ≈
       2.0-2.2 with `lambda_home + lambda_away ≈ 8.8` gives `var_diff ≈ 18.5 → SD ≈ 4.3`;
       (b) the realized average margin of victory ~3.285 runs implies `SD = 3.285/0.798 ≈
       4.1`. The constant is pinned by the `+0.5-run -> ~55%` golden test
       (`Phi(0.5/4.3) = 54.6%`).
    3. **Deterministic — no RNG, no seed, no per-run sim state.** This is strictly better than
       a 10k-sim Monte Carlo, which adds ~`sqrt(p(1-p)/10000) ≈ 0.5pp` of avoidable sampling
       noise per game and would have to be seeded/managed across **two** daily runs.
    4. **Clear bug-prevention narrative:** reaching 0.81 demonstrably requires a **~3.8-run**
       expected edge (`Phi^-1(0.81)*4.3 = 3.77`), which regressed inputs make impossible.
    Ties / continuity: real games never tie (extra innings resolve them), and the continuous
    map already handles the near-tie mass symmetrically; the residual extra-innings
    correction is sub-0.1pp. The `EXTRA_INNINGS_HOME_WINRATE` constant is retained for the
    discrete engine (below) and is set to **~0.49** (see §5; the prior 0.53 was refuted).
    - **`SD_diff` corrects a dangerous draft error.** The original "variance/mean ~1.3-1.5 per
      game" is **wrong**: the published per-team runs/game variance-to-mean ratio is **~2.0-2.2**
      (1981-96: 4.456/9.360 = 2.10; AL 2008-13: 4.500/9.999 = 2.22; NL: 4.258/9.139 = 2.15).
      The ~1.1 figure that was likely misremembered is the Tango/Dolinar **`B` over-dispersion
      add-on** (`B = VMR − 1 ≈ 1.1`), not the VMR. Using 1.3-1.5 makes the run distribution
      ~3× too tight (implied shape `r ≈ 11` vs the true `r ≈ 3.7-4.1`), which **inflates**
      single-game separation — the exact mechanism behind the 81% bug — and would slip past the
      `+0.5-run` test (insensitive near a half-run edge).
    - **Skellam/Poisson** closed form (`var_diff = lambda_h + lambda_a ≈ 8.8`, SD ≈ 3.0) is
      retained **only as a fast unit-test oracle**; it is too confident in the tail and is not
      on the live path.
    - **Full negative-binomial run distribution is deferred to v4** (totals/props), computed by
      an **exact NB-difference convolution** (deterministic — *not* Monte Carlo), parameterized
      with VMR ≈ 2.0-2.2 (`variance = lambda + lambda^2/r`, `r ≈ 3.7-4.1`). There the
      distribution *shape* drives the price, so the full distribution earns its keep; for the
      v1 moneyline it does not.
  - **Cross-check (not independent):** PythagenPat (`x = RPG^0.287`) -> log5, with the same
    data-derived HFA, runs in parallel as a **sanity check on the run-to-winprob transform,
    NOT an independent estimator** (it consumes the same regressed inputs). A >~5pp divergence
    raises an investigative flag only. A **genuinely independent** team-Elo estimator (a
    different data lineage — game results, not box-score peripherals, with ~.534 HFA and a
    light starter adjustment) is **promoted to v2** to give the divergence guard a real second
    opinion, replacing the circular PythagenPat check.

### `calibrate` (the centerpiece — pure, per-game)
- **Responsibility:** convert raw model output + market odds into a guarded, market-anchored
  final probability and a vetted divergence decision. **All guards fire on diagnostic raw
  quantities first.** (Offline batch metrics live in `validation/`.)
- **Outputs:** fair consensus market prob, calibrated final prob, displayed divergence, and a
  `Divergence | None` with explicit suppression reasons.
- **Key decisions / modules:**
  - `devig.py`: per-book **multiplicative** de-vig (`fair_i = implied_i / sum(implied)`), then
    **median** across books for the consensus. Multiplicative is **pinned as the principled
    default** (Berkowitz, Depken & Gandar 2018: in MLB moneylines it performs as well as Shin
    with no economically meaningful favorite-longshot bias to correct). It is **NOT** chosen by
    an offline calibration selector — in MLB the methods are statistically indistinguishable,
    so a selector would fit noise and flip season to season. For 2-way markets **Shin ==
    additive** (verified to machine precision); `additive(=Shin)` is computed alongside
    multiplicative **only** to drive the de-vig-method-fragility guard (Layer 4b). `power` is
    kept offline-only as a diagnostic (it over-corrects an FLB MLB does not have). Anchor is
    explicitly **soft-US** for the consensus, with **Pinnacle (eu)** as the separate sharp
    reference.
  - `shrink.py`: `p_final = w*p_model_raw + (1-w)*p_market_fair`. `w` seeded at a conservative
    default (`SHRINK_W = 0.35`, provisional) and **pinned near 0** until validation shows the
    model component beats market-only out-of-sample (fit deferred to v3).
  - `guards.py` (the layered stack, §6): raw-OOD band, raw-divergence guard, no-market guard,
    de-vig-method-fragility guard, clamp, edge floor, max-bets alarm. Every guard records a
    suppression reason into the snapshot.
  - `edge.py`: displayed divergence `= p_final - p_market_fair = w*(p_model_raw -
    p_market_fair)` (the identity holds because the shrink weights form a convex combination).
    EV and quarter-Kelly stake are shown for *display context only*, hard-capped at ~1-2%
    bankroll, and labeled non-advice.

### `validation` (offline/batch — needs graded data; mostly v3)
- **Responsibility:** everything that needs graded outcomes or the whole history. Kept out of
  per-game `calibrate`.
- **v1 contents (ship now):** Brier / log-loss / ECE accumulation; the snapshot grading hook;
  a **point-estimate** incremental log-loss of the model component vs a market-only baseline,
  displayed with an "insufficient data / not yet significant" caveat.
- **v3 contents (deferred until graded data exists):** the **bootstrap/paired significance
  test** on incremental log-loss with auto `w -> 0`; **selection-aware (empirical-Bayes /
  James-Stein) shrinkage** of chosen daily divergences; the de-vig-calibration **monitor**
  (flags mis-calibration; does **not** select the method); the **walk-forward, strictly
  chronological backtest harness**; and CLV computed against the **sharpest available close**
  (Pinnacle eu). These run on outcomes that do not exist for ~1-2 seasons, so they are not
  carried as untested code through years of API drift; the snapshot schema is kept rich now so
  nothing is lost.

### `render`
- **Responsibility:** one dark static `index.html` from a typed context, with a first-class
  honest empty state and a model-health status line.
- **Key decisions:** Jinja2, no SSG framework. **Headline banner:** the falsifiable question
  *"Does a free-data model beat the market?"* and its current answer (incremental log-loss vs
  market, with significance once available; "not yet" otherwise). Surfaced games are labeled
  **"model-vs-market divergence"** with a divergence percentage and a running CLV record —
  **not** "+X% edge / best bet." Empty state ("No qualifying divergences today") is a designed
  view. Status line surfaces: credits remaining, rolling incremental log-loss vs market,
  Brier/ECE, the CLV scoreboard, and a **freshness stamp** (`data as of <generated_at> UTC`,
  plus which slate bucket) so a dropped/late run is visibly stale, not silently missing.
  Framed as analytical content, NOT betting advice.

### `pipeline` + automation
- **Responsibility:** orchestrate each run, automate it, persist the audit/backtest dataset,
  keep the repo alive.
- **Key decisions:** `pipeline.py` is a linear, **bucket-agnostic** orchestrator: `ingest ->
  transform -> model -> calibrate -> render`, parameterized by the slate window it is given
  (§8). Every run commits an inputs+outputs JSON snapshot that triples as audit trail,
  walk-forward backtest dataset, and inactivity keepalive.

---

## 4. Data flow (one prediction run)

A run is invoked for a **slate window** `[now + safety_margin, end_of_slate]` (which bucket
fired is read from `github.event.schedule`; §8). The pipeline is identical for both buckets.

1. `ingest/mlb_statsapi`: `schedule?sportId=1&date=TODAY&hydrate=probablePitcher,venue,team`
   -> `gamePks`, probable-pitcher ids (read from `teams.home/away.probablePitcher`), venues.
   **Filter `gameType == "R"`.** Keep only games whose `commence_time` is in the window.
2. For posted games, `boxscore?hydrate=person` -> batting order + handedness (`batSide` for
   hitters, `pitchHand` for the starter). If a lineup is empty (early bucket / not yet posted),
   fall back to probable-pitcher-only features and mark the divergence **provisional**.
3. Per probable pitcher: `people/{id}/stats?stats=sabermetrics&group=pitching` reads `fip`
   (handle empty splits; min-IP gated; regressed manual-FIP fallback with `cFIP ≈ 3.10`
   otherwise); standard stats give K/9, BB/9; `statSplits&sitCodes=vl,vr` give vs-LHB/RHB.
4. Per team: `statSplits&sitCodes=vl,vr` (discounted), `lastXGames` (regressed form nudge).
5. `ingest/odds_api`: ONE `.../odds?regions=us&markets=h2h&commenceTimeFrom=<window>` call
   (**1 credit**) for the in-window slate; quota headers logged. **Not cached.**
6. `inputs/park_factors.csv` + optional weather (`/v1/forecast`, roof-gated) + optional
   `inputs/umpires.csv` loaded.
7. All raw payloads parse into frozen pydantic models (parse failures localized per game).
8. `transform`: regress FIP by IP (min-IP gated), regress/discount platoon, build lineup
   handedness profile, compute a small form nudge.
9. `model`: estimate `lambda_home/lambda_away`, apply the **closed-form `Phi` map** to get
   `raw_win_prob`; PythagenPat+log5 sanity cross-check; record divergence flag.
10. `calibrate` (guards in §6 order): **(a) raw-OOD band** — `raw_win_prob` outside
    `PROB_OOD_BAND` => suppress + alarm at source (a soft flag outside `PROB_OOD_SOFT_BAND` is
    logged, not suppressed); **(b) no-market guard** — fewer than `MIN_BOOKS` usable two-way
    prices, or odds call failed/401/quota-zero => suppress to NONE (never model-only); **(c)
    de-vig** each book multiplicatively, take the median consensus, compute `additive(=Shin)`
    alongside; **(d) raw-divergence guard** — `|raw_win_prob - p_market_fair| >
    MAX_RAW_DIVERGENCE` => suppress + "probable model error" alarm; **(e) de-vig-method
    fragility** — `|fair_mult - fair_additive| > DEVIG_METHOD_FRAGILE_TOL` => flag fragile and
    raise the required floor / suppress; **(f) shrink** toward market (`w`); **(g) clamp** to
    `PROB_CLAMP`; **(h) edge floor** — emit only displayed divergence `>= EDGE_FLOOR`; **(i)
    max-bets** — if more than `MAX_BETS_PER_DAY` survive, publish NONE + calibration alarm.
    (Selection-aware shrinkage is a v3 addition between (h) and (i).)
11. Survivors become `Divergence`s. **All suppressed and sub-floor candidates are recorded in
    the snapshot for counterfactual grading.**
12. `render` writes `site/index.html` (honest empty state if none) with the health/freshness
    line and the merged set of currently-upcoming divergences.
13. `pipeline` commits `data/YYYY-MM-DD.json` (slate-bucket-tagged inputs + model probs +
    de-vigged market + odds-at-prediction + suppressed candidates + placeholders for outcome
    and closing line); official Pages actions deploy the site. **Two prediction runs/day merge
    into the same dated snapshot rather than clobber it** (fetch+rebase+retry).
14. **Closing-line capture** (separate, staggered — §8) records the per-game closing line
    (us + eu/Pinnacle).
15. **Grading run** (next morning — §8) reads final scores and writes win/loss + closing-line
    CLV into prior snapshots, moving them to the `graded` state.

---

## 5. Modeling approach

**Primary engine (v1): expected-runs -> deterministic over-dispersed run-differential map.**

For each game, estimate each team's expected runs `lambda` for *this* game from free MLB Stats
API data:

- Team offense (vs-LHP/RHP split, regressed/discounted) against the opposing starter's
  **regressed FIP**, weighted by a **per-game-estimated innings share** (from his recent
  IP/start distribution and the team's bullpen usage), with the remaining innings on a
  league/team bullpen rate. The flat "55%" of the original draft is replaced by this bounded,
  tested per-game estimate.
- Park factor (index/100, roof-gated) and platoon/handedness folded in **at the rate level**
  via the odds-ratio / Tango method.
- Home-field advantage derived **once from data** (~.534 empirical; canonical Elo HFA = 24
  points → .5345) and applied **inside the run model** as `HFA_RUNS` (~+3 to +3.5pp on an even
  matchup), not bolted on as a flat probability add.

Convert to a home-win probability with the closed form:

```
P(home win) = Phi( (lambda_home - lambda_away) / SD_diff ),   SD_diff ≈ 4.3
```

**Why this family and this engine.** Baseball is the least single-game-predictable major sport
(the better team wins a single regular-season game only ~54% of the time), so a ~0.5-run
pregame edge is only **~55%** to win — confirmed three independent ways: exact NB convolution
(54.7-55.8% across VMR 1.3-2.1), Pythagorean with the empirical exponent 1.82 (55.0%), and the
linear runs-to-wins regression `Wpct = 0.49999 + 0.000609*RD` (54.9% for a 0.5 R/G edge). The
closed-form `Phi` map bakes that variance directly into the output through a single published
parameter, is fully deterministic (ideal for two daily runs), and makes the bug structurally
impossible (0.81 needs a ~3.8-run edge). The reviewers' objection to the original
"variance-inflation factor on a Skellam CDF" is resolved honestly: the inflation **is** the
empirical over-dispersion (VMR ≈ 2.1 ⇒ `SD_diff ≈ 4.3`), a published and testable quantity,
not a magic knob — and it is stated as one number rather than hidden in a simulation.

**This is a market-anchored system with a small model nudge (made explicit).** With `w` pinned
near 0 for 1-2 seasons (no historical-odds backtest exists), the engine choice is second-order:
every candidate engine produces "market ± a tiny nudge." The governing selection criteria are
therefore **calibration-safety, determinism, and maintainability for a solo owner** — which is
exactly why the closed form beats the Monte Carlo here. The full NB distribution is held in
reserve for v4 totals/props, where the distribution shape actually drives the answer.

**Cross-check (not independent):** PythagenPat -> log5 with the same data-derived HFA, run in
parallel as a sanity check on the transform only; divergence > ~5pp raises an investigative
flag. A genuinely independent team-Elo estimator is promoted to **v2**.

**Extra innings / ties.** In the discrete engine (v4 NB convolution), tie outcomes (the
diagonal) go to the home team at `EXTRA_INNINGS_HOME_WINRATE ≈ 0.49`. **Corrected from the
draft's 0.53:** under the post-2020 automatic-runner ("ghost runner") rule — the era we operate
in — home teams won only **~49.3%** of extra-inning games (2020-2024; FOX raw records: visitors
477-465 = home .494). The 0.53 figure was a conflation with the all-games HFA (~.534). Using
0.53 added a systematic ~+0.3-0.5pp upward home bias on every tie — the exact compounding
over-confidence the project exists to prevent. In the v1 closed-form engine there is no
discrete tie atom, so this correction is sub-0.1pp there but is pinned for the discrete path.

**Timing / slate scope (RESOLVED — owner chose BOTH afternoon + evening; see §8).** A single
fixed-UTC cron cannot run *after* lineups post and *before* first pitch across a ~12:35-22:10
ET slate. The owner's decision is implemented with **two scheduled prediction runs** plus a
bucket-agnostic, `commence_time`-filtered pipeline (full details in §8). The original
"evening-only" scope is removed everywhere.

**Rejected:** any direct FIP/rate -> win-prob map (the original bug); a 10k-draw Monte Carlo
(non-deterministic, ~0.5pp sampling noise, RNG state to manage across two runs, built on a
wrong dispersion number); a fixed-exponent Pythagorean reported as a single-game prob; the
"variance-inflation factor on a Skellam CDF" as a magic knob; a bolted-on flat "+4pp home"
(double-counts HFA, and .534 = +3.4pp); an Elo HFA of 55 (~58%, a strawman — the canonical
constant is 24 → .534); `variance/mean ~1.3-1.5` (refuted; true ~2.0-2.2); extra-innings home
rate 0.53 (refuted; ~0.49); choosing the de-vig method by an offline selector (the methods are
indistinguishable in MLB).

---

## 6. Calibration strategy (the layered, re-derived stack)

The re-derivation fixes the draft's self-defeating floor × shrinkage arithmetic and moves the
load-bearing guards onto the **diagnostic raw quantities**.

**Layer 0 — Input regression.** Regress FIP by IP (min-IP gated; manual-FIP fallback with
`cFIP ≈ 3.10`) and platoon at the correct level before they touch the model. Never feed raw
single-season rates.

**Layer 1 — Single-game variance (deterministic, correctly specified).** Always push expected
run differential through the closed-form `Phi((lambda_h - lambda_a)/SD_diff)` map with
`SD_diff ≈ 4.3`. Never a deterministic run-to-win map without variance. **Test:** a +0.5-run
pregame edge yields **~54-56%** (pinned as a band, not a point, since it is robust across the
dispersion range).

**Layer 2 — Raw-OOD band (source-level redundant catch).** Fires on the **raw model
probability** before any blending.

- **`PROB_OOD_BAND = [0.20, 0.80]` (hard suppress + calibration alarm).** A calibrated model
  essentially never exceeds ~0.72-0.74, so 0.80 sits at the empirical *market* maximum and
  **never suppresses a legitimate model output**, while it **catches the historical 0.81 bug
  at source** (0.81 > 0.80), redundantly with the divergence guard.
- **`PROB_OOD_SOFT_BAND = [0.28, 0.72]` (non-suppressing investigative flag).** A raw prob
  outside this band (e.g. a genuine ace-vs-tanker read of 0.74-0.79) is logged and shown on the
  health line as "heavy-favorite read — verify vs market," **without** suppressing it — this is
  exactly "flag, don't suppress legitimate heavy favorites." 0.72 is the true statistical
  model ceiling where genuine heavy favorites live.

**Layer 3 — Raw-divergence guard (PRIMARY blowup catcher).** If `|raw_win_prob - p_market_fair|
> MAX_RAW_DIVERGENCE` (default **0.10**) the game is suppressed and flagged "probable model
error." This is the **primary** catcher of the bug class, operating on the raw divergence: the
Astros 81% vs 47% = **34pp** divergence dies here (34pp >> 10pp), redundantly with Layer 2.
(0.08 is a defensible tightening once validated, since a free-data model diverging >8pp from an
efficient market is almost always error; 0.10 is kept as the default because it preserves the
documented emit window, Layer 7.)

**Layer 4 — No-market guard.** No usable de-vigged market (odds missing, 401/403, quota zero,
or fewer than `MIN_BOOKS` two-way prices) => suppress to NONE. **Model-only emission is never
allowed** — that is the unanchored 81% mode. Unit- and golden-tested.

**Layer 4b — De-vig-method fragility (NEW).** Compute `additive(=Shin)` alongside the
multiplicative consensus. The methods agree to <0.02pp on near-pick'em lines but diverge up to
~1.0-1.2pp on heavy favorites — *the same magnitude as the divergences AlgoBall measures*. If
`|fair_mult - fair_additive| > DEVIG_METHOD_FRAGILE_TOL` (~0.005, which triggers around lines
steeper than ~-180 / implied favorite >~63%), flag the game "de-vig-method-fragile" and either
suppress or raise its required floor by the divergence. This makes de-vig uncertainty an
explicit, bounded source of doubt exactly in the lopsided-favorite regime where the original
bug lived.

**Layer 5 — Shrink-to-market.** `p_final = w*p_model_raw + (1-w)*p_market_fair`. Seed
`SHRINK_W = 0.35` (provisional), **pinned near 0** until the model component beats market-only
out-of-sample (v3 metric). The seed and floor are derived **jointly** (Layer 7) so the emit
window is reachable by *plausible* edges.

**Layer 6 — Final-probability clamp.** Clamp `p_final` to `PROB_CLAMP = [0.15, 0.85]`. This
fires on the **market-anchored blend** (distinct from the raw-model band of Layer 2): with `w`
near 0, a model correctly agreeing with an extreme ~0.80 market blends to ~0.80, comfortably
under 0.85, so the clamp **does not clip a legitimate market anchor** (the reason it stays at
0.85 and is **not** tightened to 0.75 — and 0.75 would clip FiveThirtyEight's own 0.742 model
max). CI fails if any produced probability is outside the clamp.

**Layer 7 — Edge floor (derived jointly with `w`).** Emit only displayed divergence
`= w*(p_model_raw - p_market_fair) >= EDGE_FLOOR`. With `EDGE_FLOOR = 0.015` and seed `w =
0.35`, the implied **raw-divergence floor is 0.015/0.35 = 0.042857 ≈ 0.043 (4.3pp)** — a
*plausible genuine edge*, not a 20pp blowup. Combined with the Layer-3 cap at 0.10, the **emit
window is raw divergence in ~[4.3pp, 10pp]** and **displayed divergence in [1.5%, 3.5%]**
(lower bound = `EDGE_FLOOR` exactly; upper bound = `w*MAX_RAW_DIVERGENCE = 0.35*0.10 = 0.035`).
A +34pp divergence is structurally barred at Layer 3. If `w` is re-fit, the floor is re-derived
so the window stays reachable. (The old standalone 6% floor / 33.3pp ceiling are retired.)

**Layer 8 — Max-bets sanity.** If more than `MAX_BETS_PER_DAY` (default **3**) survive,
**publish NONE and raise a calibration alarm** (19 bets/day was itself the alarm). *In v3*, a
selection-aware (empirical-Bayes / James-Stein) shrinkage of the surviving divergences is
inserted **before** this check to correct winner's/optimizer's curse; note it sits *after* the
Layer-7 floor gate, so once enabled it can shrink a displayed divergence below 3.5% and even
below the 1.5% floor. It is deferred because it needs graded data to size and adds no value at
`w ≈ 0`.

**Layer 9 — Validation (model-aware, see §7-8).** The primary fast metric is the **model
component's incremental OOS log-loss vs market-only on ALL games**. *v1* computes the point
estimate (caveated as not-yet-significant); *v3* adds the bootstrap/paired significance test
and drives `w -> 0` automatically if it is not positive. **All suppressed (Layers 2/3) and
sub-floor (Layer 7) candidates are counterfactually graded** so the guards are *investigative
alarms*, not silent error-laundering filters. CLV against the **sharpest available close
(Pinnacle eu)** is the slower confirmatory signal.

### Calibration golden/regression tests (the centerpiece)

- **Astros grid, not a single point.** Replay the historical input and a grid of raw probs
  `{0.81, 0.78, 0.75, 0.73}` × market `{0.47, 0.50, 0.55}` and assert **0 divergences for
  all**. Under Layers 2-3 they all suppress (each exceeds `MAX_RAW_DIVERGENCE` and/or the OOD
  band). **Removing any single guard must not change a suppression decision** — a test asserts
  this directly.
- **Safety-band discrimination (NEW).** Assert a **raw model 0.81 trips the OOD hard band**
  (0.81 > 0.80) while a **de-vigged market of 0.82 is NOT clamped away** (the clamp fires on
  the blend, not the market). Assert a raw model 0.74 trips only the **soft** flag (no
  suppression).
- **Features-level regression.** Feed realistic raw `PitcherFeatures`/`TeamFeatures` through
  `transform -> model -> calibrate` and assert `raw_win_prob < ~0.75` and 0 divergences — the
  test exercises the engine that *produced* the bug, not just an injected scalar.
- **Synthetic ace-vs-replacement** (hand-checked): asserts the model needs a physically absurd
  run edge to approach 0.80; a realistic extreme stays well under it.
- **+0.5-run edge -> ~54-56%** pins `SD_diff` (and the realized-avg-MOV anchor pins it again).
- **De-vig invariants:** two-way sums to 1.0; `-110/-110 -> 50/50`; `fair_i < raw_implied_i`
  both sides; **Shin == additive for 2-way** (machine precision); edge computed against fair
  consensus, never raw implied, never `1 - opponent_raw`.
- **De-vig-method fragility** test: a -300/+235 line flags fragile; a -110/-105 line does not.
- **No-market -> NONE** (never model-only).
- **Emit-window mapping** test (Layer 7): `EDGE_FLOOR/w ≈ 0.043` and `w*MAX_RAW_DIVERGENCE =
  0.035`.
- **Never-publish-started-games** render guard: any game with `commence_time <= now + margin`
  is excluded (independent of the odds-API commence filter).
- **CI fails** on any produced probability outside `PROB_CLAMP`.

---

## 7. Testing strategy

Three tiers, all runnable offline with zero API quota.

1. **Pure-function unit tests (math):** de-vig (multiplicative / additive(=Shin) / power, with
   the invariants above and the Shin==additive equivalence), FIP regression + min-IP gate +
   manual-FIP fallback, odds-ratio matchup, the closed-form win-prob map and the **+0.5-run ->
   ~54-56%** pin (fully deterministic — no RNG), PythagenPat/log5 cross-check, EV/Kelly,
   Brier/log-loss/ECE, incremental-log-loss-vs-market point estimate. Each with hand-computed
   expected values. **Core math tests are backed by committed, hand-trimmed static JSON
   fixtures**, so the crown-jewel golden suite never depends on cassette machinery.

2. **API tests via static fixtures + vcrpy:** keep a small set of **committed static JSON
   fixtures** (real, hand-trimmed payloads) for boundary-parse and graceful-degradation tests;
   keep **vcrpy cassettes** only for the boundary-parse / degradation path (scrub `apiKey` via
   `filter_query_parameters=['apiKey']`), replayed in CI with no key/quota. Assert the pydantic
   boundary parses real payloads and **degrades gracefully** on missing fields (empty
   `battingOrder`, absent/empty/low-IP FIP, missing book, null `probablePitcher`,
   non-regular-season `gameType`). An occasional **quota-aware live smoke test**
   (`workflow_dispatch`) catches cassette/fixture rot when statsapi silently drifts.

3. **Calibration golden/regression tests:** the full §6 suite (Astros grid, safety-band
   discrimination, features-level regression, ace-vs-replacement, +0.5-run, de-vig invariants
   + fragility, no-market, emit-window mapping, never-publish-started-games, clamp-in-CI, and
   the **joint contextual-signal bound** below).

**Joint contextual-signal property test.** The real failure mode is *aligned* signals
(lefty-heavy lineup + hitters' park + weak-platoon pitcher + tired pen) multiplying through the
odds-ratio chain. Test: with **all** contextual signals pushed to plausible same-direction
extremes **simultaneously**, total win-prob movement must stay under a small bound (e.g.
**6-8pp**) and must not by itself clear the emit floor.

**Backtesting** (v3) is walk-forward and strictly chronological (train past, evaluate future,
use odds available at prediction time, reserve the close only for CLV). It requires ~300-500+
graded results across multiple seasons before any edge is trusted; a backtest ROI above
~15-20% is treated as a **leakage/overfitting red flag**, not a success. Because graded samples
accrue slowly, **full-slate probability calibration and the incremental-log-loss-vs-market
metric are the primary, fast feedback** (available in weeks); CLV is the slow confirmatory
signal.

---

## 8. Deployment / automation (two-run afternoon + evening coverage)

Three small GitHub Actions workflows. GitHub Actions + Pages are **unlimited-free only for
PUBLIC repos** — so the code, picks, and `data/` snapshots are world-readable; secret hygiene
(below) is therefore non-negotiable. All publishing workflows use the official
`configure-pages` / `upload-pages-artifact` / `deploy-pages` chain, `permissions: contents:
write, pages: write, id-token: write`, `concurrency: pages, cancel-in-progress: false`, and
`ODDS_API_KEY` from Actions secrets (masked, never committed). **Pin the toolchain:**
`astral-sh/setup-uv` with an explicit uv version, committed `uv.lock` and `.python-version`;
`pip` + a pinned `requirements.txt` documented as the durable fallback (uv is Production/Stable
but pre-1.0).

### `predict.yml` — TWO scheduled prediction runs (afternoon + evening)

One workflow with **two `schedule:` cron entries** plus `workflow_dispatch` (the owner's
button). Branch on `github.event.schedule`; the pipeline is otherwise **bucket-agnostic**.

- **Afternoon run ~15:00 UTC (11:00 ET).** After typical afternoon-game lineup posting (~2-3h
  before first pitch), before afternoon first pitches (~12:35-13:10 ET). Predicts afternoon
  games on posted lineups; evening games are predicted **provisionally** (probable-pitcher
  only — a supported fallback) so the page is never empty mid-day.
- **Evening run ~21:00 UTC (17:00 ET).** After evening lineup posting, before evening first
  pitches. **Re-predicts all still-upcoming games**, upgrading evening picks from provisional
  to lineup-based, and naturally excludes afternoon games that have already started.

**Bucket-agnostic window logic (the core of the design).** Each run computes `now_utc` and
processes every game with `commence_time` in `[now + slate_safety_margin, end_of_slate]`,
using `commenceTimeFrom` on the `/odds` call (a **free** filter). An **independent render-layer
guard** drops any game with `commence_time <= now + margin`, so a late/delayed cron can **never
publish an in-progress game** even if the odds filter is bypassed. This single code path serves
both crons and is robust to GitHub's routine 10-30 min cron delay and drift. The earliest
12:35 ET getaway games may occasionally precede the 11:00 ET run's lineup posting; those fall
back to probable-pitcher-only + "provisional" — **no third early cron** is added for a handful
of getaway-day games.

Both runs write the **same** `data/YYYY-MM-DD.json` (with a per-game `slate_bucket` tag),
merging rather than clobbering via `git fetch && git rebase` + retry. `index.html` is rendered
each run from the merged set of currently-upcoming divergences, with the freshness stamp +
bucket exposing any missed/late run.

Steps each run: `checkout` -> `setup-uv` (pinned) + Python -> `uv sync` -> `uv run python -m
algoball --window <bucket>` (env `ODDS_API_KEY`) -> fetch/rebase commit -> Pages deploy.
**1 Odds credit per prediction run.**

### `close.yml` — staggered per-game closing capture (us + eu/Pinnacle)

Several light, staggered runs across the day snapshot the slate's `h2h` line, selecting the
**latest pre-`commence_time` price per game** so CLV is keyed to each game's own first pitch.
Staggered to bracket the two first-pitch clusters (afternoon ~12:30 ET; early evening ~18:30
ET; late/West-Coast ~20:30 and ~22:00 ET). To anchor CLV to the **sharpest** line, the close
poll fetches **`regions=us,eu`** (Pinnacle) — **this costs 2 credits per call** (1 market × 2
regions), corrected from the prior draft's "still 1 credit." Pinnacle on the free tier may be
slightly delayed, so the captured "sharp close" can be a few minutes stale — labeled as such.

### `grade.yml` — next-morning grading + keepalive + failure notify (REQUIRED)

Reads statsapi final scores for unresolved past `gamePks`, writes win/loss + closing-line CLV
into those snapshots (-> `graded`), and recomputes the rolling validation metrics for the
health line. An `if: always()` step makes a **trivial keepalive commit** (a heartbeat file)
**even on a failed/empty run**, so sustained failures still reset GitHub's 60-day inactivity
timer (research confirms only *new commits* reset it; a failing run otherwise commits nothing).
The keepalive is verified, with a documented fallback (a separate trivial scheduled commit, or
accepted manual re-enable) if bot commits prove not to reset the timer.

### Quota budget (two prediction runs, verified credit model)

`cost = markets × regions` per `/odds` call; empty windows cost 0; the free tier is 500
credits/month (reset on the 1st). A second prediction run therefore adds only **+1 credit/day**,
not a doubling.

| Item | Calls/day | Credits each | Credits/day |
|---|---|---|---|
| Afternoon predict (us, h2h) | 1 | 1 | 1 |
| Evening predict (us, h2h) | 1 | 1 | 1 |
| Optional early odds-only snapshot per slate (us, for open→close CLV) | 2 | 1 | 2 |
| Staggered closes (us + eu = 2 regions) | 3-4 | 2 | 6-8 |
| **Total** | | | **~10-12/day ≈ 300-360/month** |

Comfortably under 500 with headroom. If quota tightens, drop the `eu` region from closes
(halves close cost) or the early snapshots first. `x-requests-remaining` is logged every run;
the run fails soft near zero.

**Failure handling for a non-technical owner (v1, required).** Every workflow has an
`if: failure()` step that **opens/updates a GitHub issue and emails the owner** with a one-line
cause. `README.md` contains a numbered, screenshot-level **recovery runbook** ("it went red —
here's exactly what to click"). The owner's primary interface is the **"Run workflow" button**;
a one-time setup checklist covers: add the `ODDS_API_KEY` Actions secret, enable Actions, set
Pages source to "GitHub Actions," confirm `workflow_dispatch` is enabled.

**Secret hygiene (procedural must-fix).** A live-key `.env` sits in this not-yet-git directory.
**Before** `git init`/`git add`, commit a `.gitignore` containing `.env`, `.cache/`, `*.sqlite`
so the key can never land in the first commit. `ODDS_API_KEY` is a `SecretStr`; the blank
`.env.example` is the only env file committed. Because the repo is public, double down on this.

---

## 9. Tech stack

- **Python 3.12** (committed `.python-version`)
- **uv** (env + deps; single `pyproject.toml`; `hatchling`; `src` layout) — **version pinned**
  in CI; `uv.lock` committed; `pip` + pinned `requirements.txt` documented as fallback
- **ruff** (lint + format)
- **pydantic v2 + pydantic-settings** (frozen boundary *and* internal models; `SecretStr`;
  typed calibration constants) — **one** type system, no dataclass mirror
- **requests** (**no caching** — the SQLite/`requests-cache` layer is dropped from v1: in a
  fresh once/twice-daily CI runner it is git-ignored and empty, saves no quota, and adds a
  `*.sqlite` hygiene footgun; reintroduce only via `actions/cache` if a concrete need appears)
- **tenacity** (retry timeouts/5xx only, never 4xx; explicit timeouts)
- **numpy + scipy.stats** (the closed-form `Phi` map via `scipy.stats.norm`; `skellam`/`nbinom`
  kept as **test oracles** only in v1; `nbinom` convolution becomes live in v4; hand-written
  de-vig/edge/metric functions)
- **Jinja2** (single dark `index.html`, no SSG framework)
- **pytest + static JSON fixtures + pytest-recording/vcrpy** (golden calibration tests; cassettes
  scoped to boundary-parse/degradation, `apiKey` scrubbed)
- **scikit-learn** (OPTIONAL, v3+: Platt/sigmoid while <~1000 graded games, isotonic only
  above)
- **GitHub Actions + GitHub Pages** (official deploy chain; **public repo**)
- **Free data:** MLB Stats API (no key; verified `probablePitcher` nested under `teams.*`,
  `gameType=='R'` filter, `boxscore?hydrate=person` -> `batSide`/`pitchHand` on every person,
  `sabermetrics` group -> `fip` incl. 2026 with empty-splits handling, `statSplits`,
  `lastXGames`), The Odds API (`ODDS_API_KEY`, free **500 credits/mo**, `cost = markets ×
  regions`, three `x-requests-*` headers, **Pinnacle via `eu`**), Open-Meteo (`/v1/forecast`,
  no key, roof-gated), hand-maintained park-factor + umpire CSVs.

---

## 10. Repository layout

```
algoball/
  pyproject.toml              # uv + ruff + pytest; src layout; hatchling
  uv.lock                     # committed (pinned, reproducible)
  .python-version             # committed (3.12)
  requirements.txt            # pinned pip fallback
  .gitignore                  # COMMIT FIRST: .env, .cache/, *.sqlite
  .env.example                # ODDS_API_KEY= (blank); real .env git-ignored
  README.md                   # honest measurement framing; "Run workflow" button first;
                              #   one-time setup; plain-English recovery runbook; public-repo note
  src/algoball/
    __init__.py
    __main__.py               # `uv run python -m algoball --window {afternoon|evening}`
    config.py                 # Settings, get_settings(), all calibration constants
    models.py                 # frozen pydantic boundary + internal models (one type system)
    pipeline.py               # bucket-agnostic orchestrator: ingest->transform->model->calibrate->render
    ingest/
      __init__.py
      odds_api.py             # h2h odds (not cached; commenceTimeFrom; us, +eu for closes), quota logging
      mlb_statsapi.py         # schedule(gameType=R), boxscore(hydrate=person), sabermetrics FIP, splits, lastXGames
      grade.py                # REQUIRED: final scores + closing CLV -> prior snapshots
      park_factors.py         # loads inputs/park_factors.csv (100-centered, handedness/roof)
      weather.py              # Open-Meteo /v1/forecast, roof-gated (v2 feature)
      umpires.py              # loads inputs/umpires.csv, absent-by-default
      parse.py                # named, tested extraction (FIP from sabermetrics, handedness, nested probables)
    transform/
      __init__.py
      features.py             # regressed FIP (+manual fallback), platoon (correct level), handedness, form nudge
    model/
      __init__.py
      runs.py                 # expected-runs (odds-ratio/Tango, park, per-game IP share, data HFA as runs)
      winprob.py              # closed-form Phi((lam_h-lam_a)/SD_diff); PythagenPat/log5 sanity; skellam/nbinom oracles
    calibrate/                # per-game, pure
      __init__.py
      devig.py                # multiplicative default + median consensus; additive(=Shin) for fragility guard
      shrink.py               # shrink-to-market (w seeded, pinned ~0)
      guards.py               # raw-OOD band+soft, raw-divergence, no-market, devig-fragility, clamp, floor, max-bets
      edge.py                 # displayed divergence + quarter-Kelly (display only, non-advice)
    validation/               # offline/batch; needs graded data
      __init__.py
      metrics.py              # Brier, log-loss, ECE, CLV (v1)
      incremental.py          # model-vs-market OOS log-loss point estimate (v1); bootstrap significance (v3)
      selection.py            # empirical-Bayes/James-Stein edge shrinkage (v3)
      anchor.py               # de-vig calibration MONITOR only (v3) -- does not select the method
      backtest.py             # walk-forward chronological harness (v3)
    render/
      __init__.py
      writer.py               # Jinja2 render to site/index.html (never-started-games guard)
      templates/index.html.j2 # dark theme, measurement headline, honest empty state, health + freshness + bucket
  inputs/                     # HUMAN-OWNED, hand-edited (kept away from generated data/)
    park_factors.csv
    umpires.csv               # optional stub
  data/                       # MACHINE-WRITTEN YYYY-MM-DD.json (slate-bucket-tagged; audit + backtest + keepalive)
  site/                       # build output: index.html (Pages artifact)
  tests/
    fixtures/                 # committed static JSON payloads (load-bearing math/parse tests)
    cassettes/                # vcrpy YAML, apiKey scrubbed (boundary-parse/degradation only)
    test_devig.py             # invariants + Shin==additive + fragility
    test_winprob.py           # closed-form determinism + +0.5-run -> ~54-56%
    test_calibration_golden.py# Astros grid -> 0; safety-band discrimination; features-level; no-market; emit-window
    test_signals_joint.py     # joint contextual-signal bound
    test_schedule_guard.py    # never-publish-started-games + window filtering
    test_metrics.py           # incremental-log-loss-vs-market point estimate
    test_ingest_vcr.py        # boundary parse + graceful degradation
  .github/workflows/
    predict.yml               # TWO crons (afternoon+evening) + workflow_dispatch + Pages deploy
    close.yml                 # staggered per-game closing capture (commence_time-keyed; us+eu)
    grade.yml                 # next-morning grading + keepalive(always) + failure notify(issue+email)
```

---

## 11. Risk register (with mitigations)

- **Calibration regression resurrects the +34% bug.** -> Dedicated pure-function module;
  **divergence guard (primary) + raw-OOD band (redundant, source-level)**; Astros *grid*
  golden test; safety-band discrimination test; features-level regression; "remove-any-single-
  guard must not change the decision" test; CI fail on any prob outside the clamp.
- **Over-confident output sliding under a cap.** -> Guards fire on raw probability and raw
  divergence *before* shrinkage; the raw-OOD hard band 0.80 sits below the 0.85 clamp so 0.81
  is caught at source, not one tick under the clamp.
- **Wrong dispersion makes the model over-confident (silently).** -> `SD_diff ≈ 4.3` from
  published VMR ≈ 2.0-2.2 (NOT 1.3-1.5); pinned by the +0.5-run band test *and* the avg-MOV
  anchor.
- **Self-defeating emit math.** -> Floor and `w` derived jointly; emit window mapped to
  plausible [4.3pp, 10pp] raw divergence / [1.5%, 3.5%] displayed and tested.
- **De-vig method artifact fabricates/erases a divergence on heavy favorites.** -> Layer-4b
  de-vig-method-fragility guard; multiplicative pinned on principle (not selector-chosen);
  Shin==additive invariant tested.
- **Validating the market copy, not the model.** -> Incremental OOS log-loss vs market-only on
  all games; `w -> 0` if not positive (significance test in v3).
- **Free-data model cannot beat the sharp close (honesty risk).** -> Measurement-first framing;
  divergences labeled, not "value bets"; Pinnacle (eu) sharp anchor; open→close + prediction→
  close CLV scoreboard as the falsification test.
- **Winner's/optimizer's curse on daily top-3.** -> Max-bets -> NONE alarm (v1); empirical-Bayes
  selection shrinkage (v3); counterfactual grading of suppressed/sub-floor candidates.
- **Open validation loop (no outcomes).** -> Required `grade.yml`; "graded" is a snapshot
  state; metric claims caveated until grading exists.
- **No-market unanchored fallback (the 81% mode).** -> No-market guard suppresses to NONE;
  401/quota-zero is fatal-for-bets, never degrade-to-model; golden-tested.
- **Two-run timing / publishing started games.** -> Two crons + bucket-agnostic
  `commence_time` window + **independent never-publish-started-games render guard** + test;
  evening run upgrades provisional afternoon picks; getaway-day games fall back to provisional.
- **Odds quota drained (esp. props).** -> us+h2h prediction (1/run) + staggered closes; second
  run adds only +1 credit/day; eu only on closes (2 credits, droppable); log remaining every
  run, fail soft; props gated and budgeted (roadmap v4).
- **MLB Stats API drift / absent or low-IP / empty FIP.** -> pydantic boundary + static
  fixtures localize blast radius; `sabermetrics.fip` with consumer-side min-IP gate + empty-
  splits handling + regressed manual-FIP fallback (`cFIP ≈ 3.10`); nested-probables /
  `gameType=='R'` / `hydrate=person` parse contract tested; occasional live smoke test.
- **Extra-innings tie bias.** -> `EXTRA_INNINGS_HOME_WINRATE ≈ 0.49` (ghost-runner era), pinned;
  revisited if the automatic-runner rule changes.
- **Backtest leakage/overfitting.** -> Walk-forward chronological, odds-at-prediction-time,
  close reserved for CLV, ~300-500+ graded results, >15-20% ROI treated as a red flag (v3).
- **Joint contextual signals manufacture fake separation.** -> Joint property test (<=6-8pp);
  platoon regressed at the correct level; form gated and required to beat talent-only OOS.
- **Umpire data has no honest free feed.** -> Absent-by-default hand-filled CSV, near-zero
  weight, labeled non-live; pipeline runs unchanged when missing.
- **Maintainability rot for a solo owner.** -> Drop requests-cache; defer the validation
  inference stack (James-Stein, bootstrap, anchor monitor, backtester) to v3; pin uv + commit
  uv.lock/.python-version + pip fallback; static fixtures over cassettes for core tests.
- **Operational: cron delay/drop, push collisions, silent dark site, public repo.** ->
  Freshness stamp + bucket on the page; fetch+rebase+retry on commits; failure issue+email +
  runbook (v1); keepalive on failure; secret hygiene before `git init`.
- **Secret leak via committed .env.** -> `.gitignore` committed before `git init`/`add`;
  `SecretStr`; only blank `.env.example` committed; public-repo caveat documented.

---

## 12. Value-vs-market verdict (honest)

Can free, public-input data beat the de-vigged closing line? **Essentially no — not the sharp
close.** Closing lines are among the most efficient prices in sports; AlgoBall deliberately
waits until lineups post (for handedness), which is precisely the hardest-to-beat moment, using
inputs already in the price. A model built from already-priced public signals has ~0 expected
edge over the de-vigged consensus at that time. The only realistic inefficiencies live in
**early/soft lines** before the market sharpens and in **soft US books lagging the sharp
consensus** — which is why the owner's two-run coverage is an asset: it lets a once/twice-daily
free tool capture an earlier (softer) line and measure **open→close** CLV (the only structural
path to *demonstrating* edge), in addition to prediction→close CLV.

The framing is therefore **measurement, not profit**: the homepage leads with the falsifiable
incremental-log-loss-vs-market question; surfaced games are **labeled divergences**, not value
bets; and a standing **CLV scoreboard** against the sharpest available close (Pinnacle eu) is
the falsification test. This converts the "can't beat the close" reality from a weakness into
credibility: AlgoBall is a transparent instrument that publicly tests, every day, whether a
free-data model tracks or diverges from the market — and says so plainly.
