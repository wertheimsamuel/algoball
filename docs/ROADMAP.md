# AlgoBall — Roadmap (docs/ROADMAP.md)

Four phases, v1 minimal-correct through v4 props. **The bug-prevention guard stack ships in
full in v1** — it is never deferred. The heavier *statistical-validation inference* machinery
(bootstrap significance, selection shrinkage, anchor-calibration monitor, walk-forward
backtester) is deferred to v3, because it runs on graded outcomes that do not exist for ~1-2
seasons and would otherwise rot silently through API drift. Each phase lists concrete
deliverables and explicit acceptance criteria. "Done" means the acceptance criteria pass in CI
(offline, zero API quota) where applicable.

> **Honest expectation, up front.** AlgoBall is a **measurement instrument**, not a profit
> tool. A free-data model run after lineups post **cannot be expected to beat the de-vigged
> sharp close** (§12 of ARCHITECTURE.md). For roughly the **first one to two seasons** the
> surfaced divergences are **empirically unvalidated** — forward-collected snapshots are the
> only backtest data (the Odds API historical endpoint is paid), and at 0-3 divergences/day it
> takes multiple seasons to accumulate the ~300-500 graded results needed to trust anything.
> During that window, **conservatism plus the calibration guards are the only safeguards**, and
> the fast feedback is full-slate probability calibration + the model-vs-market incremental
> log-loss metric, **not** emitted-bet ROI. 

> **Coverage decision (owner, firm): BOTH afternoon + evening games**, implemented from v1 via
> **two scheduled prediction runs** and a bucket-agnostic, `commence_time`-filtered pipeline.
> The original "evening-only" scope is removed everywhere.

---

## v1 — Minimal-correct (moneyline, FULL slate via two runs)

**Goal:** a correct, conservatively-calibrated, end-to-end pipeline that a human runs with one
button and that is **structurally incapable** of reproducing the +34% / 81% / 19-bets bug,
covering the full afternoon + evening slate. The complete guard stack ships now; outcome
grading and the snapshot schema ship now so data accrues from the first run.

**Deliverables**
- Secret hygiene first: commit `.gitignore` (`.env`, `.cache/`, `*.sqlite`) **before**
  `git init`/`git add`; `.env.example` blank; `ODDS_API_KEY` as `SecretStr` + Actions secret.
  README states the **public-repo** dependency and secret-hygiene rules explicitly.
- `uv`/`src` package skeleton; **pinned toolchain** (`setup-uv` with explicit version,
  committed `uv.lock` + `.python-version`, pip `requirements.txt` fallback); `config.py` with
  all calibration constants as typed fields; **one** frozen-pydantic type system (no dataclass
  mirror). **No requests-cache / SQLite** (dropped).
- `ingest`: Odds API `h2h` (us; **`commenceTimeFrom` window filter**; quota-header logging;
  **not cached**); MLB Stats API schedule (**`gameType=='R'` filter**; probables read from
  **`teams.home/away.probablePitcher`**, treated as optional/null before announcement) /
  `boxscore?hydrate=person` (**`batSide`/`pitchHand` on every person**; select by role) /
  `sabermetrics&group=pitching` FIP (**empty-splits handling**; consumer-side min-IP gate) /
  team splits; named tested `parse.py`.
- **`ingest/grade.py` + snapshot schema** with `predicted | closed | graded` states; a
  `grade.yml` morning job that writes final win/loss (and closing-line CLV) into prior
  snapshots.
- `transform`: regress FIP by IP (min-IP gate) with **manual-FIP fallback**
  `FIP = ((13*HR)+(3*(BB+HBP))-(2*K))/IP + cFIP`, `cFIP ≈ 3.10`; regress platoon at the correct
  level (individual->league coefficient; team splits discounted).
- `model`: expected-runs -> **deterministic closed-form win-prob**
  `P(home) = Phi((lambda_h - lambda_a)/SD_diff)`, **`SD_diff ≈ 4.3`** (from VMR ≈ 2.0-2.2 and
  avg MOV ~3.3; **NOT** the refuted 1.3-1.5); data-derived HFA applied as runs (~+3 to +3.5pp;
  Elo-equivalent 24 points → .534); `EXTRA_INNINGS_HOME_WINRATE ≈ 0.49` for the discrete oracle
  path; PythagenPat+log5 as a transform sanity cross-check (not "independent"); skellam/nbinom
  as test oracles only.
