# Local full-research repository preparation

Prepared on 2026-09-24 as a new local Git repository named `thermal-experiment-research`. The owner chose the complete research archive rather than a product-only extraction. No commit, remote, push, release or public upload was performed.

## Preserved research

- Copied and initially byte-checked 1,475 research files (249,802,940 logical bytes).
- Excluded 8 environment/cache roots; no original virtual environment or parent session-recovery files copied.
- Preserved the study hierarchy, numerical arrays, failed/development runs, protocols, logs, original scientific conclusions, examples and source records.
- Disclosed two changes in `archive-replacements.json`: a token-bearing, non-article CAPTCHA response became a notice; root intent gained the repository-preparation scope. All other imported files remain byte-identical, and all eight pinned stage snapshots still match.
- Added new README/navigation, workflow diagram, repository rules, `.gitignore`, byte-preserving `.gitattributes`, a local/CI aggregate check, contribution guidance and publication/rights notes.

## Executed validation

The temporary validation environment was outside this repository and installed **only NumPy 2.5.3 and SciPy 1.18.1** using the existing hash-locked thermal requirements. It did not reuse the old study environment.

| Validation | Observed result |
|---|---|
| `python scripts/check.py --quick` | Import inventory and 28 standard-library entrypoint tests passed |
| `python scripts/check.py` | 28 entrypoint + 14 evidence-report + 26 prototype/workflow + 6 array checks = **74 tests passed** |
| `demo_workflow.py --approve-simulation` into ignored output/ | Actual plan/review/observe subprocesses completed, selected heat_high, consumed one declared budget unit, preserved `engineering_release=not_supported` |
| Fixed stage integrity | **1,186 manifest entries matched**; this is not 1,186 independent experiments |
| `actionlint .github/workflows/check.yml` | Passed after the pip install command was expressed as a YAML block |
| README skill audit, both languages | Local image references and SVG basics passed |
| README preview | Both languages, light/dark, ~900px content and 360px viewport; images loaded and page-level horizontal overflow absent |
| Final `gitleaks dir . --redact` | No findings after documented CAPTCHA replacement; scanner reported approximately 12.15 MB of scanned text, not all 250 MB of binary/PDF content |
| New-document local links | 66 local links resolved at the preparation check |
| GitHub single-file size screening | No file in the publication tree reaches 100 MiB |

The README previews are local GitHub-like Markdown rendering in a real browser, not screenshots of an actual GitHub page. Dense existing research plots remain linked at full resolution, and essential findings/commands are repeated as Markdown for mobile readers.

No new numerical benchmark is claimed. The same development example is replayed to verify relocation, not as a fresh held-out scientific result. Tests and a secret scanner do not prove physical validity, complete privacy, licensing compliance or production security.

## Local evidence locations

Ignored `output/validation/` contains full-check.log, quick.log, demo.log, install.log, actionlint.log, README audits and final redacted secret-scan output. `output/validation/research-demo/` contains newly generated workflow states and data, separate from the archived studies.

Ignored `output/playwright/` contains both README previews and eight full-page screenshots: two languages × two themes × desktop/mobile. These are local acceptance artifacts and are not required to run the research code.

## Still required before publication

Choose the original-work license, review redistribution rights for the third-party papers/docs/source captures, review retained historical host metadata, and explicitly authorize remote creation/visibility/push. See PUBLICATION.md. A complete private research archive is prepared; this is **not** an assertion that the entire archive is already cleared for public distribution.
