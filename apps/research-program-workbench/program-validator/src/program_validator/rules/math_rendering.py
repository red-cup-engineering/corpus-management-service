"""Optional TeX renderability check, separate from scientific proof."""
from __future__ import annotations

from typing import Iterator

from research_corpus import Corpus, Diagnostic
from research_corpus.pandoc import PandocError, tex_fallbacks


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    for note in corpus:
        try:
            fallback = tex_fallbacks(note.body)
        except PandocError as exc:
            yield Diagnostic(code="tex-check-unavailable", severity="error",
                             path=note.path, message=str(exc))
            return
        for tex in fallback:
            yield Diagnostic(code="tex-rendering", severity="error", path=note.path,
                             message="Pandoc could not render this formula as MathML",
                             extra={"slug": note.slug, "tex": tex})
