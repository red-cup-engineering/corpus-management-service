from __future__ import annotations

from typing import Iterator

from research_corpus import CITE_RE, Corpus, Diagnostic, RELATION_KEYS, find_cross_refs


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
        for key in RELATION_KEYS:
            v = note.fm.get(key)
            if isinstance(v, list):
                referenced.update(v)
            elif isinstance(v, str):
                referenced.add(v)
        referenced.update(find_cross_refs(note.body))
        referenced.update(CITE_RE.findall(note.body))

    for note in corpus:
        if note.slug in referenced:
            continue
        if note.dir == "references":
            continue
        positions = any(note.fm.get(k) for k in
                        ("introduces", "recaps", "discusses", "chapters"))
        if note.kind == "narrative" and positions:
            continue
        if note.kind == "question" and note.fm.get("explores"):
            continue
        yield Diagnostic(
            code="orphan",
            severity="warning",
            path=note.path,
            message=f"`{note.slug}` — no incoming references",
            extra={"slug": note.slug},
        )
