# blurscan — User Manual

blurscan scans a directory of photos, scores each image's sharpness, and flags the
blurry ones — while trying to spare intentional shallow-depth-of-field shots. Flagged
images can be **reported**, **quarantined** (copy/move), **tagged** (XMP via exiftool),
or **triaged** in a local web UI.

blurscan is **report-only by default**: a bare scan changes nothing on disk. Files are
only created, moved, or modified when you pass an action flag, and every destructive
action honors `--dry-run`.

---

## 1. Installation

```bash
pip install -e .            # core: numpy, opencv, pillow, pillow-heif, rawpy, flask
pip install -e ".[ml]"      # adds the learned `ml` detector (torch + torchvision)
pip install -e ".[dev]"     # ruff + mypy + pytest (for development)
```

- Requires **Python ≥ 3.11**.
- The `--tag` action additionally requires **exiftool** on your `PATH`:
  - Debian/Ubuntu: `apt install libimage-exiftool-perl`
  - macOS: `brew install exiftool`
- Installation registers a console command named `blurscan`.

Verify the install:

```bash
blurscan --help
```

Running `blurscan` with no arguments prints the help text and exits 0.

---

## 2. Command structure

blurscan is a **single command** (no subcommands). The general form is:

```bash
blurscan <SCAN_PATH> [detection options] [output options] [action options] [review options]
```

`SCAN_PATH` is a directory to scan (recursively). If it is not a directory, blurscan
prints `error: not a directory: <path>` and exits with code `2`.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success (also: help printed when run with no arguments) |
| `2` | `SCAN_PATH` is not a directory |
| `3` | `--tag` was requested but exiftool was not found on `PATH` |

---

## 3. What gets scanned (input formats)

blurscan walks `SCAN_PATH` recursively and decodes any file with a supported extension:

- **Standard raster (Pillow):** `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`, `.webp`
- **HEIC/HEIF (pillow-heif):** `.heic`, `.heif`
- **Camera RAW (rawpy):** `.cr2`, `.cr3`, `.nef`, `.arw`, `.dng`, `.raf`, `.rw2`, `.orf`, `.pef`, `.srw`

Files that fail to decode are not dropped — they appear in results with an `error`
message and are classified `blurry` so they surface for review rather than being silently
skipped.

By default, RAW files are scored from their **embedded preview** (fast). See
`--raw-full` to demosaic the full sensor instead.

---

## 4. How scoring and classification work

Each image receives a **sharpness score** (higher = sharper). The score scale depends on
the method, so thresholds are **not comparable across methods** (see §5 and §10).

Three scores are recorded per image:

- `score_max_tile` — the **primary** decision metric: the sharpest tile's score (max over
  the tile grid). This is what classification and ranking use.
- `score_global` — a whole-image secondary signal.
- `fft_ratio` — a frequency-domain secondary signal (shown in the review UI).

Each image is classified into one of three labels using the active threshold *floor*:

| Class | Condition |
|-------|-----------|
| `blurry` | `score < floor` |
| `borderline` | `floor ≤ score < floor × 1.25` (a 25% band above the floor) |
| `sharp` | `score ≥ floor × 1.25` |

The **floor** is the method's `default_threshold` unless you override it with
`--threshold` (see §10 for defaults). Adaptive mode (`--adaptive`) can additionally
promote the bottom slice of a run to `borderline` — but it never upgrades a `blurry`
call.

By default, actions operate on **blurry only**. Add `--include-borderline` to also act on
borderline images.

---

## 5. Detection methods — `--method`

```
--method {laplacian,motion,ml}   (default: laplacian)
```

| Method | How it works | ROC-AUC* | Best for |
|--------|--------------|----------|----------|
| `laplacian` (default) | Tiled **max** variance-of-Laplacian (the sharpest region wins) | 0.93 | General / out-of-focus blur |
| `motion` | Orientation-aware: energy in the weakest gradient direction | 0.87 | Residual subject **motion / panning** blur |
| `ml` | Frozen MobileNetV3 features + logistic head (requires `[ml]` extra) | 0.95 | Content-specific blur; best overall |

