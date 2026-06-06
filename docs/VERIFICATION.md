# AlgoBall — Verification Report (docs/VERIFICATION.md)

This report records round 2's adversarial verification of the round-1 design. For each
fact-checked claim: the verdict, the correction applied to ARCHITECTURE.md / ROADMAP.md, and
the source. It then records the architecture-alternatives verdicts (keep / modify / switch) and
the two deep-dive conclusions (safety band, de-vig method), and the senior-engineer decisions
made from them.

Senior-engineer spot-checks performed this round (independent reproduction): the win-prob
arithmetic, `SD_diff`, de-vig math, emit-window, and NB shape were recomputed in Python; the
MLB Stats API FIP field and the schedule `probablePitcher` nesting were re-queried live on
2026-06-05 and confirmed (FIP populated; `probablePitcher` nested under `teams.home/away`, NOT
top-level; `gameType=='R'`; `venue` at game level).

---

## A. Fact-check verdicts and corrections applied

### A1. `winprob-072-ceiling` — REFUTED (high) — the consequential one
**Claim (round 1):** a correctly-calibrated single-game home win prob "essentially never
exceeds ~0.72"; "heaviest real de-vigged moneylines sit near 70-74%"; extremes "75-78%."

**Correction applied.** Two distributions were conflated:
- **Predictive MODELS** top out ~0.72-0.74 (FiveThirtyEight's own pitcher-aware Elo season-max
  = **74.22%** computed directly from `mlb_elo_latest.csv` 2023; 75th pct ~58.7%). The ~0.72
  figure is correct for **models**, and is the conservative bound.
- **De-vigged MARKETS** reach **~0.80-0.82** in the extreme tail (record road favorite Astros
  -550/Orioles +380 de-vigs multiplicatively to **exactly 80.2%**; Astros -521 (2019) ≈
  80.8-81.4%; ~-600 ≈ 82.5%; all-time ~82-84%).

The 0.81 bug was diagnostic because of its **34pp divergence** from a 46.8% market, not because
0.81 is unreachable. ARCHITECTURE.md §1 now states model ceiling ~0.72-0.74 vs market ceiling
~0.80-0.82, designates the **divergence guard as primary** and the OOD band as a redundant
source-level catch, and the safety-band §6 Layer 2 is rewritten accordingly (decision in §C1).
**Sources:** FiveThirtyEight `mlb_elo_latest.csv` (2023); Las Vegas Review-Journal (Astros
-550/+380); BetMGM "Largest MLB Moneyline Favorites Since 2005"; SABR head-to-head matchup
table; multiplicative de-vig references.

### A2. `odds-api-500-quota` — CONFIRMED (high)
500 credits/month (reset on the 1st); `/odds?regions=us&markets=h2h` = exactly 1 credit
(markets × regions); headers `x-requests-remaining` / `-used` / `-last` named exactly. No
change needed; quota design rests on accurate numbers. **Source:** the-odds-api.com v4 guide +
pricing/FAQ.

### A3. `props-perevent-45-credits` — CONFIRMED (high)
Props are per-event only; cost = unique markets **RETURNED** × regions; empty responses are
free; 15×3×1 = **up to 45 credits/pull** (variable, not fixed) -> ~1,350/month -> ~2.7× the free
tier; ~4-5 games/day realistic. ROADMAP v4 now states per-pull cost is **variable (≤45)** keyed
off `x-requests-last`. **Source:** the-odds-api.com v4 guide + MLB odds page + pricing.

### A4. `emit-window-floor-shrink-math` — CONFIRMED (high)
`EDGE_FLOOR/w = 0.015/0.35 = 0.042857 ≈ 0.043`; `w*MAX_RAW_DIVERGENCE = 0.35*0.10 = 0.035`;
displayed-edge identity `= w*(p_model - p_market)` holds (convex combination). Emit window =
raw divergence [4.3pp, 10pp], displayed [1.5%, 3.5%]. **Added nuance:** the [1.5%, 3.5%] window
is pre-selection-shrinkage; since the floor gate (Layer 7) precedes selection shrinkage
(v3 Layer 8), enabling selection shrinkage can push displayed divergences below 3.5% and even
below the 1.5% floor. Recomputed and confirmed this round. ARCHITECTURE §6 Layer 7/8 note this.

