# Corpus review

Staged from Openverse (Creative-Commons / public-domain). 100 `blurry` + 100
`not_blurry` candidates, auto-screened with the project's own blur metrics
(Laplacian variance + FFT high-frequency ratio), calibrated against the existing
hand-labeled `test_samples/` set.

## How to review

1. Open the contact sheets in `contact_sheets/`:
   - `not_blurry__confident.jpg` (75) — high quality, skim for any soft ones.
   - `not_blurry__review.jpg` (25) — sharp subjects on low-texture/dark
     backgrounds that scored low; mostly keepers.
   - `blurry__confident.jpg` (54) — motion blur / defocus / bokeh; reject any
     with a clearly **sharp subject**.
   - `blurry__review.jpg` (46) — genuine mixed bag, needs the most attention.
2. Note the short id printed under each thumb. Add ids to drop in `rejects.txt`
   (one per line; `#` comments allowed).
3. Run `python scripts/finalize_corpus.py` to delete rejects and rewrite the
   manifest + attribution. Add `--promote` to copy keepers into
   `test_samples/<label>/` (prefixed `web_`).

## Notes

- `manifest.csv` has per-image scores, license, creator, and source URL.
- `ATTRIBUTION.md` is the credits file — keep it with any redistribution.
- The single-metric overlap on the existing set was large (blurry 12–257, sharp
  112–543), which is exactly why your eyes are the final label authority.