- `calibrate` (full guard stack): **multiplicative de-vig pinned on principle** + consensus
  **median**; `additive(=Shin)` computed alongside for the fragility guard; **raw-OOD band
  `[0.20, 0.80]` hard + `[0.28, 0.72]` soft flag**; **raw-divergence guard `0.10`**;
  **no-market guard -> NONE**; **de-vig-method-fragility guard**; shrink (seed `w=0.35`, pinned
  near 0); **clamp `[0.15, 0.85]`**; **jointly-derived edge floor (1.5%)**; **max-bets (3) ->
  NONE + alarm**. All suppressed/sub-floor candidates recorded in the snapshot.
- `validation/metrics.py`: Brier/log-loss/ECE accumulation; `incremental.py` **point-estimate**
  model-vs-market OOS log-loss (caveated "insufficient data / not yet significant"). The
  bootstrap significance test, James-Stein selection shrinkage, anchor monitor, and backtester
  are **v3** (interfaces stubbed; snapshot schema kept rich now).
- `render`: dark `index.html` with the **measurement headline** ("Does a free-data model beat
  the market? Current: not yet / insufficient data"), surfaced games labeled **"model-vs-market
  divergence"** (not "+X% edge"), honest empty state, health line (credits, incremental
  log-loss, Brier/ECE, CLV record), a **freshness stamp + slate bucket**, and the
  **never-publish-started-games** guard.
- **Automation in v1:** `predict.yml` with **two cron entries** (afternoon ~15:00 UTC, evening
  ~21:00 UTC) + `workflow_dispatch`; `grade.yml` morning grading + **keepalive on `always()`**
  + **failure notification (issue + email)**; fetch+rebase+retry on all committing jobs.
  (Closing-line capture / weather / contextual signals land in v2.)
- Coverage: **FULL slate** via the bucket-agnostic window pipeline; afternoon run predicts
  afternoon games on lineups and evening games provisionally; evening run upgrades them.
- Tests: de-vig invariants + **Shin==additive** + fragility; closed-form determinism + **+0.5-run
  -> ~54-56%**; **Astros grid {0.81,0.78,0.75,0.73} × {0.47,0.50,0.55} -> 0 divergences**;
  **safety-band discrimination (raw 0.81 trips OOD; market 0.82 not clamped; raw 0.74 soft-only)**;
  **features-level regression**; ace-vs-replacement; **no-market -> NONE**; emit-window mapping;
  **never-publish-started-games + window filtering**; remove-any-single-guard test; CI fail
  outside clamp.
- Manual run via `uv run python -m algoball --window {afternoon|evening}` (maintainer path).

**Acceptance criteria**
- `uv run python -m algoball` produces a valid `site/index.html` from committed
  fixtures/cassettes with **zero** network/quota.
- **Every** Astros-grid case yields **0 divergences**, removing any single guard does not flip a
  suppression decision, and the safety-band discrimination test passes (raw 0.81 suppressed at
  the OOD band; de-vigged market 0.82 not clamped away).
- Features-level regression keeps `raw_win_prob < ~0.75`; the +0.5-run test lands ~54-56%.
- No-market / 401 / quota-zero yields the honest empty state, **never** a model-only divergence.
- No produced probability is ever outside `[0.15, 0.85]` (CI gate).
- Displayed divergence on any surfaced game is within ~[1.5%, 3.5%]; no run surfaces more than 3.
- **Both crons run the same bucket-agnostic pipeline**; a late/delayed run never publishes a
  game with `commence_time <= now + margin` (tested); the two runs merge into one dated snapshot
  without clobbering.
- A run writes a `predicted` snapshot; the grading job moves a prior snapshot to `graded` with a
  correct win/loss read from statsapi.
- On a realistic full slate, the tool surfaces 0-3 divergences (often 0), across afternoon and
  evening games.

---

## v2 — Context signals + sharp anchor + full hands-off automation

