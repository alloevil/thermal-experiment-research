# README, GitHub discovery and accurate AI summaries

Status: GitHub discovery metadata prepared for the owner-authorized public edition; no measured search performance is claimed. This work changes entry-point documentation, not research algorithms or numerical results. Public reference handling is documented in REFERENCE_POLICY.md.

## Three README references actually reviewed

| Reference | Observed pattern | Adapted here | Not copied or claimed |
|---|---|---|---|
| [BayBE](https://github.com/emdgroup/baybe) | A concrete optimization problem, a search-space/objective setup, and a recommendation → measurement loop | State the user's model-mismatch question; link a real example, task input and observation update before the research archive map | No adoption claims, package-download badges, chemistry coverage or general-purpose optimizer positioning |
| [PyBOP](https://github.com/pybop-team/PyBOP) | Explicit scientific use cases, executable examples, related research, and a dedicated citation section | Separate implemented capabilities from study evidence; provide source-linked project facts and citation guidance | No borrowed publication, DOI, author list, research sponsorship or performance result |
| [do-mpc](https://github.com/do-mpc/do-mpc) | A concise technical identity, scope/features, installation/docs and citation | Say what the current method is and is not: finite-ensemble model discrimination rather than autonomous equipment control | No robust-MPC, MHE or general-control capabilities implied for our bounded prototype |

These are information-architecture references, not templates copied pixel-for-pixel or evidence that these designs cause more search traffic. The existing research-native SVG/plot system stays intact. Retrieved README snapshots for this review live under ignored `output/discovery/`, not in the scientific archive or a new distributable third-party bundle.

## Semantic positioning, not keyword stuffing

| Search concept | Actual support in this repository | Entry point |
|---|---|---|
| thermal modeling / heat transfer | Conductive, convective and radiative model studies | README introduction; radiation/protocol.md |
| parameter calibration / parameter estimation | Finite-model calibration and explicit identifiability limits | docs/PROJECT_FACTS.md; calibration/RESULTS.md |
| model discrimination / experimental design | Select among allowed experiments to compare two mechanisms | README FAQ; next_experiment/GUIDE.md |
| sensor calibration / sensor bias | One-point offset correction and counterexamples involving reference error | reference_correction/RESULTS.md |
| reproducible research | Saved protocols, input/output data, negative outcomes and runnable examples | docs/REPRODUCE.md; docs/ARCHIVE.md |

The English/Chinese README introductions now name these concepts in complete sentences. They are not claims about measured search volume, keyword difficulty or ranking. Avoid misleading tags such as `autonomous-scientist`, `production-ready`, or `digital-twin` for capabilities that are absent or unvalidated. Semiconductor equipment remains application motivation, not a tested product claim.

## GitHub settings to apply only after publication approval

`docs/github-discovery.json` records the intended repository, English About description and ten relevant topics. It is **not** automatically consumed by GitHub. Publication applies these settings through the GitHub API; the file alone does not prove the remote state. Canonical repository: https://github.com/alloevil/thermal-experiment-research .

After ownership, visibility and redistribution rights are confirmed:

1. Set the repository About description from the draft.
2. Set the topics; GitHub documents lowercase letters/numbers/hyphens, up to 50 characters each, at most 20 topics. Topic names are public even if created for a private repository—do not use private customer or project names.
3. Leave Homepage empty unless a real maintained site exists. Do not invent a canonical URL or advertise an unpublished package.
4. Confirm author attribution and the real repository URL, then add a valid `CITATION.cff`. GitHub also recognizes `CITATION.md`; the current file gives truthful interim guidance, not a fake formatted software citation.
5. On an actual release, link reusable examples and research evidence with commit/tag permalinks where appropriate. Preserve normal relative links for everyday navigation.
6. A social-preview image is optional and separate from README rendering. The current SVG is a README diagram, not proof that a repository social card has been configured. No image upload or remote setting change has been made.

Official references: [GitHub repository topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics), [GitHub citation files](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files).

## What “GEO” means in this change

Here it means making the project easier to understand and accurately cite, not manipulating an assistant into recommending it. There are no instructions telling crawlers or models to rank the repository highly or ignore limitations.

- Keep the project name, actual methods, inputs/outputs and limitations explicit in text.
- Answer real reader questions with short, standalone FAQ responses and source links.
- Link numerical claims to the exact study and protocol; carry qualifiers about synthetic data and candidate-set probabilities alongside the numbers.
- Keep third-party references, our experiments and current product hypotheses distinct.
- Do not hide essential facts solely in diagrams, screenshots or large JSON logs.

`docs/PROJECT_FACTS.md` and `CITATION.md` serve readers and automated summarizers without requiring a special protocol. They do not guarantee AI retrieval or citation. Updating the methods or scope requires updating these entry documents too; they are summaries, not a second source of experimental truth.

No `llms.txt`, robots.txt, sitemap, JSON-LD or custom meta tags were added. A repository file does not control github.com's headers or crawler policy. Google explicitly states that its AI Overviews/AI Mode require no additional AI text files or special structured data; normal SEO principles and accessible textual content still apply. This guidance is specific to Google Search, not a guarantee about every answer engine. [Google AI features and your website](https://developers.google.com/search/docs/appearance/ai-features).

If a standalone documentation site is later justified, evaluate real page titles/descriptions, canonical URLs, crawlability, sitemap and structured data there. Do not build a site merely to tick SEO boxes before publication rights and user value are established.

## Validation now versus measurement after release

Locally check that all statements match code/study results, JSON fields/topic syntax are valid, citation metadata is not fabricated, links resolve, and both language READMEs render at desktop/mobile widths on light/dark backgrounds. This can verify content preparation—not search performance.

After authorized public release, record dated observations: whether the repository is publicly reachable, relevant search-query visibility, GitHub traffic/referrers within their available retention window, and whether users reach the documented demo. If manually testing AI summaries, use fixed prompts and a dated provider/model list; score factual accuracy and source attribution, not just whether the project is mentioned. Do not assume Search Console access to github.com or claim impressions for pages you do not control.

There is no baseline search or AI-citation dataset yet. The earlier content-preparation change did not publish remotely; the owner subsequently authorized publication after reference processing. No crawl submission, promotion or external messaging is implied. See PUBLICATION.md and REFERENCE_POLICY.md.

## Executed local checks

- The three reference READMEs were fetched and read for this change; local snapshots and hashes are retained under ignored `output/discovery/`.
- The proposed About description is 180 characters; all ten topic strings satisfy GitHub's documented length/character/count constraints. They remain unapplied.
- 94 local document/image links across the updated entry documents resolved. Quoted result counts were checked against the saved study JSON, rather than copied from competing projects.
- Both README image/SVG audits passed. Real-browser local previews covered both languages, light/dark themes, ~900px desktop content and a 360px viewport: images loaded, and no page-level horizontal overflow was detected. The screenshots are GitHub-like local renders, not published GitHub pages.
- `python scripts/check.py --quick` passed the preserved-import/pinned-snapshot checks and 28 standard-library tests. No algorithms or recorded experiment data changed; full numerical experiments were not rerun for a documentation-only change.

Logs: `output/discovery/content-verification.log`, `output/discovery/quick-check.log`; screenshots: `output/playwright/discovery-*`. These demonstrate content and layout validation only, not SEO or GEO effectiveness.
