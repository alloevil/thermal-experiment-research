# README design brief

- Audience: control/thermal researchers and engineers who want the complete path from a physical model to next-experiment recommendations, including failures.
- One-sentence value: reproduce how thermal model mismatch, calibration, measurement bias and experimental choices interact, then try a bounded reviewable next-test workflow.
- Primary proof: the actual candidate-probability demo and the negative comparison against a simple separation heuristic; unchanged historical numerical arrays and failure cases.
- First successful action: standard-library `python workbench.py check`, then a NumPy/SciPy-only synthetic `demo_workflow.py` with explicit simulation approval.
- Theme: an engineering lab notebook, not a generic AI service. A restrained static SVG research sequence plus native Markdown tables/commands and a real generated plot.
- Palette: warm white `#f7f8fa`, ink `#172b3a`, blue `#245d78`, rust `#a75031`, muted `#536977`.
- Typography: system sans-serif; large sequence labels, compact explanatory Markdown. No remote fonts, photos, image generation or animation.
- Shapes: 2px strokes, 12px radii, 32px spacing grid. Motif: model → experiment → evidence; branches can also reject or remain ambiguous.
- Mobile: keep essential instructions and study conclusions in Markdown, not inside scaled plots. The SVG is an overview only, and full-size plots are linked for detail.
- Preview: inspect both READMEs at a ~900px desktop content width and 360px viewport, including dark-page contrast; local preview is not a claim that a GitHub remote has been published.

## Discovery-oriented content refresh

Reviewed BayBE, PyBOP and do-mpc READMEs for problem-to-example flow, scientific use cases/citation, and clear technical scope. Their design principles are adapted, not their logos, adoption evidence or algorithm claims. The title and static visual system are unchanged.

The bilingual opening now explicitly names thermal modeling, calibration and model discrimination. Short FAQs answer actual scope questions; a project-facts index links claims to original studies, and CITATION.md explains unresolved publication metadata. Details and official GitHub/Google references are in DISCOVERABILITY.md. There is no measured SEO/GEO lift or remote configuration change.