**Goal:** add the defensible free contextual signals, the sharp (Pinnacle) anchor and CLV
capture, and a genuinely independent cross-check; make the tool fully hands-off and safe to
leave alone.

**Deliverables**
- Park factors (`inputs/park_factors.csv`, index/100, roof-gated) and platoon/handedness via the
  odds-ratio/Tango method at the rate level; **net out double-counting** vs team run
  environments.
- Lineup-handedness aggregation (lefty-heavy detection), with **provisional fallback** when
  lineups are unposted (reuses the v1 provisional path used by the afternoon run for evening
  games).
- Open-Meteo weather (**`/v1/forecast`**), hard-gated to open-air parks, applied as context, not
  as a moneyline driver.
- **Joint contextual-signal property test** (all signals same-direction extreme -> <=6-8pp,
  cannot clear the floor alone) wired into CI.
- **`close.yml`: staggered, `commence_time`-keyed** closing capture (latest pre-first-pitch price
  per game), bracketing both afternoon and evening first-pitch clusters, fetching **`regions=us,eu`
  (Pinnacle) at 2 credits/call** for the sharpest close (Pinnacle-delay caveat labeled). Quota
  budget documented and logged (~10-12 credits/day ≈ 300-360/month, under 500).
- **Genuinely independent team-Elo cross-check** (game-results lineage, ~.534 HFA, light starter
  adjustment) **replacing the circular PythagenPat check** as the divergence guard's second
  opinion.
- CLV computed two ways per graded game: **prediction→close** and **open→close** (the latter via
  the optional early odds-only snapshot), surfaced on the CLV scoreboard.
- README: "Run workflow" button as the primary owner control; numbered one-time setup checklist;
  plain-English recovery runbook; public-repo + secret-hygiene notes. (Failure notify + keepalive
  shipped in v1; reaffirmed here.)
- Static-fixture + vcrpy cassette API tests in CI + an occasional quota-aware **live smoke test**
  for fixture/cassette rot.

**Acceptance criteria**
- A fully unattended day produces an updated, deployed page across **both** afternoon and evening
  buckets with a correct freshness stamp + bucket; no human action required.
- Joint-signal test passes: aligned contextual signals move win-prob <=6-8pp and never clear the
  floor on their own.
- Closing lines are recorded **per game** keyed to each game's first pitch; CLV is computed for
  each graded game against the sharpest captured close (us+eu).
- The independent Elo cross-check disagrees with the run model from a different data lineage
  (verified non-trivially correlated, not identical), feeding the divergence guard.
- A deliberately failed run **emails/opens an issue** and **still** commits a keepalive; the
  inactivity timer is verified to reset (or the documented fallback is in place).
- Concurrent commits from the two `predict` runs + `close` + `grade` never fail on
  non-fast-forward (rebase retry proven).
- Daily Odds API spend stays ~10-12 credits; `x-requests-remaining` logged every run; the eu
  region is droppable if quota tightens.

---

## v3 — Validation inference, recalibration, recent form

**Goal:** prove honesty over time and tighten the engine using accumulated graded data — and let
the data, not feel, set the load-bearing constants. This is where the deferred statistical
machinery lands.

**Deliverables**
- **Fit `w` from data** (minimize OOS blended log-loss over graded games) and **re-derive the
  edge floor jointly** so the emit window stays in the defensible range; pin both with regression
  tests. **Drive `w -> 0` automatically** if the model component fails to beat market-only with
  significance.
- **Bootstrap/paired significance test** on the incremental-log-loss-vs-market metric (replacing
  the v1 point estimate); the health line reports a statistically tested figure.
- **Selection-aware (empirical-Bayes / James-Stein) shrinkage** of the day's surviving
  divergences (inserted before the max-bets check); note it sits after the floor gate, so it can
  shrink a displayed divergence below 3.5% and even below the 1.5% floor.
- **Pin `SD_diff` against accumulated game-level run variance** (validate the published VMR ≈
  2.0-2.2 prior); regression-test it. If/when the full NB distribution is needed early, validate
  the exact-convolution path against the closed form.
