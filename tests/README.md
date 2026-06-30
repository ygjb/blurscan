# blurscan tests

Run everything from the repo root (with the dev extras installed):

```bash
pip install -e ".[dev]"      # add ".[ml]" to exercise the ml detector locally
pytest -q
ruff check . && mypy blurscan
```

## Fixture strategy (DESIGN.md §8.1)

Two tiers, so the suite is self-contained yet validated on real photos:

- **Synthetic, always-run** — images are generated in-test (checkerboards, Gaussian/
  directional blur). These cover the core invariants and gate CI with no external
  dependency. Most tests use them.
- **Real labeled corpus (download-on-demand)** — Creative-Commons / public-domain images
  described by committed manifests under `test_samples/{web_corpus,raw_corpus,heic_corpus}/`
  (`manifest.csv` + `ATTRIBUTION.md`); the images themselves are **not** committed.
  Reconstruct them with:

  ```bash
  python scripts/fetch_corpus.py            # all corpora -> test_samples/_cache/
  python scripts/fetch_corpus.py raw_corpus # just one
  ```

  Files are verified by sha256 (HEIC is transcoded locally from the CC JPEGs). `conftest.py`
  exposes them via the `blurry_samples` / `sharp_samples` / `raw_corpus_files` /
  `heic_corpus_files` fixtures, which `pytest.skip` when the cache is absent. Real-image
  tests assert a **ranking-quality** bar (median separation + ROC-AUC). Override the cache
  location with `$BLURSCAN_CORPUS_CACHE`.

## Conditional skips

- `blurry_samples` / `sharp_samples` / `raw_corpus_files` / `heic_corpus_files` — skip when
  the corpus cache is absent (fresh clone / CI; run `scripts/fetch_corpus.py` locally).
- Manifest integrity (`test_corpus_manifest.py`) always runs — no network or cache needed.
- **exiftool** round-trip (`test_tag.py`) — skips unless `exiftool` is on PATH.
- **ml** detector feature/scoring tests — skip unless torch is installed (the `[ml]`
  extra). CI does not install it and never downloads model weights.

## Layout

One `test_<module>.py` per source module, plus `test_integration.py` for an end-to-end
CLI run (scan → report → quarantine). 100+ tests; `ruff` + `mypy` are part of the gate.
