# Authenticated Science glossary dataset

Build the exact reviewed vocabulary, glossary documents, observed navigation,
and authored assertions as separate named RDF graphs. This Workbench
application uses the Science repository's data-only build profile, not a
catalog of special cases in code. It never treats a hyperlink as a scientific
claim or classifies all glossary notes as reviewed concepts.

## Runtime and inputs

- GNU gzip. The tracked artifact uses `gzip -n -9 -c` (qualified with
  1.13); the receipt records the encoder version and arguments. For exact
  compressed-byte reproduction use the same encoder. No local checkout path
  or wall-clock timestamp enters the receipt.

- Node 24 and native Git. This operation reads an **already available, exact
  local SHA-1 commit**. It does not change the checkout, resolve a branch in
  place of the requested commit, fetch missing objects, or ask for credentials.
- Exact Git Engine 0.1.11-dev.0, Term 0.3.8 and Triplet 0.2.9 artifacts. The package
  manifest fixes these direct inputs. Use the issued Git Engine archive from
  the canonical registry and its [owner's runtime lock](https://github.com/red-cup-engineering/git-engine/blob/5618cc1c6b722179aa29d03b93e8176e059cd467/package-lock.json).
  Pass the actual resolved cohort through your established package acquisition
  process.
- Markdown **0.6.0-dev.0**, from [merged source
  9e69aa58](https://github.com/red-cup-engineering/markdown-engineering-services-section/tree/9e69aa588317cae2c505c097ee0ce32180f6000c)
  ([Markdown #62](https://github.com/red-cup-engineering/markdown-engineering-services-section/pull/62)).
  This source build has not been established as a clean registry receiving
  path. Acquire its exact package through the original Markdown owner; do not
  silently substitute issued 0.5.13. A changed observer version
  needs to be qualified against the receiving corpus before adoption.
- One Python 3.12+ environment with the original [Research
  Corpus](https://github.com/red-cup-engineering/corpus-management-service/tree/0cea49d462f17b7b73bde380cc36d3a2c5a79d8e/apps/research-program-workbench/research-corpus)
  (the authored-relations profile command), the original [RDF
  Conformance](https://github.com/red-cup-engineering/rdf-vocabulary-conformance-service/tree/25d5c2432aa38ada297acfae3dcdc49aac6aedab)
  (dataset.ask and dataset.shacl), and its pinned RDFLib. Build and install
  these from the cited source revisions where issued artifacts are not
  available. The renderer uses the owner programs rather than reopening their
  admission logic in JavaScript.

The Science profile must itself exist as a regular file at the input commit.
It selects the canonical content/text/glossary catalog (including README
navigation), original Turtle, authored relation profile, and dataset
conformance config. That commit supplies every selected glossary blob,
research.toml, the exact shapes, and the exact ASK query. The Workbench
uses original frontmatter authority; Term's closed Engineering schema decides
carrier admission independently. Reviewed assertions must match visible
original document bytes and both reviewed SKOS endpoint bindings. No ad hoc
command-line predicate or unpinned inventory is accepted.

## Receive a pinned source catalog

The existing `@red-cup-engineering/research-glossary-dataset/git-source` subpath
reads the stored profile, content catalog and selected glossary blobs at one
local Git commit. It needs native Git and Git Engine, not Markdown, Term,
Triplet or the Python runtime. This is source custody only: it does not parse
Markdown or admit records or graph assertions. Building or replaying the
graph still needs the applicable projection dependencies above.

## Run

From this directory, after materializing the exact runtime:

    npm test
    npm run project -- \
      --repository /absolute/path/to/science-repository \
      --revision <full-immutable-source-commit> \
      --profile data/schema/glossary-build.json \
      --audience authenticated \
      --python /absolute/path/to/python-environment/bin/python \
      --output /absolute/existing/private-parent/new-output-directory

For an already qualified revision, compare both full output SHA-256 and graph
membership. A later commit can preserve the content tree yet intentionally
change source addresses and observation identities: do not treat those
different source pins as byte-identical. This output is private, not a
publication or validation of the scientific claims.

A successful build materializes only the canonical N-Quads at the path named
by the Science acceptance config, coverage.json, the independent
acceptance.json, and a source.json Git/blob and SHA-256 receipt under a
new directory outside the source. Each file is private. Missing inputs or
failed SHACL or ASK leave no promoted output. SHACL checks the dataset's
union for shape rules; ASK separately checks assertion placement. No
inference, external traversal, or fragment-existence claim is made.


## Query navigation with source evidence

The canonical navigation graph records each link occurrence, its source,
the canonical Markdown observer's target text and resolution state. For
reference links this is the resolved Markdown destination, not necessarily a
literal substring of the use site. A verified or admitted target
is attached to the occurrence. A reader that needs document-to-target pairs
can select distinct source/target pairs from these occurrences. They are not
stored a second time as direct Dublin Core `references` triples. That would
allow links to appear in the graph without their source observation and
lose the distinction between two citations to the same path. A navigation
reference does not establish an authored scientific relation.

## Receive the tracked snapshot

After independent SHACL and ASK acceptance, the same build also writes
`data/records/<dataset-basename>.nq.gz` and
`data/records/<dataset-basename>.manifest.json` in the private output
directory. The manifest binds the raw and compressed digests, quad count,
immutable Science source/content tree and exact input blobs, and the native
conformance report. It records the application's own builder, projection,
Git source reader, navigation projector, RDF helper and receipt modules, as well as the resolved
dependency entry-module and package manifest digests, Python entry-module
digests, and native conformance/RDFLib versions. Two builds can produce the
same graph with different code. A matching output does not make the measured
producer identities interchangeable. These measurements do not attest the
entire dependency tree, a Git revision, or release authorization.

Each evidence, authored, and navigation stage reads the prepared output
within the size limit and parses only the same bytes whose SHA-256 matches
the selected manifest. Python query consumers can use the same boundary
with `SnapshotReceiver(...).load_prepared_dataset()` rather than opening
the prepared path directly. This verifies the bytes and current pinned
Git inputs; it does not sign the manifest or establish scientific truth.

The Python `authored` stage checks each stored relation observation against
its exact pinned Markdown file, whether its value was projected to a carrier,
projected as a literal, or retained without a target. It requires the original
plain string under the named top-level or nested `relations` field and checks
the total and both projection counts. The separate reviewed-relation replay
checks selected concept edges. Lexical custody does not establish that every
authored field was retained or independently re-run Term target admission.

A saved-query reader opens the same verified buffer once and pins the
receiving Git commit. Use `receiver.open_saved_queries()`, then
`reader.select("data/schema/queries/reviewed-evidence.rq", bindings=...)`
for reviewed SELECT files already tracked in that commit. Bind variables
with RDFLib IRIs or literals. The original RDF conformance service admits
only the bounded local named-graph SELECT profile, not arbitrary query text,
external graphs, services, or a caller's different worktree file.

To receive a snapshot, commit the two generated files together in the
Science repository and preserve the exact source commit in receiving
history. Do not edit generated manifest digests or re-compress the bytes by
hand. Running this builder does not push, deploy or make the data public.


### Replay navigation against the pinned source

After preparing the tracked snapshot, an environment with the qualified Node
cohort can replay just the navigation named graph. Invoke the existing Python
receiver, with the installed Workbench entrypoint supplied by the caller:

    verify-glossary-snapshot navigation \
      --root /absolute/path/to/science-repository \
      --profile data/schema/glossary-build.json \
      --manifest data/records/glossary.manifest.json \
      --snapshot data/records/glossary.nq.gz \
      --output build/glossary.nq \
      --navigation-replay /absolute/path/to/glossary-dataset/src/replay-glossary-navigation.mjs

The Node program reads the manifest's exact source commit as selected by the
receiver and emits only the expected navigation graph. The receiver compares
all its RDF statements, not just their count or target identities. A matching
checksum alone does not authenticate an observation. This stage does not
replay carrier assertions or replace SHACL, reviewed-vocabulary checks, or
authored relation replay. It does not fetch objects or install packages. For the expected graph alone,
run `npm run replay-navigation -- --repository PATH --revision SHA --profile FILE --audience authenticated`.
