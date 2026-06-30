# blurscan — Design Document

A Python CLI tool that scans a photo collection, scores each image's sharpness,
classifies blurry images while sparing intentional shallow-depth-of-field shots,
and acts on the results: report, quarantine, tag, or review in a local web UI.

- **Status:** design / pre-implementation
- **Language:** Python 3.11+
- **Author:** yvanboily@gmail.com
- **Date:** 2026-06-29

---

## 1. Goals & non-goals

### Goals
- Identify blurry images in a personal photo collection (target < 5,000 images).
- Minimize false positives on artistic blur (shallow DoF portraits, motion blur).
- Support JPEG/PNG, HEIC/HEIF, and camera RAW.
- Offer four independent, flag-selected actions: **report**, **quarantine**
  (copy/move), **tag** (EXIF/XMP via exiftool), and **review** (local web UI).
- Be safe by default: report-only unless an action flag is passed; copy over move;
  `--dry-run` honored by every destructive action.

### Non-goals (v1)
- Machine-learning / trained blur classifiers (revisit only if heuristics fall short).
- Cloud processing, multi-machine distribution, or GPU acceleration.
- Editing or deblurring images. The tool classifies and organizes; it never alters pixels.
- Duplicate detection, face detection, or general photo culling (possible future scope).

---

## 2. Detection approach

### 2.1 Core metric — tiled variance-of-Laplacian

The classic cheap sharpness signal is the **variance of the Laplacian**: convolve the
grayscale image with a Laplacian kernel and take the variance of the response. Sharp
images carry lots of high-frequency edge energy → high variance; blurry images → low.

A single **global** score wrongly flags shallow-DoF photos (sharp subject, soft
background) because the soft regions drag the average down. To avoid that:

1. **Decode** the image (format-aware, see §3.2).
2. **Downscale** to a consistent working size — longest edge ≈ 1000px. This normalizes
   scores across resolutions and bounds runtime.
3. **Grayscale** convert.
4. **Tile** into an `N × N` grid (default 4×4 = 16 tiles).
5. Compute variance-of-Laplacian **per tile**.
6. The image's sharpness score = the **maximum tile score** (the sharpest region).
   - Rationale: a good portrait has at least one tack-sharp tile (the eye) → high score
     → not flagged. A genuinely blurry frame has *no* sharp tile anywhere → low score
     → flagged.

### 2.2 Secondary signals (reported, not decisive in v1)
- **Global variance-of-Laplacian** — for comparison / debugging.
- **FFT high-frequency ratio** — fraction of spectral energy above a cutoff; a second
  opinion robust to different content. Logged in the report; can be promoted to a
  decision input later.

### 2.3 Classification & thresholds
Absolute thresholds do not transfer across cameras and collections, so we use a hybrid:

- **Absolute floor** (`--threshold`, default tuned ≈ 100 on the max-tile metric):
  anything below is **blurry**.
- **Adaptive mode** (`--adaptive [PCT]`): additionally flag the bottom `PCT`% of the
  collection as **soft/borderline**, relative to this run's score distribution.
- A **borderline band** just above the floor is surfaced for review rather than
  auto-actioned.

Every report row includes the raw scores so thresholds can be recalibrated empirically
on the user's own library.

**Output classes:** `sharp` · `borderline` · `blurry`.

---

## 3. Architecture

### 3.1 Module layout
```
blurscan/
  __init__.py
  cli.py            # argparse; maps flags → pipeline config
  pipeline.py       # walk → load → score → classify → act; parallelized
  loader.py         # format-aware decode (Pillow + pillow-heif + rawpy)
  metrics.py        # tiled Laplacian, global Laplacian, FFT ratio, scoring
  classifier.py     # threshold + adaptive percentile → class
  cache.py          # SQLite cache keyed on path+mtime+size
  models.py         # dataclasses: ImageResult, ScanConfig
  actions/
    __init__.py
    report.py       # CSV + standalone HTML report w/ thumbnails
    quarantine.py   # copy/move w/ dry-run + collision handling
    tag.py          # exiftool-driven EXIF/XMP keyword + rating
    review/         # local web review server (see §4)
      server.py     # HTTP API + static host
      static/       # SPA: index.html, app.js, styles.css
  thumbs.py         # thumbnail generation/caching, shared by report + review
```

### 3.2 Format support (`loader.py`)
| Format        | Decoder                         | Notes |
|---------------|---------------------------------|-------|
| JPEG/PNG/TIFF | Pillow                          | built-in |
| HEIC/HEIF     | `pillow-heif`                   | registers a Pillow opener |
| Camera RAW    | `rawpy` (libraw)                | default: decode embedded JPEG **preview** (fast). `--raw-full` demosaics the sensor data (slow, rarely needed for blur scoring). |

A single `load_image(path) -> np.ndarray` returns a normalized RGB array; the rest of
the pipeline is format-agnostic.

