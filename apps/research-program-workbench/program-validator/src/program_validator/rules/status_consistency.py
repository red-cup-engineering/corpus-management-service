from __future__ import annotations

from typing import Iterator

from research_corpus import Corpus, Diagnostic

UNPROVED = ("draft", "sketch", "wip")


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """A `proved` note must not depend on a `draft`/`sketch`/`wip` note —
    otherwise the proved claim is conditional on unproved work."""
    for slug, n in corpus.items():
        if n.fm.get("status") != "proved":
            continue
        for dep in (n.fm.get("depends-on") or []):
            d = corpus.notes.get(dep)
            if d is None:
                continue
            dep_status = d.fm.get("status")
            if dep_status in UNPROVED:
                yield Diagnostic(
                    code="status-inconsistency",
                    severity="error",
                    path=n.path,
                    message=f"`{slug}` (proved) depends on `{dep}` ({dep_status})",
                    extra={"slug": slug, "dep": dep, "dep_status": dep_status},
                )
