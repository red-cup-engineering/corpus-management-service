from __future__ import annotations

from typing import Iterator

from research_corpus import Corpus, Diagnostic, detect_cycles


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Cycles in the depends-on graph — corruption signal."""
    for cycle in detect_cycles(corpus.notes):
        if len(cycle) == 1:
            slug = cycle[0]
            yield Diagnostic(
                code="cycle",
                severity="error",
                path=corpus[slug].path,
                message=f"`{slug}` lists itself in depends-on (self-loop)",
                extra={"slugs": cycle},
            )
        else:
            yield Diagnostic(
                code="cycle",
                severity="error",
                path=None,
                message="cycle in depends-on: " + " → ".join(f"`{s}`" for s in cycle),
                extra={"slugs": cycle},
            )