\* On the bundled Creative-Commons test corpus.

The `ml` method only appears in `--method` choices when `torch`/`torchvision` are
installed (`pip install -e ".[ml]"`). For `ml`, the score is `p(sharp) × 100`, so a floor
of `50` ≈ a 50% sharp probability.

---

## 6. Detection / scoring options

| Flag | Default | Effect |
|------|---------|--------|
| `--method {laplacian,motion,ml}` | `laplacian` | Detection method (see §5). |
| `--threshold N` | method-specific | Absolute sharpness floor. Overrides the method default. |
| `--adaptive [PCT]` | off | Also flag the bottom `PCT`% of *this run's* distribution as borderline. `PCT` defaults to `10` when the flag is given without a number. |
| `--grid N` | `4` | Tiles per side (an N×N grid) for tiled scoring. |
| `--working-size N` | `1000` | Downscale the longest edge to N px before analysis (speed/consistency). |
| `--raw-full` | off | Demosaic full RAW sensor data instead of the embedded preview (slower, more faithful). |
| `--no-cache` | off | Disable the on-disk result cache; re-score every file. |
| `--jobs N` | CPU count | Number of parallel worker processes. |

**Caching:** Results are cached on disk under `<SCAN_PATH>/.blurscan_cache/`, keyed on
path + mtime + size. Reruns only re-score files that changed, so iterating on the
threshold is effectively instant (classification is recomputed every run; only the
expensive scoring is cached). Use `--no-cache` to force a full re-score.

**Parallelism:** Scoring is spread across CPU cores. Use `--jobs 1` to run serially (handy
for debugging or constrained machines).

---

## 7. Output options

These control what blurscan *reports* (they do not modify your photos).

### Default summary (stdout)

With no output flags, blurscan prints a one-line summary plus the **10 blurriest** flagged
images, ranked blurriest-first:

```
Scanned 412 images — blurry: 23, borderline: 8, sharp: 381
  blurry        42.3  /home/me/Photos/IMG_0421.jpg
  blurry        55.1  /home/me/Photos/IMG_0388.jpg
  ...
  … and 21 more (use -v to list all)
```

| Flag | Effect |
|------|--------|
| `-v`, `--verbose` | List **every** flagged image instead of the top 10 (also lists per-file actions for copy/move/tag). |

### `--report PATH`

Writes two files:

- `PATH.csv` — every image with all scores (machine-readable).
- `PATH.html` — a self-contained gallery, blurriest-first (open in any browser).

Example: `blurscan ~/Photos --report report` → `report.csv` + `report.html`, and prints
`Wrote report.csv and report.html`.

### `--json`

Emits the full results list as JSON to stdout (pretty-printed, 2-space indent) and exits.
This **takes precedence** over the human summary and report writing. Each record:

```json
{
  "path": "/home/me/Photos/IMG_0421.jpg",
  "width": 6000,
  "height": 4000,
  "score_max_tile": 42.3,
  "score_global": 38.9,
  "fft_ratio": 0.012,
  "classification": "blurry",
  "method": "laplacian",
  "error": null
}
```

Use `--json` to inspect raw scores when calibrating a threshold (see §10).

---

## 8. Action options

Actions decide what to *do* with flagged images. They can be combined freely (e.g.
`--report` + `--copy` + `--tag` in one run). All destructive actions respect `--dry-run`.

> Note: `--review` and `--json` short-circuit the run. If `--review` is set, blurscan
> launches the UI instead of running copy/move/tag/report. If `--json` is set (and
> `--review` is not), it prints JSON and exits before any action runs.

### Quarantine — `--copy DIR` / `--move DIR`

Mutually exclusive. Relocates flagged images into `DIR`:

- `--copy DIR` — copies (reversible; originals untouched).
- `--move DIR` — moves (originals removed from the library).

Names are made **collision-safe** so two `IMG_1234.jpg` from different folders won't clobber
each other. Prints e.g. `copy 23 flagged image(s) to /path/_blurry`. With `-v` or
`--dry-run`, each `src -> dst` pair is listed.

