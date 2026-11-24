from __future__ import annotations

from typing import Iterator

from research_corpus import CITE_RE, Corpus, Diagnostic, find_cross_refs, outgoing, relation_targets


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Notes that participate in nothing: not referenced by anything and don't
    position any other note (no introduces/recaps/discusses/chapters).

    Excluded:
      - Reference notes (standalone resources by design)
      - Narratives that position other notes
      - Questions that declare `explores:`
    """
    referenced: set[str] = set()
    for note in corpus:
        referenced.update(outgoing(note.fm))
        referenced.update(find_cross_refs(
            note.body, source_path=note.path, path_slugs=corpus.path_slugs,
        ))
        referenced.update(CITE_RE.findall(note.body))

    for note in corpus:
        if note.slug in referenced:
            continue
        if note.dir == "references":
            continue
        positions = any(relation_targets(note.fm, k) for k in
                        ("introduces", "recaps", "discusses", "chapters"))
        if note.kind == "narrative" and positions:
            continue
        if note.kind == "question" and relation_targets(note.fm, "explores"):
            continue
        yield Diagnostic(
            code="orphan",
            severity="warning",
            path=note.path,
            message=f"`{note.slug}` — no incoming references",
            extra={"slug": note.slug},
        )
