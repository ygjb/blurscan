# blurscan — Manual Testing Guide

A hands-on checklist to exercise every blurscan feature and confirm it works. Work top to
bottom; later sections assume the setup from §0. Each test states **what to do**, the
**expected result**, and a checkbox to mark pass/fail.

> Companion doc: see [MANUAL.md](MANUAL.md) for what each feature is supposed to do.

---

## 0. Setup

### 0.1 Install

```bash
cd /home/yvan/projects/image_analyzer
pip install -e ".[dev]"     # core + test tooling
pip install -e ".[ml]"      # only if you want to test the ml method (§3)
which exiftool || echo "exiftool MISSING — §6 tag tests will be skipped"
```

- [ ] `blurscan --help` prints usage with the four option groups (detection, output,
  actions, review). **No traceback.**

### 0.2 Build a test corpus

You need a directory with a mix of blurry and sharp images, ideally across formats. Two
options:

**Option A — use the bundled samples / corpus builder:**

```bash
ls test_samples/                 # repo-bundled fixtures
ls scripts/                      # corpus builder utilities, if present
```

**Option B — make a scratch corpus by hand:**

```bash
export TC="/tmp/blurscan_test"
rm -rf "$TC" && mkdir -p "$TC/sub"
# Copy in a handful of known-sharp and known-blurry photos.
# Put at least one image inside $TC/sub to verify recursion.
cp /path/to/sharp1.jpg /path/to/blurry1.jpg "$TC/"
cp /path/to/sharp2.png "$TC/sub/"
```

Aim to include: at least one obviously **sharp** photo, one obviously **blurry** photo, one
photo in a **subdirectory** (recursion check), and — if available — a **HEIC** and a **RAW**
file. To test error handling, also drop in a junk file:

```bash
printf 'not an image' > "$TC/broken.jpg"
```

- [ ] `$TC` contains a known mix of sharp + blurry images, at least one in a subfolder.

### 0.3 Sanity: the automated suite still passes

```bash
pytest -q && ruff check . && mypy blurscan
```

- [ ] All three pass clean (good baseline before manual testing).

---

## 1. Basic scan & summary output

### 1.1 Bare scan (report-only default)

```bash
blurscan "$TC"
```

- [ ] Prints `Scanned N images — blurry: X, borderline: Y, sharp: Z` (counts look sane).
- [ ] Lists flagged images **blurriest-first** with class, score, and path.
- [ ] If more than 10 flagged, shows `… and N more (use -v to list all)`.
- [ ] **Nothing is created or modified** in `$TC` except a new `.blurscan_cache/` dir.
- [ ] `broken.jpg` appears classified `blurry` with an error note, and the summary shows
  `errors: 1`.

### 1.2 Verbose listing

```bash
blurscan "$TC" -v
```

- [ ] **Every** flagged image is listed (no "… and N more" truncation).

### 1.3 Recursion

- [ ] The image you placed in `$TC/sub/` appears in the results (scan is recursive).

### 1.4 Error handling for bad path

```bash
blurscan "$TC/sharp1.jpg"      # a file, not a directory
echo "exit=$?"
```

- [ ] Prints `error: not a directory: …` to stderr and exits with code **2**.

### 1.5 No-args help

```bash
blurscan; echo "exit=$?"
```

- [ ] Prints help and exits **0** (no error).

---

## 2. Detection methods (`--method`)

### 2.1 Laplacian (default)

```bash
blurscan "$TC" --method laplacian -v
```

- [ ] Known-blurry images rank at/near the top (lowest scores).
- [ ] Known-sharp images are classified `sharp`.

### 2.2 Motion

```bash
blurscan "$TC" --method motion -v
```

- [ ] Runs without error; scores are on a **different (larger) scale** than laplacian
  (motion floor is ~1000 vs laplacian ~100).
- [ ] If you have a panning/motion-blur shot, it should rank worse here than under
  laplacian.

### 2.3 Invalid method rejected

```bash
blurscan "$TC" --method bogus; echo "exit=$?"
```

- [ ] argparse rejects it with a "choose from …" error and a non-zero exit.

---

## 3. ML method (optional — only if `[ml]` installed)

```bash
blurscan "$TC" --method ml -v
```

- [ ] If torch/torchvision are installed: runs and produces scores in the **0–100** range.
- [ ] If `[ml]` is **not** installed: `ml` is not even offered as a `--method` choice
  (argparse error) — confirming the optional dependency gating.

---

## 4. Threshold tuning

