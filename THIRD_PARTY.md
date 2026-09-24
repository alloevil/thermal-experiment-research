# Third-party references and retained code

The owner authorized a public research edition with third-party reference bodies removed. This repository is not a mirror of the external literature. See [REFERENCE_POLICY.md](docs/REFERENCE_POLICY.md) for exact handling and [reference-publication.json](docs/reference-publication.json) for paths, source URLs and before/after hashes.

## Retained upstream executable examples

| Files | Source | License supplied |
|---|---|---|
| `feasibility/upstream/pde-example.py`, `pde-tests.py` | [py-pde](https://github.com/zwicker-group/py-pde), pinned commit in upstream/manifest.json | [MIT, David Zwicker](feasibility/upstream/pde-LICENSE) |
| `feasibility/upstream/botorch-tutorial.ipynb` | [BoTorch](https://github.com/pytorch/botorch), pinned commit in upstream/manifest.json | [MIT, Meta Platforms and affiliates](feasibility/upstream/botorch-LICENSE) |

These are upstream-authored examples, not our original implementations. Existing source notices and licenses remain intact. Requirements locks identify dependencies but do not bundle their installed runtime code.

## References not redistributed

- External PDFs and the derived paper-page image are absent; sibling `.source.md` files identify the original document and capture digest.
- External README, documentation, full-paper text and reference-only code extracts are replaced by short source notices at their previous text paths.
- Search JSON retains bibliographic/repository metadata and links, but removes abstract bodies and descriptions. Original numerical results and authored discussion remain unchanged.
- Historical retrieval receipts describe the original privately retained captures, not their replacement notices. Stage-local manifests explicitly separate original_capture_sha256 from current notice hashes.

Standalone license texts may remain for reference. Source metadata, attribution or a link is not a license grant for the linked work. Consult the source's specific terms before downloading or redistributing it.

## Original research work

Original code, prose and generated data do not yet have an owner-selected open-source license. The repository is publicly inspectable, but no blanket MIT/Apache grant is implied. Selecting a future license for original work cannot relicense upstream material.

This is a conservative distribution-scope review, not a legal opinion or guarantee about every possible right. No third-party adoption, sponsorship, performance result or DOI is attributed to this project.
