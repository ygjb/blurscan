# Build Loop Runbook

How the autonomous build loop drives `blurscan` from issues to merged code.
This is the operating contract — when work is "go", follow it exactly.

## Mode
- **Pacing:** self-paced, continuous. Finish one issue, immediately start the next.
- **Delivery:** one branch + PR per issue; **auto-merge when CI is green**.
- **Tracking:** GitHub issues (`build-loop` label) grouped by milestone M1–M6.

## Issue selection
Each iteration, pick the **lowest-numbered open issue** that:
1. carries the `build-loop` label, and
2. has all of its stated dependencies (the "Depends on:" line in its body) **closed**, and
3. is **not** labeled `security`.

If the only remaining eligible issues are `security`-labeled, **stop and notify** —
those require explicit human approval (see below).

## Per-issue procedure
1. `git switch -c issue-<n>-<slug>` off the latest `master`.
2. Implement strictly per the issue's Acceptance section and the referenced DESIGN.md sections.
3. Write the unit tests named in the issue.
4. Run the **local done-gate** before pushing:
   - `ruff check .`
   - `mypy blurscan`
   - `pytest -q`
   - package imports + `blurscan --help` runs without error
5. Commit (Co-Authored-By trailer), push, and open a PR that:
   - title references the issue,
   - body has **`Closes #<n>`**, a short **self-review note**, and any **deviations from DESIGN.md**.
6. Enable auto-merge: `gh pr merge --auto --squash`.
   - GitHub's required `ci` check gates the actual merge; the PR lands only when green.
7. Move to the next eligible issue without waiting for the merge (CI runs async).
   - If CI fails, fix forward on the same branch; do not start dependent issues until it merges.

## Security gate — APPROVED (2026-06-29)
The maintainer granted standing approval to build the `security`-labeled issues
(**#12 exiftool subprocess**, **#15 Flask review server**) autonomously, and wants the
loop to run continuously overnight. **Do NOT pause at the security gate.** Build #12/#15
in dependency order like any other issue, with extra care on the flagged concerns
(subprocess arg handling for #12; path-traversal / CSRF / 127.0.0.1 binding for #15).

A **dedicated security review pass** runs AFTER all build-loop issues are complete
(e.g. `/security-review` over the merged work), then report findings.

## Stop conditions
- Backlog empty (all `build-loop` issues closed) → report completion.
- Only `security` issues remain → request approval, then halt.
- A CI failure that can't be resolved by fix-forward → stop and report.

## Definition of "green" (CI)
`.github/workflows/ci.yml` runs ruff + mypy + pytest on every PR. `master` is
branch-protected to require the `ci` check, so auto-merge cannot land a red PR.
