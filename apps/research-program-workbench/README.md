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

Pass `--out /path/to/report.md` to `program-auditor` to select the report output path.

The original Pandoc pipeline may be selected separately from a qualified host. Bibliography generation consumes the same local `research-citations` workspace package; the original `research-dagger` ordering function remains importable, without a compatibility wrapper.

## Living Science sections

The same workbench reads a section's maintained glossary, claims, and teaching
articles. Select their actual leaf directories in the section's `research.toml`:

```toml
[program]
title = "Relationality"

[corpus]
lib_dirs = [
  "content/text/glossary/terms",
  "content/text/glossary/concepts",
  "content/text/glossary/topics",
  "content/text/documents/articles/teaching-articles/explanations",
  "content/text/documents/articles/learning-articles/claims",
  "references",
]
```

Each directory contributes its direct Markdown files. This bounded selection
does not recursively enroll `lib/legacy`, a nested archive, or unrelated section
content. Symbolic-link files are excluded and a configured directory that leaves
the selected root fails validation. `README.md` remains navigation rather than a
research entity. Inspect `total_notes` in the JSON report alongside diagnostics.

Science's canonical `type:` supplies the note type. The original `kind:` field
remains supported; differing `type` and `kind` declarations fail validation.
Without either field, the leaf directory supplies the historical singularized
default. A narrative in a deeply nested teaching directory is therefore still a
narrative, and a `type: question` still participates in the existing planner.
Duplicate slugs remain hard errors rather than selecting one copy silently.

Local inline Markdown links are resolved from the source file's directory.
`../../../glossary/terms/relating.md` must name that exact file; another
`relating.md` elsewhere cannot satisfy it. Existing local navigation files may
be linked without entering the configured research corpus. The planner,
dependency auditor, and monograph composer use exact indexed paths when turning
body links into graph edges or composed-document anchors. A historical homonym
outside the configured corpus cannot become an edge to the living definition.
The shared scanner excludes fenced code, inline code, HTML comments, images,
and escaped link examples, and accepts percent-encoded paths and quoted titles.

The composer includes indexed `type: reference` notes outside the legacy root
`references/` directory in a **Source notes** appendix. Each has its own stable
slug anchor and full annotation body, including source-verification limits and
literal code examples. The composition manifest marks these entries with `R`.
Links between the lessons and source annotations therefore point to emitted
content. The original root `references/` further-reading/citeproc pathway stays
separate; nested typed notes are not implicitly converted into BibTeX records.
Generated YAML metadata quotes title, subtitle and bibliography strings so that
colons, quotation marks, newlines and Unicode retain their values when parsed.

```sh
python -m unittest discover -s monograph-composer/tests -v
```

Run the original validator before composing a document:

```sh
uv run program-validator --root /path/to/science-section --no-lean --format json
```

This check covers local inline `.md` file destinations. It does not fetch network
URLs, validate fragment anchors, or parse reference-style links or HTML anchors.
It validates structure and source identity, not a claim's scientific truth.
The receiving tests exercise the same CLI, planner, auditor and composer with
the Relationality section's nested directory shapes:

```sh
python -m unittest discover -s program-validator/tests -v
```

### Generate a reviewed vocabulary from the source notes

The `research-vocabulary` command projects selected glossary frontmatter to
[SKOS](https://www.w3.org/TR/skos-reference/) in
[Turtle](https://www.w3.org/TR/turtle/). The Markdown source remains the editable
definition; the generated vocabulary is a reproducible view of that source.
Add an explicit selection to the same `research.toml`:

```toml
[vocabulary]
scheme = "urn:561:relationality:vocabulary"
namespace = "urn:561:relationality:concept:"
document_base_url = "https://github.com/lenticule-science/relationality-science-services-section/blob/main"
output = "data/records/ontology.ttl"
members = [
  "content/text/glossary/terms/relating.md",
  "content/text/glossary/concepts/attending.md",
]
```

Each member must be an exact path already indexed by `[corpus].lib_dirs`. A
matching filename elsewhere cannot supply the source. The selection controls
only this vocabulary projection; it does not remove unselected notes or their
diagnostics from whole-corpus validation. Configurations without `[vocabulary]`
keep their existing behavior. Invoking the exporter without it is an error.

```sh
uv run research-vocabulary --root /path/to/science-section
uv run research-vocabulary --root /path/to/science-section --check
```

The command is also available as `python -m research_corpus.vocabulary`. Normal
mode validates every selected source before atomically replacing the configured
Turtle file. `--check` compares expected UTF-8 bytes without writing. Exit status
is `0` for a successful write or current output, `1` for missing/stale output in
check mode, and `2` for invalid input or an I/O error. The output must be a
root-relative `.ttl` path and cannot be a symbolic link or escape the root.

For each member the exporter emits `skos:Concept`, `skos:prefLabel` from `name`
(or `title` when `name` is absent), `skos:definition` from `description`,
`skos:inScheme`, and `rdfs:isDefinedBy` using the document base URL plus the
percent-encoded source path. An original `id`, when present, is preserved as a
`dct:identifier` string. Concept IRIs append the percent-encoded filename stem
to `namespace`, which must end in `/`, `#`, or `:`. The document base must be
HTTP(S) without a query or fragment. Labels and definitions must be nonempty
strings; missing sources, selected slug collisions and duplicate members fail.

Source HTTP(S) and URN IRIs from `source`, `original-source`, `sources`, or
`provenance` become `prov:wasDerivedFrom` statements. A dedicated `sources`
array must contain IRIs. Descriptive provenance may be a string, list or mapping;
recognized `url`, `source_url`, `source-url`, `source`, `original-source`, and
`sources` fields retain actual IRIs. Free prose and owner names remain in the
source note. An attempted malformed URL is refused, and no URI is invented from
descriptive text. Source declarations are preserved claims of derivation, not
independent authentication or verification that remote resources are available.

The projection orders members and source IRIs deterministically and does not
guess semantic relationships from body links. Validate any additional ontology
contract with the section's SHACL shapes. Native receiving tests cover source
selection, escaping, provenance, drift, refusal without output replacement, and
the actual nested glossary directory shape:

```sh
python -m unittest discover -s research-corpus/tests -v
```

## First-class Science question → research-program focus

The existing Red Cup **record-research-question-service** writes an original
section-owned question as a create-only Markdown carrier; it does not answer or
route it. The original program planner now has a **read-only**, source-preserving
receiving operation for those already-recorded files:

```sh
uv run program-planner --root /path/to/research-toml-root \
  --question-file /path/to/science-section/content/text/documents/articles/research-articles/questions/existing.md
```

To read an actual *research program* rather than one topic, repeat
`--question-file` with **2–32 explicitly selected, distinct original
question files**. The same CLI reuses the current research-corpus source
graph to return each exact source claim, existing typed dependencies and
shared unresolved bottlenecks through the existing program-planner cluster
function. It never elevates source-graph proximity to truth, automatically
selects neighboring projects, or labels the program as HITS-received.
Different questions remain distinguishable even if they share a blocker;
the \`foam\` and \`FOAM\` homonyms are never canonicalized by spelling.
A multi-question program requires no new persistent program directory.

```sh
uv run program-planner --root /path/to/research-toml-root \
  --question-file /path/to/original/question-a.md \
  --question-file /path/to/original/question-b.md
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
