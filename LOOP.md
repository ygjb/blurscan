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

## Security gate (the only approval stop)
Issues labeled `security` (currently **#12 exiftool subprocess**, **#15 Flask review server**)
are **never implemented autonomously**. When one becomes the next eligible issue:
- **skip it**, continue with later non-security issues whose dependencies are met
  ("skip ahead, circle back"),
- and surface it to the human for explicit approval before it is built.
Dependents of a skipped security issue wait until it is approved, built, and merged.

## Stop conditions
- Backlog empty (all `build-loop` issues closed) → report completion.
- Only `security` issues remain → request approval, then halt.
- A CI failure that can't be resolved by fix-forward → stop and report.

## Definition of "green" (CI)
`.github/workflows/ci.yml` runs ruff + mypy + pytest on every PR. `master` is
branch-protected to require the `ci` check, so auto-merge cannot land a red PR.