```bash
blurscan ~/Photos --copy ~/Photos/_blurry           # safe triage pile
blurscan ~/Photos --move ~/Photos/_blurry --dry-run # preview a move
```

### Tag — `--tag`

Writes an XMP keyword `blurscan:<class>` plus a star rating onto each flagged image via
**exiftool**, so Lightroom / digiKam / etc. can filter on it.

- **RAW files** get an **XMP sidecar** by default (the RAW itself is not modified).
- `--raw-inplace` writes the tag into the RAW file itself instead of a sidecar.
- If exiftool is not on `PATH`, blurscan prints an error and exits with code `3`.

Prints e.g. `tag 23 flagged image(s) via exiftool`. With `-v` or `--dry-run`, the exact
exiftool invocations are shown.

```bash
blurscan ~/Photos --tag
blurscan ~/Photos --tag --raw-inplace
blurscan ~/Photos --tag --dry-run         # show the exiftool commands, change nothing
```

### Scope — `--include-borderline`

By default, actions touch only `blurry` images. Add `--include-borderline` to also
copy/move/tag the `borderline` ones.

### Safety — `--dry-run`

Show what every action *would* do — files listed, exiftool commands printed — without
changing anything on disk. Output is prefixed with `[dry-run] would …`.

---

## 9. Review UI — `--review`

```bash
blurscan ~/Photos --review
```

Launches a small local web app for triaging flagged images by hand. It binds **loopback
only** (`127.0.0.1`) on an ephemeral port, prints the URL, and opens your browser.

| Flag | Default | Effect |
|------|---------|--------|
| `--review` | off | Launch the local web review UI (blocks until you stop it). |
| `--port N` | `0` (auto) | Pick a specific port instead of an ephemeral one. |
| `--no-open` | off | Don't auto-open a browser (print the URL only). |

Stop the server with **Ctrl-C**, or click **Done** in the UI.

### What the UI shows

- A header with overall counts (`N images — blurry X, borderline Y, sharp Z`).
- A **filter** dropdown: `flagged` (blurry + borderline), `blurry`, `borderline`, `all`.
- A **gallery** of thumbnails, **blurriest-first**, each with its class badge and score.
- A **dry-run banner** if the scan was started with `--dry-run`.

### Detail view & decisions

Click any thumbnail to open the detail view, which shows a larger preview and the full
stats (class, method, score, global score, fft ratio, current decision). For each image
you stage one of three decisions:

| Decision | Meaning |
|----------|---------|
| `keep` | Leave it alone (the default for every image). |
| `quarantine` | Mark to be copied aside on Apply. |
| `tag` | Mark to be XMP-tagged on Apply. |

#### Keyboard shortcuts (in the detail view)

| Key | Action |
|-----|--------|
| `k` | Decide **keep** (and advance to the next image) |
| `x` | Decide **quarantine** (and advance) |
| `t` | Decide **tag** (and advance) |
| `h` | Toggle the **per-tile heatmap** overlay on the preview |
| `→` | Next image |
| `←` | Previous image |
| `Esc` | Close the detail view |

After a decision, blurscan auto-advances to the next image so you can rip through a queue
with one keypress each.

### Heatmap (`h`)

The heatmap overlays the per-tile sharpness grid so you can see **where** sharpness is
concentrated — useful for confirming a shallow-DOF keeper (sharp subject, soft background)
versus a genuinely soft frame. Heatmaps are available for tile-grid methods (`laplacian`,
`motion`); the `ml` method has no tile grid, so its heatmap endpoint returns nothing and
the toggle has no effect.

### Persistent / resumable decisions

Staged decisions are saved under the scan's cache directory, so if you stop and re-run
`--review` on the same directory, your earlier decisions are **restored** and you can pick
up where you left off. (This persistence is tied to the cache; running with `--no-cache`
disables it.)

### Apply

Click **Apply** to execute all staged decisions at once:

- `quarantine` decisions → images are **copied** into `<SCAN_PATH>/_blurscan_quarantine`.
- `tag` decisions → images are tagged via exiftool (same behavior as `--tag`).

A summary dialog reports how many were quarantined and tagged (and any tag error, e.g.
exiftool missing). If the scan was launched with `--dry-run`, Apply only *reports* what it
would do.