### A5. `old-design-floor-arithmetic` — CONFIRMED (high)
`0.06/0.30 = 20pp`; `0.10/0.30 = 33.3pp` (stated "33pp"; exact 33.3). The collapse depends on
weights summing to 1 (0.30+0.70). Recomputed and confirmed. ARCHITECTURE §1 quotes 33.3pp.

### A6. `nb-dispersion-variance-mean` — PARTIALLY-CORRECT (high) — dangerous direction
**Claim (round 1):** runs/game variance-to-mean ratio "~1.3-1.5."
**Correction applied.** The empirical VMR is **~2.0-2.2** (1981-96: 4.456/9.360 = 2.10; AL
2008-13: 2.22; NL: 2.15). The ~1.1 figure likely confused with the Tango/Dolinar **`B` =
VMR−1 ≈ 1.1** over-dispersion add-on. Using 1.3-1.5 makes the distribution ~3× too tight
(implied shape `r ≈ 11` vs true `r ≈ 3.7-4.1`), **inflating** single-game separation — the 81%
bug mechanism — and slips past the +0.5-run test. ARCHITECTURE §5 replaces 1.3-1.5 with VMR ≈
2.0-2.2 and derives **`SD_diff ≈ 4.3`** from it (verified: VMR 2.1 → SD_diff 4.30; avg MOV
3.285 → SD 4.12). **Sources:** walksaber.blogspot.com; stats.seandolinar.com;
community.fangraphs.com; thedatajocks.com.

### A7. `half-run-edge-winprob` — CONFIRMED (high)
+0.5-run edge → **~55%** (54-56%), via three independent methods (NB convolution 54.7-55.8%;
Pythagorean exp 1.82 → 55.0%; linear runs-to-wins → 54.9%). 70% needs ~2.15 runs; 81.2% needs
~3.6 runs. Recomputed with `SD_diff = 4.3`: +0.5 → 54.6%, 0.81 needs 3.77 runs. Kept as a
**band** (54-56%), pinning the win-prob rather than the exact dispersion constant, per the
recommendation. **Sources:** exact NB convolution; Analyzing Baseball Data with R 3e; FanGraphs.

### A8. `devig-multiplicative-formula` — CONFIRMED (high)
`fair_i = implied_i/Σ`; `-110/-110 → 50/50` (verified: implied 0.52381 each, sum 1.04762, fair
0.50000); `fair_i < implied_i` both sides; **for 2-way, Shin == additive** (machine precision).
Caveat: multiplicative is "standard and defensible," not provably "best-in-class" (additive/
power sometimes score marginally better, mainly in 3-way markets). ARCHITECTURE §6 retains
multiplicative and adds the Shin==additive invariant test + the de-vig-method-fragility guard.
**Sources:** CRAN `implied` vignette; penaltyblog; sharkbetting; Clarke (2017).

### A9. `nb-monte-carlo-vs-skellam` — PARTIALLY-CORRECT (high)
NB-over-Poisson direction correct (captures over-dispersion). Three fixes: (a) the dispersion
figure is wrong (see A6); (b) "Monte Carlo best-in-class" overstates it — an **exact NB-difference
convolution dominates** 10k-sim MC (removes ~0.5pp sampling noise, deterministic); (c) Skellam is
a valid Poisson-model, not merely a test oracle (it is relegated for equidispersion, not bad
math). Extra-innings home rate ~0.52-0.53 historically but **~0.49 in the ghost-runner era** (see
A14). **Decision (§C):** kill the Monte Carlo entirely; v1 uses a **deterministic closed-form**
map; the exact NB convolution is deferred to v4 (totals/props) where shape matters. **Sources:**
Wikipedia Skellam; scipy.stats; sabermetric run-distribution sources.

### A10. `statsapi-sabermetrics-fip` — CONFIRMED (high)
`people/{id}/stats?stats=sabermetrics&group=pitching` returns a real `fip` (verified live
2026-06-05; Skubal 2025 FIP = 2.44913). `fip` is exclusive to the `sabermetrics` group. **The
API imposes no min-IP gate** — it returns `fip` for ≥1 appearance and **empty `stats:[]`** when
there is no pitching data. The min-IP gate + manual fallback are **consumer-side** choices.
ARCHITECTURE §3 now states empty-splits handling explicitly and adds the manual-FIP formula
`FIP = ((13*HR)+(3*(BB+HBP))-(2*K))/IP + cFIP`, `cFIP ≈ 3.10`. **Source:** live API + FanGraphs.