### 3.3 Processing pipeline (`pipeline.py`)
1. **Walk** `SCAN_PATH` for supported extensions (respecting `--formats`).
2. For each file, check the **cache**; skip if `path + mtime + size` unchanged.
3. **Load → score → classify** (CPU-bound work in a `ProcessPoolExecutor`,
   `--jobs` workers, default = CPU count).
4. Persist results to cache.
5. Hand the full result set to each requested **action**.

For < 5k images this completes in a couple of minutes; RAW-heavy sets are dominated by
decode time, mitigated by the preview-decode default.

### 3.4 Data model (`models.py`)
```python
@dataclass
class ImageResult:
    path: Path
    width: int
    height: int
    score_max_tile: float      # primary decision metric
    score_global: float        # secondary
    fft_ratio: float           # secondary
    classification: str        # "sharp" | "borderline" | "blurry"
    error: str | None = None   # decode/IO failures recorded, not fatal
```

---

## 4. Local web review UI

Selected approach: a **local web server** (Flask) that opens in the browser. No data
leaves the machine; it binds to `127.0.0.1` on an ephemeral port and prints/opens the URL.

### 4.1 Launch
- `blurscan SCAN_PATH --review` runs a scan (or loads cached results) and starts the server.
- `--port` to pin a port; otherwise auto-select. `--no-open` to skip auto-launching the browser.
- Server shuts down on Ctrl-C; a "Done" button in the UI also triggers shutdown.

### 4.2 Features
- **Grid gallery** of flagged + borderline images, sorted by score (blurriest first),
  each thumbnail showing its sharpness score and class badge.
- **Filters:** by class (blurry / borderline / all), by score range, by folder.
- **Detail view:** click a thumbnail for a larger preview, full metric breakdown
  (max-tile, global, FFT), per-tile heatmap overlay showing *where* the sharp regions are,
  and EXIF basics (camera, lens, shutter — useful to spot motion blur).
- **Per-image decisions:** mark **Keep**, **Quarantine**, or **Tag**. Keyboard shortcuts
  (`k` keep, `x` quarantine, `t` tag, arrows to navigate) for fast triage.
- **Bulk actions:** select-all-in-filter → apply a decision to the whole set.
- **Apply & commit:** decisions are staged in the browser; an **Apply** button POSTs them
  to the server, which executes the corresponding quarantine/tag actions (honoring
  `--dry-run`). A summary of what changed is shown.
- **Resumable:** decisions persist to the cache DB, so closing and reopening the review
  session keeps prior choices.

### 4.3 API surface (`server.py`)
| Method & path             | Purpose |
|---------------------------|---------|
| `GET /api/results`        | JSON list of `ImageResult`s (+ current decision state) |
| `GET /api/thumb/<id>`     | Thumbnail bytes (cached) |
| `GET /api/image/<id>`     | Full-size preview bytes |
| `GET /api/heatmap/<id>`   | Per-tile sharpness overlay |
| `POST /api/decision`      | Stage a decision for one image |
| `POST /api/apply`         | Execute all staged decisions (or dry-run) |
| `POST /api/shutdown`      | Graceful server stop |

Frontend is a small vanilla-JS single-page app (no build step) served from `static/`,
keeping the dependency footprint to Flask only.

---

## 5. Metadata tagging (`actions/tag.py`)

Uses **exiftool** (external binary, the gold standard for format/sidecar coverage incl.
RAW and HEIC) invoked via `subprocess`:

- Writes an XMP keyword (e.g. `blurscan:blurry`) and optionally a low star rating
  (`-XMP:Rating=1`) so Lightroom / digiKam / Apple Photos can filter on it.
- For RAW, writes to an **XMP sidecar** by default (never touches the original RAW),
  configurable via `--raw-sidecar/--raw-inplace`.
- Batched through a single persistent `exiftool -stay_open` process for speed.
- Startup check verifies `exiftool` is on `PATH`; clear error + install hint if missing.
- Fully non-destructive to pixels; respects `--dry-run` (prints the commands it would run).

---

## 6. CLI reference

```
blurscan SCAN_PATH [options]

Detection:
  --threshold FLOAT     Absolute sharpness floor (default ~100)
  --adaptive [PCT]      Also flag bottom PCT% of collection (default 10)
  --grid N              Tiles per side (default 4)
  --working-size PX     Downscale longest edge before analysis (default 1000)
  --raw-full            Demosaic full RAW instead of embedded preview

Actions (combine freely; default = report only):
  --report PATH         Write CSV + HTML report w/ thumbnails
  --copy DIR            Copy flagged images to DIR (reversible)
  --move DIR            Move flagged images to DIR
  --tag                 Write XMP keyword + rating via exiftool
  --raw-sidecar/--raw-inplace   Where RAW tags go (default: sidecar)
  --review              Launch local web review UI
  --port N / --no-open  Review server options

Performance / safety:
  --jobs N              Parallel workers (default = CPU count)
  --cache / --no-cache  Skip unchanged files on rerun (default on)
  --dry-run             Show actions without changing anything
  --formats EXT...      Restrict to given extensions
  -v / --json           Verbose / machine-readable output
```

