"""Optional TeX renderability check, separate from scientific proof."""
from __future__ import annotations

from functools import lru_cache
from typing import Callable, Iterator

from research_corpus import Corpus, Diagnostic
from research_corpus.pandoc import PandocError, tex_fallbacks


TexReader = Callable[[str], tuple[str, ...]]


def cached_reader() -> TexReader:
    """Reuse only exact successful reads, within one validation invocation."""
    return lru_cache(maxsize=256)(tex_fallbacks)


def check(corpus: Corpus, *, read: TexReader = tex_fallbacks) -> Iterator[Diagnostic]:
    for note in corpus:
        try:
            fallback = read(note.body)
        except PandocError as exc:
            yield Diagnostic(code="tex-check-unavailable", severity="error",
                             path=note.path, message=str(exc))
            return
        for tex in fallback:
            yield Diagnostic(code="tex-rendering", severity="error", path=note.path,
                             message="Pandoc could not render this formula as MathML",
                             extra={"slug": note.slug, "tex": tex})
