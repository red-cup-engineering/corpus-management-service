from __future__ import annotations

from pathlib import Path
from typing import Iterator

from research_corpus import Corpus, Diagnostic, parse_bib_diagnostics


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """references.bib parse: brace balance + duplicate cite-keys."""
    rel = Path(corpus.config.bib)
    for msg in parse_bib_diagnostics(corpus.bib_path):
        yield Diagnostic(
            code="bib-error",
            severity="error",
            path=rel,
            message=msg,
        )
