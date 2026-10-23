# Research program workbench

This is the living **Red Cup Content Engineering / Corpus Management** consumer of the original 561 mathematical-research toolchain. Eight coherent Python packages occupy one source-owned `uv` workspace; seven are end-user or reusable original capabilities, and `research-corpus` supplies their shared corpus semantics. This is not a second ontology, source-of-truth for theorems, or new migration registry.

The initial recoveries preserved the original Python implementations and individual package `pyproject.toml` Git blobs byte-for-byte. The citation loader and CLI were subsequently adjusted to receive the older keyed-map citation format without discarding the recovered list grammar:

- `research-corpus`: frontmatter-Markdown research program, `research.toml`, typed links and dependency graph
- `program-validator`: frontmatter, link, citation, dependency-cycle, status and prose-proof diagnostics. Lean-source `sorry` is informational and never a proof-realization verdict; the Obsmetrologia owner decides proof completion.
- `program-auditor`: dependency risk, foundation distance, load-bearing links and declared/body dependency divergence
- `research-dagger`: dependency-topological order with introductory/recap narrative placement
- `program-planner`: question readiness, shared blockers, enablement frontier, research demands and missing realizations
- `research-citations`: citation metadata validation/collection, cite-key generation and BibTeX projections
- `cite-tool`: the original command-line check, list and `references.bib` generation operations using that same citations library
- `monograph-composer`: section/part/chapter ordering, stable anchors, optional bibliography and Pandoc citeproc composition

## Existing CLI and import contracts

Use an existing mathematical research program with `research.toml`. The original entrypoints still select `--root` explicitly and do not need a second source registry:

```sh
uv run cite-tool check --root /path/to/research-program
uv run cite-tool generate --root /path/to/research-program --out /path/to/research-program/references.bib
uv run program-validator --root /path/to/research-program --no-lean
uv run program-auditor --root /path/to/research-program
uv run program-planner --root /path/to/research-program
uv run monograph-composer --root /path/to/research-program --no-pandoc
```

The original Pandoc pipeline may be selected separately from a qualified host. Bibliography generation consumes the same local `research-citations` workspace package; the original `research-dagger` ordering function remains importable, without a compatibility wrapper.

## First-class Science question → research-program focus

The existing Red Cup **record-research-question-service** writes an original
section-owned question as a create-only Markdown carrier; it does not answer or
route it. The original program planner now has a **read-only**, source-preserving
receiving operation for those already-recorded files:

```sh
uv run program-planner --root /path/to/research-toml-root \
  --question-file /path/to/science-section/content/text/documents/articles/research-articles/questions/existing.md
```

Optionally supply `--previous-question-file <earlier-recorded-question.md>`
to compare two **explicitly selected** source questions. The readout retains
the prior file digest and exact source substrings aligned to complete tokens. This is
*not* an inferred semantic novelty judgment or an automatic attribution of
message order. It refuses a missing predecessor rather than choosing one by
search relevance.

This mode emits one structured JSON readout to **stdout**; it never generates a
paper, opens a second question, silently inserts a new corpus entity, writes a
batch plan, or supplies missing source links by string similarity. It records
the exact question body, SHA-256 of the original file bytes, exact source
references, exact matches to the **configured** research corpus, unjoined
references, a *frontmatter-graph-only* readiness classification, and explicitly
unassessed proof, Engineering, Operations and independent-receiving states.
Source pointers, even if present, are **claims of provenance, not authenticated
witnesses**. The full original question survives later research re-readings.

The question file may belong to a sibling source-owned Science checkout. The
caller selects it explicitly; a source not found, non-question file, malformed
reference, or ambiguous slug collision is refused without manufacturing a
replacement. The programme reads only the configured research corpus; absence
of an exact reference is not proof that the 561 Group does not know it. The
output is a *candidate source-linked research structure*, **not a received
Holistic Integrated Thing Structure** or a mathematical theorem.

The native receiving test calls the **pinned original question recorder**
commit `23b4fcd56cdf9aa7636759a382c27edfeadc61bd` and then this
same CLI/library across valid, missing, invalid, homonymous and resolved
question conditions. The source check is:

```sh
python -m unittest discover -s program-planner/tests -v
```

A runnable environment with its actual workspace packages is required.
The ordinary no-`--question-file` Markdown batch planner remains unchanged.
No scientific acceptance, installed host adoption or physical foam theorem is
inferred from the research-program graph.

## Archive citation-manifest receiving

The archived `emsenn/emsenn-archive-code` `research/citations/README.md` uses a `references:` **list** of entries with `key:` and `type:`. The separate historical `emsenn/emsenn-archive-org/citations.md` defines a **citekey-keyed map** with `class:`, `in:` and `location:`. Those formats are different; neither one's existence certifies the current Science citation policy.

The original `research-citations` loader now receives either format in place. For keyed manifests, it translates only the historical class vocabulary (article, book, chapter, preprint, report, thesis, online, software) and the `in → booktitle` / `location → address` field spellings. It retains unrelated fields and their warnings. Disagreeing `class` and `type`, disagreeing keys, conflicting field spellings, invalid map values, and unknown classes are **errors**, not best-effort citation records. Annotations remain additive to original inline declarations.

`cite-tool generate` now refuses to replace an existing `references.bib` if any references fail validation. `cite-tool check` and `list` remain the original entrypoints. Regression and refusal examples reside in each original package's `tests/` directory; they document intended behavior but are not an executed test receipt. The normalized reading of historical metadata does not confer scientific or bibliographic verification on its claims.

## Source custody

Original source repository and revision: `emsenn/emsenn-archive-code@3c69d5cf9d3bec484f1dc22067ed9623b1bab7c6`. Source locations: `topical/information/561-group/research-tools/research/math/` and `topical/information/561-group/research-tools/research/citations/research-citations/`. No original archive repository is a live implementation owner.

The previously recovered two-package `research-program-dependency-auditor` subtree is preserved without byte changes as this correctly named workbench, then augmented with its original Python planning, citation, monograph and validator packages, plus the original `cite-tool` CLI. Do not duplicate the parser/auditor or the existing JS research-document metadata projections. The historical `program-validator` source is recovered with its structural rules intact. Its old source-text `sorry` hard-fail is deliberately corrected to a warning: frontier theorems are not a failure, and only the actual Obsmetrologia axiom census and proof-work-order gate can certify completed proof realization.

This is Git source integration; any original `uv`/Pandoc run, installed consumer, and scientific qualification are separate evidence.