### A11. `statsapi-boxscore-hydrate-person` — CONFIRMED (high)
`boxscore?hydrate=person` adds `batSide`/`pitchHand` (`{code, description}`), absent without the
hydrate. **Both fields appear on every person (hitter AND pitcher);** role is derived from
lineup/position, not field presence. Alternative: `GET /people/{id}` returns them natively.
ARCHITECTURE §3 parse contract notes this. **Source:** live API + type-definition references.

### A12. `statsapi-schedule-hydrate` — CONFIRMED (high)
Verified live: `probablePitcher` is nested under **`teams.home/away.probablePitcher`** (NOT
top-level — confirmed `False` this round), `venue` at game level, `gamePk` int. `probablePitcher`
is **optional/null before announcement** (re-hydrated on the second run). **Filter `gameType ==
"R"`** (the slate can include All-Star/exhibition). ARCHITECTURE §3/§4 corrected. **Source:**
live API 2026-06-05 + community docs.

### A13. `hfa-534-empirical` — CONFIRMED (high)
Modern MLB HFA ~.530-.534 (2020s = .534, lowest Live-Ball decade); ~58% is too high. **Key
correction:** the canonical Elo HFA constant is **24 points → P(home)=.5345**, which already
agrees with ~.534 — the round-1 "Elo HFA of 55 ≈ .578" is a **strawman** (no standard MLB Elo
uses 55). `.534 = +3.4pp`, so a flat "+4pp" slightly overstates. ARCHITECTURE §5 applies HFA as
`HFA_RUNS` (~+3 to +3.5pp inside the run model) and drops the 55-Elo strawman. **Sources:** SI;
FiveThirtyEight methodology (24 points); SABR historical-HFA.

### A14. `extra-innings-home-053` — REFUTED (high) — dangerous direction
**Claim (round 1):** tie → home at the extra-innings home win rate "~0.53."
**Correction applied.** Under the post-2020 automatic-runner rule (our era), home teams won
**~49.3%** of extra-inning games (2020-2024; FOX raw: visitors 477-465 = home .494) — a slight
home **disadvantage**. The 0.53 figure conflated the all-games HFA (~.534) / a theoretical
sudden-death model. Using 0.53 added ~+0.3-0.5pp systematic upward home bias on every tie — the
compounding over-confidence the project guards against. ARCHITECTURE sets
`EXTRA_INNINGS_HOME_WINRATE ≈ 0.49`, pinned, revisited if the rule changes. (Note: in the v1
closed-form engine there is no discrete tie atom, so this is sub-0.1pp there; it is pinned for
the discrete path.) **Sources:** FanGraphs (Rob Mains, 49.3%); FOX Sports.

---

## B. Architecture-alternatives verdicts (keep / modify / switch)

### B1. Win-probability modeling engine — **MODIFY**
Keep the expected-runs → run-distribution → win-prob spine (right level of abstraction; folds
in free signals at the rate level; enforces "0.5 runs ≈ 55%"). **Switch the engine** from the
10k-draw NB Monte Carlo to a **deterministic closed-form** `P(home) = Phi((λ_h-λ_a)/SD_diff)`,
`SD_diff ≈ 4.3`. Rationale: near 50% only mean and SD of the differential matter; one published,
doubly-anchored parameter; fully deterministic (no RNG/seed across two daily runs); clearer bug
narrative (0.81 needs ~3.8 runs). Fix the dispersion fact (VMR ~2.0-2.2). Hold the full NB
distribution (exact convolution, not MC) in reserve for v4 totals/props. Promote a genuinely
independent team-Elo cross-check (replacing the circular PythagenPat) — placed at **v2**.
Make explicit that AlgoBall is a **market-anchored system with a small nudge** (`w ≈ 0`), so the
engine choice is second-order and simplicity/determinism govern. **Applied** in ARCHITECTURE §5.

