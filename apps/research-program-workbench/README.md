# Research program workbench

This is the living **Red Cup Content Engineering / Corpus Management** consumer of the original 561 mathematical-research toolchain. Seven coherent Python packages occupy one source-owned `uv` workspace; five are end-user or reusable original capabilities, and `research-corpus` supplies their shared corpus semantics. This is not a second ontology, source-of-truth for theorems, or new migration registry.

The recoveries preserve the original Python implementation files and individual package `pyproject.toml` Git blobs byte-for-byte:

- `research-corpus`: frontmatter-Markdown research program, `research.toml`, typed links and dependency graph
- `program-validator`: frontmatter, link, citation, dependency-cycle, status and prose-proof diagnostics. Lean-source `sorry` is informational and never a proof-realization verdict; the Obsmetrologia owner decides proof completion.
- `program-auditor`: dependency risk, foundation distance, load-bearing links and declared/body dependency divergence
- `research-dagger`: dependency-topological order with introductory/recap narrative placement
- `program-planner`: question readiness, shared blockers, enablement frontier, research demands and missing realizations
- `research-citations`: citation metadata validation/collection, cite-key generation and BibTeX projections
- `monograph-composer`: section/part/chapter ordering, stable anchors, optional bibliography and Pandoc citeproc composition

## Existing CLI and import contracts

Use an existing mathematical research program with `research.toml`. The original entrypoints still select `--root` explicitly and do not need a second source registry:

```sh
uv run program-validator --root /path/to/research-program --no-lean
uv run program-auditor --root /path/to/research-program
uv run program-planner --root /path/to/research-program
uv run monograph-composer --root /path/to/research-program --no-pandoc
```

The original Pandoc pipeline may be selected separately from a qualified host. Bibliography generation consumes the same local `research-citations` workspace package; the original `research-dagger` ordering function remains importable, without a compatibility wrapper.

## Source custody

Original source repository and revision: `emsenn/emsenn-archive-code@3c69d5cf9d3bec484f1dc22067ed9623b1bab7c6`. Source locations: `topical/information/561-group/research-tools/research/math/` and `topical/information/561-group/research-tools/research/citations/research-citations/`. No original archive repository is a live implementation owner.

The previously recovered two-package `research-program-dependency-auditor` subtree is preserved without byte changes as this correctly named workbench, then augmented with **four original Python packages**. Do not duplicate the parser/auditor or the existing JS research-document metadata projections. The historical `program-validator` source is recovered with its structural rules intact. Its old source-text `sorry` hard-fail is deliberately corrected to a warning: frontier theorems are not a failure, and only the actual Obsmetrologia axiom census and proof-work-order gate can certify completed proof realization.

This is Git source integration; any original `uv`/Pandoc run, installed consumer, and scientific qualification are separate evidence.
