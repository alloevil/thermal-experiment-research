# Full research archive: import and portability

This repository began as a copy of the complete thermal research tree, not a product-only extraction. The public edition keeps the original research while replacing external full-text references with source notices. The earlier private local workspace and its unrelated session-recovery files were not modified.

## Included

The initial import recorded 1,475 files (approximately 249.8 MB): protocols, code, numerical data/results, development runs and external references. Original research and negative results remain available. The public reference transformations are documented in REFERENCE_POLICY.md and reference-publication.json; the original import inventory is retained as provenance, not a claim that every original third-party byte is redistributed. No Git LFS is required for the included files.

The study hierarchy is retained: `next_experiment/core.py` still imports `radiation/model.py`. Only source-notice inventories and their two affected aggregate pins were updated for publication; scientific code and numerical arrays were not changed.

## Excluded

- Local virtual environments and generated Python/tool caches (8 roots at import).
- The parent workspace's unrelated model-context/session-recovery files; these are not research material.
- New local README previews, validation logs and temporary environments, stored in ignored `output/`.

`docs/archive-import.json` lists every imported source file with its original SHA-256 and byte count, plus excluded roots. It is a local provenance record, not an independent signature.

## Disclosed content handling

`sources/rtp-1994-publisher.txt` was a publisher CAPTCHA challenge, not article text. Gitleaks flagged token-like content. The new repository replaces that unusable response with a notice; the original source file remains untouched in the original local workspace.

`docs/archive-replacements.json` records original and public hashes or explicit omissions. Historical `sources/*receipts.json` and `source-audit.json` retain original response digests; these are not hashes of the shipped notices. Two aggregate stage manifests now identify public source notices, with before/after digests in publication-manifest-changes.json.

The root `intent.md` includes the user-authorized preparation and public-edition scope. Reference bodies, quoted search abstracts and source inventories have the explicitly declared changes listed in the replacement record. All remaining imported files retain their original hashes.

`.gitattributes` disables automatic text conversion for the archive so Git does not silently normalize historical line endings and invalidate recorded hashes. New Markdown/source files use LF, but captured third-party documents retain their original bytes.

## Historical paths and provenance

Old logs, source retrieval records and example commands may contain machine-local paths such as `/mnt/...` or `/home/...`, original timestamps, and previous workspace names. They document historical execution; they are not portable installation commands. Do not mass-rewrite those files, since that would invalidate provenance.

Use the repository-root README, QUICKSTART, and docs/REPRODUCE.md for current commands. No old virtual environment is copied or symlinked into this repository. Old standalone source-audit scripts/receipts are not automatically a root-level validator; imported-source paths and the CAPTCHA replacement must be interpreted as described here.

## New writes

Run demos and replays into a fresh output directory. New audit results live under `output/`, which is ignored. Never redirect fresh logs over archived logs. `scripts/check.py` validates the import inventory (with the declared replacement), pinned stages and selected existing tests without regenerating stage snapshots.

## Publication boundary

The owner authorized publication after external-reference processing. The public edition does not redistribute external full texts. See PUBLICATION.md and THIRD_PARTY.md for the retained upstream examples and the still-undecided license for original work. Website availability alone is never treated as permission.