### 4.1 Inspect raw scores

```bash
blurscan "$TC" --json | head -40
```

- [ ] Valid JSON array; each object has `path`, `score_max_tile`, `score_global`,
  `fft_ratio`, `classification`, `method`, `error`.
- [ ] `--json` **suppresses** the human summary (only JSON is printed).

### 4.2 Absolute threshold

```bash
blurscan "$TC" --threshold 1 -v       # almost everything becomes sharp
blurscan "$TC" --threshold 100000 -v  # almost everything becomes blurry
```

- [ ] A very low floor → counts shift heavily to `sharp`.
- [ ] A very high floor → counts shift heavily to `blurry`.
- [ ] Confirms `--threshold` overrides the method default.

### 4.3 Borderline band

- [ ] With a moderate `--threshold`, some images land in `borderline` (the 25% band just
  above the floor).

### 4.4 Adaptive mode

```bash
blurscan "$TC" --adaptive -v          # default 10%
blurscan "$TC" --adaptive 50 -v       # bottom 50%
```

- [ ] `--adaptive` (no number) flags roughly the bottom **10%** as borderline.
- [ ] `--adaptive 50` flags about half the run as at-least-borderline.
- [ ] Adaptive **never** turns a `blurry` image into something cleaner (it only promotes
  `sharp` → `borderline`).

---

## 5. Scoring options

### 5.1 Grid size

```bash
blurscan "$TC" --grid 2 -v
blurscan "$TC" --grid 8 -v
```

- [ ] Both run cleanly; scores shift with grid size (finer grid can find a sharper tile).

### 5.2 Working size

```bash
blurscan "$TC" --working-size 400 -v
blurscan "$TC" --working-size 2000 -v
```

- [ ] Both run; smaller is faster, larger is slower / more sensitive to fine detail.

### 5.3 Jobs / parallelism

```bash
blurscan "$TC" --no-cache --jobs 1     # serial
blurscan "$TC" --no-cache --jobs 4     # parallel
```

- [ ] Both produce the **same classifications**; `--jobs 4` is faster on a multi-image
  corpus.

---

## 6. RAW handling (only if you have a RAW file in `$TC`)

```bash
blurscan "$TC" --method laplacian -v               # embedded preview (fast, default)
time blurscan "$TC" --no-cache --raw-full -v       # full demosaic (slower)
```

- [ ] The RAW file is scored in both modes.
- [ ] `--raw-full` is noticeably **slower** (full sensor demosaic vs embedded preview).

---

## 7. Caching

### 7.1 Cache is created and reused

```bash
rm -rf "$TC/.blurscan_cache"
time blurscan "$TC"            # cold: scores everything
time blurscan "$TC"            # warm: should be much faster
ls "$TC/.blurscan_cache"
```

- [ ] First run creates `$TC/.blurscan_cache/`.
- [ ] Second run is **markedly faster** (cache hit) with identical results.

### 7.2 Cache invalidation on change

```bash
touch "$TC/sharp1.jpg"        # change mtime
blurscan "$TC"
```

- [ ] Re-scores the touched file (cache key is path+mtime+size) — no stale/incorrect result.

### 7.3 `--no-cache`

```bash
blurscan "$TC" --no-cache
```

- [ ] Re-scores every file regardless of cache (slower than a warm run).

### 7.4 Threshold changes don't need a re-score

```bash
blurscan "$TC" --threshold 50      # warm
blurscan "$TC" --threshold 150     # warm
```

- [ ] Both are fast (scoring cached; only **classification** recomputes per run).

---

## 8. Report action (`--report`)

```bash
blurscan "$TC" --report /tmp/bs_report
```

- [ ] Prints `Wrote /tmp/bs_report.csv and /tmp/bs_report.html`.
- [ ] `/tmp/bs_report.csv` exists; opening it shows one row per image with all score
  columns + `error` (sharp images included, not just flagged ones).
- [ ] `/tmp/bs_report.html` opens in a browser as a **self-contained** gallery
  (thumbnails embedded, blurriest-first, color-coded class badges) with no broken external
  links.
- [ ] Re-running with `--report` over the same path overwrites cleanly.

---

## 9. Quarantine actions (`--copy` / `--move`)

> Use a **disposable copy** of your corpus for `--move` so you don't lose originals.

### 9.1 Copy (reversible)

```bash
rm -rf "$TC/_blurry"
blurscan "$TC" --copy "$TC/_blurry" -v
ls "$TC/_blurry"
```