---

## 7. Dependencies
- **Runtime (Python):** `opencv-python-headless`, `numpy`, `pillow`, `pillow-heif`,
  `rawpy`, `flask`.
- **External binary:** `exiftool` (required only for `--tag`).
- **Dev:** `pytest`, `ruff`, `mypy`.
- Packaged with a `pyproject.toml`; console entry point `blurscan = blurscan.cli:main`.

---

## 8. Testing strategy

### 8.1 Two-tier fixtures (synthetic gates CI; real images validate locally)
- **Synthetic, always-run (the CI gate):** programmatically generated images — a sharp
  checkerboard vs. a Gaussian-blurred copy, a half-sharp/half-blurred frame — so the
  merge gate never depends on any uncommitted file.
- **Real labeled images, local-only:** a `test_samples/` directory (gitignored, **not**
  committed) holding the user's own examples:
  - `test_samples/blurry/` — every image expected to classify as **blurry**.
  - `test_samples/not_blurry/` — every image expected to classify as **sharp**.
  Tests over these are guarded with `@pytest.mark.skipif(...)` on the directory's
  presence: they run during local development and **skip cleanly in CI** (where
  `test_samples/` is absent). A shared `conftest.py` fixture discovers and yields the
  labeled paths.

### 8.2 Coverage
- **Unit:** `metrics.py` against the synthetic images — order (sharp > blurred) and
  max-tile behavior (half/half scores high). Locally, also assert every
  `test_samples/blurry/*` scores below and every `test_samples/not_blurry/*` above the
  default threshold.
- **Loader:** round-trip a small JPEG, PNG, HEIC, and RAW fixture (synthetic/generated
  where possible; HEIC/RAW guarded like the real set if a committed fixture isn't viable).
- **Classifier:** threshold and adaptive-percentile boundary cases (synthetic).
- **Actions:** quarantine collision handling and dry-run (no filesystem changes);
  tag.py with a mocked exiftool process.
- **Review API:** endpoint smoke tests with Flask's test client.

---

## 9. Milestones / build order
1. **Core scan + report** — loader (JPEG/PNG), metrics, classifier, CSV/HTML report.
   *Runnable end-to-end on day one.*
2. **Formats** — add pillow-heif + rawpy; preview-decode default.
3. **Quarantine + tag** — copy/move with dry-run; exiftool tagging.
4. **Performance** — parallelism + SQLite cache.
5. **Web review UI** — server, API, SPA, heatmap, decisions, apply.
6. **Polish** — tests, packaging, README, threshold-tuning guidance.

---

## 10. Risks & open questions
- **Threshold calibration** is collection-specific; mitigated by always reporting raw
  scores and offering adaptive mode. May warrant a `--calibrate` helper that samples the
  library and suggests a floor.
- **RAW preview quality** varies by camera; the `--raw-full` escape hatch covers the rare
  case where the embedded preview is too small to score reliably.
- **Motion blur vs. soft focus** are not distinguished in v1; the review UI's EXIF
  (shutter speed) display lets a human make that call.
- **Heuristic ceiling:** if false-positive/negative rates disappoint on real data, the
  next step is a lightweight trained classifier — explicitly deferred from v1.
```

---

## 11. Effort estimate

### Human developer (competent Python dev, familiar with the libraries)
| Milestone | Estimate |
|-----------|----------|
| 1. Core scan + report | 1–1.5 days |
| 2. Formats (HEIC/RAW) | 0.5 day |
| 3. Quarantine + tag (exiftool) | 1 day |
| 4. Parallelism + cache | 0.5–1 day |
| 5. Web review UI (server + SPA + heatmap) | 2–3 days |
| 6. Tests, packaging, docs | 1–1.5 days |
| **Total** | **~6–8.5 working days** (1.5–2 weeks calendar) |

The web UI dominates; it's roughly a third of the effort. The detection core is small
and well-trodden.

### Claude (this project, with you reviewing/steering)
| Milestone | Estimate |
|-----------|----------|
| 1. Core scan + report | 15–25 min |
| 2. Formats | 10 min |
| 3. Quarantine + tag | 20–30 min |
| 4. Parallelism + cache | 15–20 min |
| 5. Web review UI | 45–75 min |
| 6. Tests, packaging, docs | 20–30 min |
| **Total active build** | **~2.5–3.5 hours** |

Caveats on the Claude estimate: this is hands-on-keyboard time, not wall-clock — add
your review cycles between milestones. The realistic gating factors aren't code
generation but **environment-dependent verification**: installing `rawpy`/`pillow-heif`
(which pull native libraries), getting real HEIC/RAW test fixtures, confirming `exiftool`
behavior on your actual files, and tuning the threshold against *your* photos. Those are
iterative and depend on your collection, so budget a few extra rounds beyond the figures
above.

Net: roughly a **10–20× speedup on raw build time** — and beyond speed, it saves the
research into which libraries to use and design tricks like the max-tile metric.
