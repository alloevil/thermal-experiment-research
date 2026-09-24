# Public edition: research retained, external full text withheld

The owner explicitly authorized processing third-party material before public release. The public edition retains the complete sequence of original research code, protocols, synthetic data, observations, positive/negative results, tests and recorded runs. It is **not** a mirror of the papers and websites consulted during that work.

## What changed before the first public commit

- External README/docs/webpage/full-paper text and reference-only source extracts are replaced at their original text paths by short source notices.
- Two external PDF files and a rendered page from one of those papers are omitted. A sibling `.source.md` notice preserves each source URL and original SHA-256. No fake text file is given a `.pdf` or `.png` extension.
- Search result JSON retains identifiers, titles, dates and links but omits abstract/full-description bodies (including inverted abstract indexes).
- Original-content hashes and explicit public-content hashes/actions are listed in `reference-publication.json`. The private original research workspace remains unchanged and was never committed into this Git repository.
- Captured text was withheld conservatively even when a permissive license might exist. This is a reduction of redistribution scope, not a claim that every removed source was legally restricted.

## Retained third-party executable examples

The py-pde example/tests and BoTorch tutorial in `feasibility/upstream/` are retained with their existing MIT notices (`pde-LICENSE`, `botorch-LICENSE`) and commit/source manifest. Their associated execution logs are original local outputs. They are not relabeled as this project's original code.

The only retained root reference text files outside source notices are the standalone BoTorch MIT and FEniCS GPL license texts. Reference-only Elmer source was removed rather than shipping its wider licensing/dependency context. No downloaded runtime packages are bundled.

## Historical evidence versus shipped notices

Old source-audit/retrieval receipts and study reports describe what was read **at the time of the experiment**. Those historical original-capture hashes remain useful for identifying the privately retained originals, but must not be interpreted as hashes of the new notices.

For the two stage-local reference inventories (`radiation` and `calibration`), `sha256` now identifies the shipped notice and `original_capture_sha256` retains the old digest. Their aggregate stage manifests and the two corresponding `workbench.py` pins are explicitly updated for the public edition. `docs/publication-manifest-changes.json` records before/after digests; numerical arrays, solvers, fitted parameters and scientific claims did not change.

`scripts/check.py` checks the full imported inventory against declared replacements/omissions and runs `check_public_references.py`. It fails if withheld binaries are restored, source notices change unexpectedly, quoted abstract fields return, or upstream example licenses disappear. This is a boundary/integrity check, not legal advice or a universal copyright detector.

## Retrieving a reference

Open the source URL listed in its notice or `reference-publication.json`. Follow the publisher/repository's access and reuse terms. Original download scripts may still retrieve externally licensed content for local research; do not commit such downloads without reviewing their rights. Re-downloading is not guaranteed to reproduce the original bytes because websites and default branches change.

## Licensing of original work

The owner has authorized public visibility but has not selected an open-source license for original code, writing or generated data. No blanket license grant is implied. The repository is publicly inspectable research, not a fully relicensed copy of its references. Future license selection cannot change upstream rights.