- [ ] Prints `copy N flagged image(s) to …` and (with `-v`) lists each `src -> dst`.
- [ ] `$TC/_blurry/` contains the **blurry** images; originals are **still in place**.
- [ ] Borderline images are **not** copied (default scope).

### 9.2 Include borderline

```bash
rm -rf "$TC/_blurry2"
blurscan "$TC" --copy "$TC/_blurry2" --include-borderline -v
```

- [ ] Now **blurry + borderline** images are copied (more files than §9.1).

### 9.3 Collision-safe names

```bash
# Ensure two same-named files exist in different folders, then:
blurscan "$TC" --copy "$TC/_blurry3" -v
ls "$TC/_blurry3"
```

- [ ] Two source files with the same basename land as distinct names (e.g. `IMG_1.jpg`,
  `IMG_1_1.jpg`) — no silent overwrite.

### 9.4 Dry-run copy/move

```bash
blurscan "$TC" --move "$TC/_gone" --dry-run -v
ls "$TC/_gone" 2>/dev/null || echo "nothing created (correct)"
```

- [ ] Output is prefixed `[dry-run] would move …` and lists each `src -> dst`.
- [ ] **No** `_gone` directory is created; originals untouched.

### 9.5 Move (destructive — use a disposable copy)

```bash
cp -r "$TC" /tmp/blurscan_move_test
blurscan /tmp/blurscan_move_test --move /tmp/blurscan_move_test/_blurry -v
```

- [ ] Flagged images are **moved** (gone from their original location, present in
  `_blurry`).

### 9.6 `--copy` and `--move` are mutually exclusive

```bash
blurscan "$TC" --copy a --move b; echo "exit=$?"
```

- [ ] argparse rejects using both at once with a non-zero exit.

---

## 10. Tag action (`--tag`) — requires exiftool

> Skip this section if `exiftool` is not installed. Use a disposable copy of the corpus.

### 10.1 exiftool missing path

If exiftool is **not** on PATH:

```bash
blurscan "$TC" --tag; echo "exit=$?"
```

- [ ] Prints an error about exiftool and exits with code **3**.

### 10.2 Dry-run tag

```bash
blurscan "$TC" --tag --dry-run -v
```

- [ ] Prints `[dry-run] would tag N flagged image(s) via exiftool` and shows the exact
  `exiftool …` invocations.
- [ ] **No files modified, no sidecars created.**

### 10.3 Tag a JPEG/PNG (in place metadata)

```bash
cp -r "$TC" /tmp/blurscan_tag_test
blurscan /tmp/blurscan_tag_test --tag -v
exiftool -XMP:Subject -Rating /tmp/blurscan_tag_test/<a-flagged>.jpg
```

- [ ] A flagged image now carries an XMP keyword `blurscan:blurry` (or `:borderline`) and
  a star **rating** (blurry=1, borderline=2). Pixels unchanged.

### 10.4 RAW → sidecar (default) vs in-place

```bash
# With a RAW file present in the disposable copy:
blurscan /tmp/blurscan_tag_test --tag -v
ls /tmp/blurscan_tag_test/*.xmp          # sidecar(s) created
blurscan /tmp/blurscan_tag_test --tag --raw-inplace -v
```

- [ ] Default run writes an **XMP sidecar** next to the RAW (RAW file byte-unchanged).
- [ ] `--raw-inplace` writes the tag into the RAW file itself instead.

---

## 11. Combined actions

```bash
cp -r "$TC" /tmp/blurscan_combo
blurscan /tmp/blurscan_combo --report /tmp/combo --copy /tmp/blurscan_combo/_b --tag --dry-run -v
```

- [ ] Report is written (report is not gated by dry-run), and copy + tag are both reported
  as `[dry-run] would …` with no filesystem changes from the actions.
- [ ] Confirms actions compose in a single run.

---

## 12. Review UI (`--review`)

### 12.1 Launch & load

```bash
blurscan "$TC" --review --port 8765
```

- [ ] Console prints `blurscan review UI: http://127.0.0.1:8765/  (Ctrl-C to stop)`.
- [ ] Browser opens automatically to that URL.
- [ ] Header shows counts (`N images — blurry X, borderline Y, sharp Z`).
- [ ] Gallery shows thumbnails, **blurriest-first**, each with a class badge + score.

### 12.2 `--no-open`

```bash
blurscan "$TC" --review --port 8765 --no-open
```