### Security notes

The review server is built to be safe to run on a workstation:

- Binds **127.0.0.1 only** (refuses any non-loopback host).
- Images are addressed by **opaque ids** mapped server-side to scan paths — clients never
  supply filesystem paths, so there is no path traversal.
- State-changing endpoints (`/api/decision`, `/api/apply`, `/api/shutdown`) require a
  **per-run token** header and reject cross-origin requests, so a random web page can't
  drive your local server.

### API endpoints (for reference / scripting)

| Method & path | Purpose |
|---------------|---------|
| `GET /` | The single-page UI. |
| `GET /static/<name>` | Static assets (JS/CSS). |
| `GET /api/results` | All items + the per-run token + dry-run flag. |
| `GET /api/thumb/<id>` | 256px JPEG thumbnail. |
| `GET /api/image/<id>` | ~1400px JPEG preview. |
| `GET /api/heatmap/<id>` | Per-tile heatmap JPEG (404 if the method has no grid). |
| `POST /api/decision` | Stage a decision (`keep`/`quarantine`/`tag`). Token required. |
| `POST /api/apply` | Execute staged decisions. Token required. |
| `POST /api/shutdown` | Stop the server. Token required. |

---

## 10. Tuning the threshold

Thresholds **don't transfer** across methods or collections — each method has its own
scale. Default floors:

| Method | Default floor |
|--------|---------------|
| `laplacian` | `100.0` |
| `motion` | `1000.0` |
| `ml` | `50.0` (≈ p(sharp)=0.5) |

Recommended workflow:

1. **Look at the scores first.** Run `blurscan DIR --json` (or read the CSV report) and
   sort by `score_max_tile`. Find the "knee" where blurry gives way to sharp.
2. **Set an absolute floor** with `--threshold N` once you've found that knee.
3. **Or go relative** with `--adaptive [PCT]` — flags the bottom `PCT`% of *this run* as
   borderline (default 10%). This is the most robust mode when a method ranks well but no
   single cut separates cleanly. It never overrides a hard `--threshold` blurry call.
4. **Re-run freely.** Scoring is cached, so iterating on the threshold is instant
   (classification is recomputed each run).

```bash
blurscan ~/Photos --json | less                       # inspect raw scores
blurscan ~/Photos --threshold 80 --report report      # absolute floor
blurscan ~/Photos --adaptive 15 --report report       # bottom 15% as borderline
```

---

## 11. Performance notes

- Scoring is parallelized across CPU cores; tune with `--jobs N`.
- Results are cached under `<SCAN_PATH>/.blurscan_cache/` (path+mtime+size key). Reruns
  only re-score changed files. Delete that directory or pass `--no-cache` to force a clean
  scan.
- RAW files decode the **embedded preview** by default (fast). `--raw-full` demosaics the
  full sensor (slower, occasionally needed for marginal cases).
- `--working-size` controls the analysis resolution (default 1000px longest edge); lower
  is faster, higher is more sensitive to fine detail.

---

## 12. Common recipes

```bash
# Report only — ranked summary + CSV + HTML, nothing modified:
blurscan ~/Photos --report report

# Verbose report listing every flagged file:
blurscan ~/Photos --report report -v

# Motion-blur pass on an action sequence:
blurscan ~/Sports --method motion --report sports

# Best-quality detection (needs the ml extra):
blurscan ~/Photos --method ml --report report

# Safe triage pile (copy, originals untouched):
blurscan ~/Photos --copy ~/Photos/_blurry

# Preview a move without touching anything:
blurscan ~/Photos --move ~/Photos/_blurry --dry-run -v

# Tag flagged images for Lightroom/digiKam (RAW → sidecar):
blurscan ~/Photos --tag

# Tag including borderline, in-place for RAW:
blurscan ~/Photos --tag --include-borderline --raw-inplace

# Interactive triage in the browser:
blurscan ~/Photos --review

# Review on a fixed port, no auto-open (e.g. over SSH tunnel):
blurscan ~/Photos --review --port 8765 --no-open
```
