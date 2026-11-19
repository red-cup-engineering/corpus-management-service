from __future__ import annotations

from typing import Iterator

from research_corpus import Corpus, Diagnostic


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Two or more notes claiming the same `symbol:` is a soft warning —
    the canonical-notation guarantee is broken."""
    by_symbol: dict[str, list[str]] = {}
    for note in corpus:
        if note.dir not in ("concepts", "objects", "morphisms", "theorems"):
            continue
        sym = note.fm.get("symbol")
        if not sym:
            continue
        by_symbol.setdefault(sym, []).append(note.slug)
    for sym, slugs in sorted(by_symbol.items()):
        if len(slugs) < 2:
            continue
        slugs = sorted(slugs)
        yield Diagnostic(
            code="symbol-collision",
            severity="warning",
            path=None,
            message=f"`{sym}` claimed by " + ", ".join(f"`{s}`" for s in slugs),
            extra={"symbol": sym, "slugs": slugs},
        )
