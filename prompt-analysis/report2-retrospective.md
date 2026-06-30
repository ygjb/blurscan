# blurscan — Build Retrospective

**Generated:** 2026-06-30
**Companion to:** [report1.md](report1.md) (prompt & token analysis)
**Sources:** git history (`git log`, author dates in PDT/−0700), Claude session transcripts (`*.jsonl`, timestamps in UTC), `DESIGN.md` §11, and the trigger analysis from report1.

> **Timezone note:** git author dates are PDT (−0700); session timestamps are UTC. This document normalizes everything to **UTC** (PDT + 7h). The first prompt (04:34 UTC) and the first commit (04:40 UTC) anchor the two clocks.

---

## 1. Headline: effort vs. duration

Two different numbers, often conflated:

| Measure | Value | What it means |
|---|---|---|
| **Duration** (wall clock, first prompt → first release) | **~10 h 44 min** | 04:34 UTC (Prompt 1) → 15:18 UTC (#19 packaging) |
| &nbsp;&nbsp;↳ of which: **overnight dead gap** | **7 h 56 min** | 06:31 → 14:27 UTC — the failed trigger window, zero progress |
| &nbsp;&nbsp;↳ **productive duration** (duration − dead gap) | **~2 h 48 min** | the wall-clock time when work actually happened |
| **Effort — Claude active build** | **~2 h 25 min** | measured from message timestamps (gaps ≤5 min counted as active) |
| **Effort — Human steering** (estimate) | **~40 min** | 18 typed prompts + 7 decision blocks, mostly in the first 80 min |
| **Combined hands-on effort** | **~3 h** | Claude + human active time |

**The punchline:** the project's *productive* duration (~2 h 48 min) almost exactly equals its *effort* (~3 h). The build was effort-bound, not duration-bound — there was essentially no waiting except the one catastrophic 8-hour overnight gap, which contributed **0% of the output** but **74% of the wall clock**.

### Versus a human developer

`DESIGN.md` §11 estimated a competent Python dev at **6–8.5 working days** (1.5–2 weeks calendar) and Claude at **2.5–3.5 h active build**. Actuals:

- Claude active build came in at **~2.4 h** — slightly *under* its own low estimate.
- Against the human baseline (≈48–68 working hours), the ~3 h combined hands-on effort is a **~16–22× effort reduction**.
- Calendar-wise, ~11 h (one evening + next morning, mostly idle overnight) vs. 1.5–2 weeks is a **~30–50× calendar compression** — and that's *with* the wasted night. Without it, the tool was buildable in a single ~3-hour sitting.

---

## 2. Build timeline (UTC)

Merged from git commits, session prompts, and `AskUserQuestion` decisions. `▶` = human prompt, `🔀` = decision point, `✓` = merged PR/commit.

| UTC | Event | Detail |
|---|---|---|
| 04:34 | ▶ Prompt 1 | "analyze a photo collection to identify blurry images… ask me questions" |
| 04:34 | 🔀 Decision 1 | output=**all-via-flags**, scale=**<5k**, **avoid artistic-blur FPs**, formats=**JPEG+HEIC+RAW** |
| 04:37 | ▶ Prompt 2 | "spawn a local webserver", "exiftool", "write a design document + estimates" |
| 04:39 | ▶ Prompt 3 | "use gh to create a public repo, include design artefacts" |
| 04:40 | ✓ commit | `DESIGN.md` + scaffolding (d180691) |
| 04:41 | ▶ Prompt 4 | "set up a build loop… create all issues first… ask me how the loop works" |
| 04:42 | 🔀 Decision 2 | **task-level issues**, **PR auto-merge if green**, **self-paced continuous**, **all 4 done-gates** |
| 04:47 | 🔀 Decision 3 | **Actions CI required**, **set up only / I start it**, **skip-ahead on security issues** |
| 04:48 | ✓ commit | CI workflow + `LOOP.md` runbook (b5bb071) |
| 04:51 | ▶ Prompt 5 | "confirm test_samples gitignore" |
| 04:52 | ▶ Prompt 6 | "use test_samples dir for unit tests; blurry/ = blurry, not_blurry/ = not" |
| 04:53 | 🔀 Decision 4 | CI fixtures = **local-only + synthetic CI** |
| 04:54 | ✓ commit | two-tier test fixtures (6d4ea67) |
| 04:55 | ▶ Prompt 7 | **"kick off the loop."** |
| 04:58 | ✓ #1 | scaffolding (PR #20) |
| 05:03 | ✓ #2 | models.py dataclasses (#21) |
| 05:07 | ✓ #3 | loader.py JPEG/PNG (#22) |
| 05:12 | 🔀 Decision 5 | **detection pivot** → "add the first three [methods] as options, each with its own flag" |
| 05:21 | ✓ #4 | detector registry + laplacian (#25) |
| 05:26 | ✓ #5 | classifier (#26) |
| 05:30 | ✓ #6 | pipeline serial (#27) |
| 05:33 | ✓ #7 | report: CSV + HTML (#28) |
| 05:36 | ✓ #8 | cli.py + `--method` (#29) |
| 05:42 | ✓ #9 | HEIC/HEIF (#30) |
| 05:46 | ✓ #10 | camera RAW (#31) |
| *05:46–06:16* | *(idle 30 min)* | |
| 06:16 | ▶ Prompt 8 | "I approve the security gates… run through the night" |
| 06:24 | ✓ #32 | CC test corpus integrated (reverses Decision 4 — see §6) |
| 06:25–06:26 | 🔀 trigger armed | hourly `create_trigger`, fresh-session-per-fire (3 attempts) |
| 06:31 | ✓ #11 | quarantine action (#33) — **last evening PR** |
| **06:31–14:27** | **⛔ OVERNIGHT DEAD GAP (7 h 56 m)** | trigger fired ~8×, **zero PRs, zero issues closed** |
| 14:27 | ▶ Prompt 9 | "status?" |
| 14:29 | 🔀 Decision 6 | "trigger fired ~8× but accomplished nothing" → **resume here + kill trigger** |
| 14:36 | ✓ #12 | exiftool tag action (#34) — **morning burst begins** |
| 14:40 | ✓ #13 | SQLite cache (#35) |
| 14:44 | ✓ #14 | parallel scoring (#36) |
| 14:48 | ✓ #23 | motion-blur detector (#37) — *spawned by Decision 5* |
| 14:57 | ✓ #24 | ML classifier (#38) — *spawned by Decision 5* |
| 15:03 | ✓ #15 | Flask review server (#39) — *security-gated, pre-authorized* |
| 15:07 | ✓ #16 | review SPA (#40) |
| 15:12 | ✓ #17 | per-tile heatmap (#41) |
| 15:15 | ✓ #18 | integration tests (#42) |
| 15:18 | ✓ #19 | packaging + docs (#43) — **first release: all 21 build-loop issues done** |
| 15:22 | ✓ security | exiftool arg-injection + review-UI DOM-XSS fixes (dca6809) |

**Cadence:** evening built 11 issues in ~1 h 30 m active (~8 min/issue, slowed by 5 decision blocks); morning built 10 issues + security in ~54 min active (~5 min/issue, no interruptions — the operator drove the live session directly). The morning was *faster per issue* precisely because the design was settled and there were no decisions to make.

---

## 3. Decisions that changed the shape of the project

Six of the seven decision blocks were routine scoping; **three were load-bearing** — they changed *what got built*, not just *how*:

1. **Decision 1 → "all output actions, via flags"** (not "report only"). This is why the tool has four delivery modes — report (#7), quarantine (#11), tag (#12), and the review UI (#15–17) — instead of one. It roughly *doubled* the action surface.

2. **Prompt 2 → local Flask server + exiftool.** The single biggest shape driver. The review UI (#15–17) is ~⅓ of the whole tool (DESIGN.md's own estimate), and the tag action (#12) exists only because the operator said "exiftool" here. A one-line answer created the largest milestone.

3. **Decision 5 → "add the first three detection methods, each with its own flag."** The pivot. The original issue list (#1–#19) assumed a single max-tile-Laplacian metric. When that metric couldn't separate the operator's motion-blur samples, Claude surfaced four options; the operator picked *three of them as parallel features*. That spawned **two new issues outside the original plan** — #23 (motion-aware) and #24 (ML classifier) — turning a single-metric tool into a 3-method tool. This is the clearest example of a mid-build decision reshaping scope.

A fourth, quieter shape change came from the **corpus side-session** (§6): it *reversed* Decision 4.

---

## 4. What could have prevented the overnight break

**Root cause (from report1's trigger analysis):** the loop was armed as an hourly cron `create_trigger` with `create_new_session_on_fire=true` in the *Default cloud environment*. Each firing spawned a cold session with **no repo checkout, no `.venv`, no `gh` auth** — so all ~8 fires were no-ops. Self-binding into the live session had failed first ("no session_id in auth claims"), forcing the fresh-session fallback.

Concrete preventions, roughly in order of leverage:

1. **Match the runner to the pacing choice.** The operator explicitly chose **"self-paced continuous"** (Decision 2) — which *is* a single-long-lived-session model. Arming an hourly *fresh-session* cron contradicted that choice. The aligned design is: keep one session driving the loop and use an in-session keep-alive (`ScheduleWakeup`/loop) so it never needs a cold box. This single alignment would have avoided the entire failure class.

2. **Smoke-test the unattended runner before walking away.** One manual fire at 06:30 would have shown a no-op in minutes — 8 hours earlier than the 14:27 "status?" discovery. **Never trust an unattended loop you haven't watched complete one real iteration.**

3. **Assert the environment contract before arming.** The runner needs three things: a checkout, a built venv, and `gh` auth. A 3-line pre-flight (`git rev-parse`, `python -c "import blurscan"`, `gh auth status`) inside the firing prompt would have failed loudly instead of silently idling — or, if you *want* fresh sessions, the firing prompt must **bootstrap** all three (clone → venv → install → auth) idempotently.

4. **Add a dead-man's switch on *progress*, not completion.** The trigger only promised a notification when the *backlog emptied*. Notify on each **merged PR** instead, and alarm on "next_run_at fired but no issue closed since last fire." Silent idling should be impossible to miss.

5. **Make the success signal externally observable.** State lived in GitHub issues (good), but nothing *watched* the close-rate. A tiny external check — "open `build-loop` issues unchanged across 2 fires → page me" — turns an 8-hour silent failure into a 2-hour alert.

---

## 5. Restructuring for fewer tokens (subagents)

**The cost problem (report1 §5):** cache reads were **166 M tokens ≈ $83 of the ~$120 total**. One monolithic session re-fed its entire growing prefix — `DESIGN.md`, every prior issue's code and test output — on every one of ~709 turns. Context that issue #24 never needed rode along in the prefix anyway.

**Restructure: orchestrator + per-issue subagents.**

- The **orchestrator** holds only a thin running state: the issue list, a one-line status per closed issue, and `DESIGN.md`'s table of contents.
- For each issue it spawns a **subagent** whose context is *scoped*: the relevant `DESIGN.md` excerpt, the one issue's text, and the handful of files it touches. The subagent builds → runs the full local gate (pytest/ruff/mypy) → returns a **structured result** (`{issue, pr_url, files_changed, tests_pass}`), not a prose transcript. Its context — including verbose test output — dies with it and never enters the orchestrator's prefix.
- Use a **cheaper model (Haiku) for mechanical issues** (scaffolding #1, models #2, docs #19) and reserve Opus for the orchestrator and the hard issues (detector core #4, ML #24). Doing this *via subagents* rather than switching models in one session matters: switching models mid-session invalidates the prompt cache, whereas a subagent is a separate cache scope.

**Rough token math.** The monolith re-read a prefix that grew toward ~Nk tokens, ~700 times → ~160 M cache reads. Per-issue subagents each carry a small prefix (~15–20 K: design excerpt + 1 issue + a few files), re-read only across that issue's ~25 turns: ≈ 24 issues × 25 turns × ~18 K ≈ **~11 M cache reads** instead of 160 M. Add orchestrator overhead (thin summaries, ~a few M). Estimated cache-read cost **~$83 → ~$8–12**, i.e. a **75–85% total-cost reduction** with no quality loss — arguably *higher* quality, since each subagent reasons over a focused context instead of a 160 M-token haystack.

---

## 6. Restructuring for speed (concurrent agents)

The build was **strictly serial**: 24 issues, one at a time, each gated on CI-green before the next. But the issues form a **dependency DAG, not a line**:

```
#1 scaffold → #2 models → #3 loader ─┬─→ #9 HEIC      (independent leaves)
                          #4 detector ┼─→ #10 RAW
                          #5 classifier┼─→ #11 quarantine
                                       ├─→ #12 tag
              #6 pipeline ─────────────┼─→ #13 cache
                                       ├─→ #14 parallel
                                       ├─→ #23 motion
                                       └─→ #24 ML
              #15 server → #16 SPA → #17 heatmap   (a 3-deep sub-chain)
              (everything) → #18 tests → #19 packaging
```

**Restructure: fan out independent issues to worktree-isolated agents.**

- Each agent works in its **own git worktree** on its own branch (`isolation: "worktree"`) so parallel file writes don't collide; it builds its issue, runs the gate, opens a PR. The orchestrator merges green PRs as they land and rebases the queue.
- **Pipeline the phases** (build → test → PR) so an issue in "test" doesn't block another in "build."
- The wall-clock floor becomes the **critical path depth**, not the issue count. The longest chain here is ~6–8 issues (scaffold→models→loader→pipeline→cli→…, plus the server→SPA→heatmap branch). At ~6 min/issue that's a **~45–60 min floor vs. the ~2.4 h serial actual — roughly a 2.5–3× wall-clock speedup**, capped by the concurrency limit (~10–16 agents) and CI throughput.

**Caveats (why it isn't free):**
- **CI becomes the bottleneck.** N parallel PRs trigger N CI runs; "auto-merge if green" serializes on the merge queue and on conflicts.
- **Shared-file conflicts.** Parallel branches touching `pyproject.toml`, `cli.py`, or the detector registry will collide at merge. Mitigation: the **task-level granularity** choice (Decision 2) already pushes toward disjoint-file issues — lean into it, and have the orchestrator own the merge order and rebases.
- **Combine with §5:** parallelism (worktree agents) and token-scoping (per-issue context) are **orthogonal** — doing both yields a build that is simultaneously ~3× faster *and* ~80% cheaper.

---

## 7. Summary scorecard

| Dimension | Actual | Best-case restructure |
|---|---|---|
| Claude active build | ~2.4 h | ~45–60 min (concurrent agents) |
| Wall-clock to release | ~10.7 h (74% wasted overnight) | ~1 h (no dead gap + concurrency) |
| Est. cost | ~$120 | ~$15–25 (scoped subagents) |
| Overnight reliability | failed (8 no-op fires) | a single continuous session, smoke-tested, with progress alerts |
| Issues delivered | 21 build-loop issues + security | same |

The tool that got built was correct and well-gated; the inefficiencies were all in **orchestration**, not in the work itself: a runner mismatched to the chosen pacing (cost: 8 hours), a monolithic context (cost: ~$100), and a serial queue over a parallelizable DAG (cost: ~1.5 h). All three are fixable with the same two primitives — **one durable orchestrator + scoped, worktree-isolated subagents.**
