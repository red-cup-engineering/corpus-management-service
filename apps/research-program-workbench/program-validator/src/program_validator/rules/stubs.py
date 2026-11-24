from __future__ import annotations

from typing import Iterator

from research_corpus import Corpus, Diagnostic


def body_chars(body: str) -> int:
    """Body length excluding heading lines and blanks."""
    return sum(
        len(ln) for ln in body.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    )


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Non-narrative notes whose body is below `min_body_chars`."""
    threshold = corpus.config.validate.min_body_chars
    for note in corpus:
        if note.kind == "narrative":
            continue
        n_chars = body_chars(note.body)
        if n_chars < threshold:
            yield Diagnostic(
                code="stub",
                severity="warning",
                path=note.path,
                message=f"`{note.slug}` ({note.kind}, {n_chars} chars)",
                extra={"slug": note.slug, "kind": note.kind, "chars": n_chars},
            )