### B2. Market efficiency & intellectual honesty — **MODIFY**
The design is more honest than typical tools but still over-claimed. **Reframe** the headline
from "genuine edge/best bets" to a falsifiable **measurement scoreboard** (incremental
log-loss-vs-market as the banner; surfaced games = "model-vs-market divergence," not "+X%
edge"; running CLV). **Exploit the two-run coverage** to capture an earlier/softer line and
measure **open→close** CLV (the only structural path to demonstrating edge). **Add Pinnacle
(eu)** as the sharp de-vig + CLV anchor. **Correct** the win-prob ceiling fact (market reaches
~0.80-0.81). **State the premise honestly:** not expected to beat the sharp close. **Applied**
in ARCHITECTURE §1, §2.2, §12 and ROADMAP framing. (Lens 2's alternative band — widen OOD to
(0.05,0.95), tighten divergence to 0.08, clamp (0.10,0.90) — was considered but the deep-dive's
band was adopted instead; see §C1.)

### B3. Software architecture & solo-owner maintainability — **MODIFY**
Bones are right (one uv package, one HTML file, GitHub Actions+Pages, frozen pydantic v2,
layered guards, offline golden suite). **Trim:** drop requests-cache/SQLite from v1; **defer the
validation inference stack** (James-Stein, bootstrap, anchor monitor, backtester) to v3; reduce
vcrpy reliance in favor of committed static JSON fixtures for core math. **Add/promote to v1:**
two-run coverage; failure notification + runbook + run button; **split the safety band into two
constants** (raw-model OOD vs final clamp). **Pin** uv version, commit `uv.lock` +
`.python-version`, document pip fallback. **Make the public-repo dependency explicit.** Keep one
frozen pydantic system; keep Actions+Pages (mitigate cron flakiness with keepalive + freshness
stamp). **Applied** in ARCHITECTURE §3, §8, §9, §10 and ROADMAP phase split.

### B4. Coverage + scheduling + quota for two-run operation — **MODIFY**
The owner override (both afternoon + evening) is cleanly achievable; the quota fear behind the
old evening-only scope is unfounded — a full-slate `/odds` call is 1 credit regardless of game
count, so a second run adds only +1 credit/day. **Adopt** two scheduled prediction crons
(afternoon ~15:00 UTC, evening ~21:00 UTC) + a **bucket-agnostic, `commence_time`-filtered**
pipeline; the evening run re-predicts/upgrades provisional picks; **one** `predict.yml` with two
cron entries; an **independent never-publish-started-games render guard**. **Correct** the §8
quota error: adding the `eu` region is **2 credits/call** (markets × regions), not "still 1."
Rejected: Design B (single long-running job — violates the 6h job limit) and Design C (dynamic
per-game crons — GitHub cron is static/UTC/delayed). **Applied** in ARCHITECTURE §8 and ROADMAP
v1/v2.

---

## C. Deep-dive conclusions and senior-engineer decisions

### C1. Safety band — DECISION (senior engineer)
**Adopted (the deep-dive's evidence-anchored, two-constant layered band):**
- **`PROB_OOD_BAND = [0.20, 0.80]`** — HARD suppress + calibration alarm on the **raw model
  probability**. A calibrated model essentially never exceeds ~0.72-0.74, so 0.80 sits at the
  empirical *market* maximum and **never suppresses a legitimate model output**, while it
  **catches the 0.81 bug at source** (0.81 > 0.80), redundantly with the divergence guard.
- **`PROB_OOD_SOFT_BAND = [0.28, 0.72]`** — non-suppressing investigative flag. A raw prob of
  0.74-0.79 (genuine heavy favorite) is logged "verify vs market," **not** suppressed — this is
  exactly "flag, don't suppress legitimate heavy favorites." 0.72 is the true model ceiling.
- **`MAX_RAW_DIVERGENCE = 0.10`** — the PRIMARY catcher (Astros 0.81 vs 0.47 = 34pp).
- **`PROB_CLAMP = [0.15, 0.85]`** — final-blended-prob backstop; fires on the market-anchored
  blend (not the raw model), so a model correctly agreeing with a ~0.80 market is not clipped.

**Why this over the alternatives.** The `winprob-072-ceiling` fact-check and lens B1 recommended
keeping a single `(0.15, 0.85)` OOD band and rejecting `(0.25, 0.75)`. Their core concern — do
not clip a legitimate ~0.80 market favorite, and 0.75 would clip FiveThirtyEight's 0.742 model
max — is **fully honored** here, because the **clamp** stays at 0.85 and fires on the *blend*,
while the **OOD band fires on the raw model** (which never legitimately exceeds ~0.74). But a
single `(0.15, 0.85)` OOD band lets the exact 0.81 value pass the band (0.81 < 0.85), leaving the
bug to a single guard — violating "no single guard / fire at source." The deep-dive's `[0.20,
0.80]` hard band restores the redundant source-level catch **without** ever suppressing a real
output, and the `[0.28, 0.72]` soft flag preserves the "don't suppress heavy favorites" behavior.
Lens B2's wider `(0.05, 0.95)` OOD (pure parse-error backstop) and lens B3's `[0.20, 0.80]`
agree directionally; the deep-dive's layered hard+soft formulation is the most precise and is
adopted. `(0.25, 0.75)` is rejected (would clip the 0.742 model max and legitimate reads). The
divergence guard is kept at 0.10 (preserves the documented emit window; 0.08 is a defensible
future tightening). **Corrected ARCHITECTURE.md §1, §6 Layer 2/6 and added the safety-band
discrimination golden test.**

### C2. De-vig method — DECISION (senior engineer)
**Adopted: keep MULTIPLICATIVE as the live default, pinned on principle (not selector-chosen).**
Decisive MLB-specific evidence (Berkowitz, Depken & Gandar 2018, *Journal of Sports Economics*):
in MLB moneylines "standard normalization performs as well as the Shin probabilities... because
this particular betting market does not suffer from economically meaningful inefficiency" — MLB
has no reliable favorite-longshot bias (Woodland & Woodland 1994's reverse-FLB was refuted by
Gandar et al. 2002 and Cain/Law/Peel 2003). So no FLB-correcting method (additive/Shin/power) is
justified; multiplicative is standard, simplest, and most stable.

Two refinements applied: (1) **Do not** let the offline calibration selector choose the method
(round 1's plan) — in MLB the methods differ by <1pp and are statistically indistinguishable, so
a selector fits noise and would flip season to season; pin multiplicative and use calibration
only as a **monitor** (v3). (2) **Add a de-vig-method-fragility guard** (ARCHITECTURE §6 Layer
4b): compute `additive(=Shin)` alongside; the methods diverge up to ~1.0-1.2pp on heavy
favorites — the same magnitude as the divergences AlgoBall measures — so on steep lines
(>~-180) flag "de-vig-method-fragile" and suppress or raise the floor. `power` stays offline-only
(over-corrects a bias MLB lacks). Verified: Shin == additive for 2-way to machine precision.

### C3. Empirical maximum single-game win probability (the safety-band input)
The de-vigged **market** maximum over 20+ years is **~0.80-0.82** (Astros -550/+380 = 80.2%
exactly; -521 ≈ 80.8-81.4%; all-time ~82-84%). The calibrated **model** maximum is **~0.72-0.74**
(FiveThirtyEight season-max 74.22%; 75th pct 58.7%; better team wins one MLB game only ~54%).
These two numbers drive the two-constant band in C1: the OOD band fires on the model
distribution (cap ~0.74 → hard ceiling 0.80 never binds on a legit output, catches 0.81), the
clamp tolerates the market tail (~0.82 < 0.85). An 0.80 model ceiling **never costs a real bet**
(a bet emits only at 4.3-10pp divergence; a model >0.80 vs a market ~0.70-0.76 is the
overconfident-favorite miscalibration that loses money, per Allen & Savala 2025), at most a rare
investigative alarm. ARCHITECTURE §1 corrected to state market max ~0.80-0.82, model max
~0.72-0.74.

---

## D. Residual uncertainties (carried forward)
- FiveThirtyEight shut down; the exact single-game forecast **maximum** (~0.74) is from a 2023
  CSV snapshot + the 58.7% 75th-pct; directionally solid, not a live citation.
- Historical de-vigged extremes assume an unrecorded paired underdog price (~5% hold); the
  Astros figures are robust across the plausible dog range but not exact.
- `SD_diff ≈ 4.3` is anchored to published pooled VMR (~2.1) and avg MOV (~3.3); the **conditional**
  single-matchup dispersion may be slightly lower — the +0.5-run win-prob band (54-56%) is robust
  to this, which is why the band (not the constant) is pinned. Re-validate `SD_diff` against
  accumulated game-level run variance in v3.
- Berkowitz et al.'s "multiplicative as good as Shin in MLB" is qualitative (their stated
  conclusion), not a published per-method Brier table; modern soft books (DK/FD) carry higher,
  more lopsided hold than the older sharp lines studied, which only strengthens the case for the
  fragility guard.
- Extra-innings ~0.49 is the 2020-2024 ghost-runner-rule figure; revisit if MLB alters/removes
  the automatic-runner rule.
- Whether a free-data model adds *any* incremental information over the de-vigged market is an
  open empirical question by design — that is precisely what the v1 measurement scoreboard exists
  to answer over 1-2 seasons.