- [ ] URL is printed but **no browser opens**; pasting the URL manually loads the UI.

### 12.3 Filters

In the UI, change the filter dropdown through `flagged`, `blurry`, `borderline`, `all`.

- [ ] `flagged` = blurry + borderline; `blurry`/`borderline` narrow further; `all` shows
  every scanned image.

### 12.4 Detail view & stats

Click any thumbnail.

- [ ] Larger preview loads, with stats: class, method, score, global score, fft ratio,
  decision.

### 12.5 Heatmap toggle

In the detail view press `h` (laplacian or motion method).

- [ ] A per-tile heatmap overlay appears; pressing `h` again returns to the plain preview.
- [ ] For `--method ml`, the heatmap toggle has **no effect** (no tile grid) — and the UI
  doesn't error.

### 12.6 Keyboard decisions & auto-advance

In the detail view press `k`, `x`, `t` on successive images, and `←`/`→` to navigate,
`Esc` to close.

- [ ] `k`=keep, `x`=quarantine, `t`=tag; after each, the view **auto-advances** to the next
  image.
- [ ] Decided cards in the gallery show a decision tag/highlight.
- [ ] `←`/`→` move between images; `Esc` closes the detail view.

### 12.7 Persistent / resumable decisions

Stage a few decisions, stop the server (Ctrl-C or **Done**), then relaunch:

```bash
blurscan "$TC" --review --port 8765
```

- [ ] Previously staged decisions are **restored** (they survived the restart).
- [ ] Running with `--no-cache --review` does **not** persist decisions across restarts
  (persistence is tied to the cache dir).

### 12.8 Apply (use a disposable corpus)

```bash
cp -r "$TC" /tmp/blurscan_review && blurscan /tmp/blurscan_review --review --port 8766
```

Stage some `quarantine` and `tag` decisions, then click **Apply**.

- [ ] A dialog reports `quarantined N, tagged M`.
- [ ] Quarantined images appear under `/tmp/blurscan_review/_blurscan_quarantine/`.
- [ ] Tagged images carry the XMP tag (if exiftool present; otherwise the dialog reports a
  tag error gracefully).

### 12.9 Dry-run review

```bash
blurscan "$TC" --review --dry-run --port 8767
```

- [ ] A **dry-run banner** is visible in the UI.
- [ ] Clicking **Apply** reports `[dry-run] …` and changes nothing on disk.

### 12.10 Shutdown

- [ ] Clicking **Done** stops the server (the `blurscan` process exits); Ctrl-C also stops
  it cleanly.

### 12.11 Security spot-checks (optional)

```bash
# Decision without the per-run token should be rejected:
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8765/api/decision \
  -H 'Content-Type: application/json' -d '{"id":"0","decision":"tag"}'
```

- [ ] Returns **403** without the `X-Blurscan-Token` header (state-changing endpoints are
  token-protected).
- [ ] `GET /api/thumb/<id>` only works for ids the server minted; there is no way to pass a
  filesystem path (opaque-id design).

---

## 13. Regression wrap-up

```bash
pytest -q && ruff check . && mypy blurscan
```

- [ ] Full automated suite still green after all the manual poking.

### Cleanup

```bash
rm -rf /tmp/blurscan_* /tmp/bs_report.* /tmp/combo.*
rm -rf "$TC/.blurscan_cache" "$TC/_blurry"*
```

---

## Coverage checklist (every feature touched)

- [ ] Scan + summary (§1) · verbose (§1.2) · recursion (§1.3) · bad-path exit 2 (§1.4)
- [ ] Methods: laplacian (§2.1) · motion (§2.2) · ml (§3) · invalid rejected (§2.3)
- [ ] Threshold (§4.2) · borderline band (§4.3) · adaptive (§4.4) · `--json` (§4.1)
- [ ] `--grid` (§5.1) · `--working-size` (§5.2) · `--jobs` (§5.3)
- [ ] RAW preview vs `--raw-full` (§6)
- [ ] Cache create/reuse/invalidate/`--no-cache` (§7)
- [ ] `--report` CSV + HTML (§8)
- [ ] `--copy`/`--move`, `--include-borderline`, collision-safe, `--dry-run`, mutual-exclusion (§9)
- [ ] `--tag`, `--raw-inplace`, exiftool-missing exit 3, dry-run (§10)
- [ ] Combined actions (§11)
- [ ] Review: launch/`--port`/`--no-open`/filters/detail/heatmap/keys/persistence/apply/dry-run/shutdown/security (§12)
