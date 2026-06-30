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
- **Real labeled corpus** — a Creative-Commons set committed under
  `test_samples/web_corpus/{blurry,not_blurry}` (see its `ATTRIBUTION.md` /
  `manifest.csv`). `conftest.py` exposes it via the `blurry_samples` / `sharp_samples`
  fixtures, which `pytest.skip` if the corpus is absent. Real-image tests assert a
  **ranking-quality** bar (median separation + ROC-AUC), not perfect separation.

## Conditional skips

- `blurry_samples` / `sharp_samples` — skip when the corpus is missing.
- **RAW** round-trip — skips unless a RAW file exists under `test_samples/` (rawpy is
  read-only; RAW can't be synthesized).
- **exiftool** round-trip (`test_tag.py`) — skips unless `exiftool` is on PATH (installed
  in CI).
- **ml** detector feature/scoring tests — skip unless torch is installed (the `[ml]`
  extra). CI does not install it and never downloads model weights.

## Layout

One `test_<module>.py` per source module, plus `test_integration.py` for an end-to-end
CLI run (scan → report → quarantine). 100+ tests; `ruff` + `mypy` are part of the gate.