- Per-game **starter innings-share** estimate from recent IP/start distribution + bullpen usage;
  team/bullpen FIP/SIERA for remaining innings; best-effort reliever fatigue from game logs.
- Recent-form as a small stabilization-gated regressed nudge, **enabled only if it beats a
  talent-only baseline out-of-sample**.
- **De-vig-calibration MONITOR** (binned fair probs vs realized win rate) — flags mis-calibration
  only; **does not** select the de-vig method (multiplicative stays pinned on principle, per the
  MLB-specific evidence).
- **Walk-forward backtest harness** with a permutation null for the top-3 selection; CLV
  (sharpest close) tracking as the slow confirmatory metric.
- Optional sklearn Platt/sigmoid recalibration once >=~1000 graded games (isotonic only above).

**Acceptance criteria**
- Fitted `w` and `SD_diff` are pinned by regression tests; the emit-window mapping test still
  passes after re-fit.
- The health line reports a **statistically tested** incremental-log-loss-vs-market figure on all
  games; if it is not positive, the page shows "model adds no information" and surfaces nothing.
- Backtest is walk-forward, uses odds-at-prediction-time, reserves the close for CLV, flags
  >15-20% ROI as a red flag, and compares top-3 selected CLV against a permuted-edge null.
- Form/contextual additions do not increase the surfaced count beyond the cap nor widen the emit
  window; the joint-signal bound still holds.
- The anchor-calibration monitor reports de-vig calibration without changing the pinned default.

---

## v4 — Totals / player props (gated, quota-honest)

**Goal:** extend to totals and player props **without** blowing the free quota or the calibration
discipline. The roadmap states bluntly that **full-slate daily props are NOT viable on the free
tier.**

**Quota reality (verified, do the math in the doc).** Player-prop markets are available **only**
via the per-event `/v4/sports/{sport}/events/{eventId}/odds` endpoint (one event per call), cost
= **[unique markets RETURNED] × [regions]**, and **empty responses do not count**. A 15-game
slate × 3 prop markets × 1 region costs **up to 45 credits per pull** (variable — less when a
game returns fewer markets) -> up to **~1,350/month -> ~2.7×** the 500-credit free allowance,
before the h2h baseline. After reserving ~2 credits/day for the two h2h prediction runs, ~14
credits/day ÷ ~3 per game ≈ **~4-5 games/day** is the realistic free-tier props ceiling. Treat
per-pull props cost as **variable (≤45)**, keyed off observed `x-requests-last`, not a fixed 45.

**Deliverables**
- Totals (over/under) de-vig + a runs-distribution total model that **promotes the exact NB
  convolution to the live path** (deterministic; parameterized with VMR ≈ 2.0-2.2, `r ≈ 3.7-4.1`)
  — here the distribution *shape* drives the price, so the full NB earns its keep.
- Player props (`batter_home_runs`, `pitcher_strikeouts`, `batter_hits`) via `/events/{id}/odds`
  behind an **explicit flag** with a **hard per-day game-count budget** (default: the single
  highest-divergence game; configurable, ≤~4-5), a **pre-call quota check that fails soft**, and
  budget logic keyed off `x-requests-last` / `x-requests-remaining`.
- Park/weather/platoon signals reused for HR and hits props.
- The **same layered calibration applied per market** (raw-OOD band + divergence + no-market +
  de-vig-fragility + jointly-derived floor + max-bets + grading + CLV).
- Umpire CSV stub remains honest, near-zero weight, labeled non-live.

**Acceptance criteria**
- With the props flag off, behavior is **byte-identical to v3** (no quota spent on props).
- With the flag on, the tool **never** exceeds the configured per-day game budget; monthly Odds
  API spend is projected and logged; a near-limit run **fails soft** with a clear health-line
  message rather than blowing quota or triggering a billing prompt.
- The totals NB-convolution path matches the closed-form moneyline on the marginal win-prob to
  <~0.5pp (regression test), confirming the two engines agree where they overlap.
- Each prop market passes the same calibration golden tests (an injected over-confident prop prob
  yields 0 surfaced props); displayed prop divergences are in the same sane range as moneyline.
- The README/roadmap state explicitly that full-slate props require a paid plan, and the default
  configuration stays inside the free tier.
