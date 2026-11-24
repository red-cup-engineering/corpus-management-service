"""Citation-coverage rule: every body `[@key]` must appear in the citing
note's frontmatter `references:` (the manifest), and the manifest must
resolve against the merged citation corpus (annotations + inline).

This rule complements the bib-keyed broken-citation check: that one fires
when a `[@key]` doesn't exist in references.bib, this one fires when the
note's manifest is incomplete or wrong.
"""
from __future__ import annotations

from typing import Iterator

from research_citations import load as load_citations
from research_corpus import CITE_RE, Corpus, Diagnostic


def _manifest_keys(note) -> set[str]:
    """Cite-keys declared in the citing note's frontmatter `references:`."""
    refs = note.fm.get("references")
    if not isinstance(refs, list):
        return set()
    keys: set[str] = set()
    for entry in refs:
        if isinstance(entry, dict):
            k = entry.get("key")
            if k:
                keys.add(str(k))
        elif isinstance(entry, str):
            keys.add(entry)  # bare-key form: `references: [arnold1995hermitian]`
    return keys


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Body cites ⊆ note's `references:` manifest ⊆ resolvable cite-corpus."""
    refs, _ = load_citations(corpus.root, tuple(corpus.config.lib_dirs))
    available = set(refs.keys())

    for note in corpus:
        if note.dir == "references":
            continue

        manifest = _manifest_keys(note)
        body_cites = set(CITE_RE.findall(note.body))

        for key in sorted(body_cites - manifest):
            yield Diagnostic(
                code="cite-not-in-manifest",
                severity="error",
                path=note.path,
                message=f"body cites `[@{key}]` but `{key}` is not in this note's "
                        f"frontmatter `references:` manifest",
                extra={"slug": note.slug, "key": key},
            )

        for key in sorted(manifest - available):
            yield Diagnostic(
                code="manifest-key-unresolved",
                severity="error",
                path=note.path,
                message=f"manifest declares `{key}` but no annotation or inline "
                        f"declaration for it exists in the project",
                extra={"slug": note.slug, "key": key},
            )
