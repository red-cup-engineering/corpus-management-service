from __future__ import annotations

from typing import Iterator

from research_corpus import Corpus, Diagnostic, find_cross_refs


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Internal `[text](slug.md)` links resolve to a known slug."""
    slugs = corpus.slugs()
    for note in corpus:
        for tgt in find_cross_refs(note.body):
            if tgt not in slugs:
                yield Diagnostic(
                    code="broken-link",
                    severity="error",
                    path=note.path,
                    message=f"references missing slug `{tgt}`",
                    extra={"slug": note.slug, "target": tgt},
                )
