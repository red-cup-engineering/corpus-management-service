from __future__ import annotations

from typing import Iterator

from research_corpus import Corpus, Diagnostic, find_markdown_links


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Relative Markdown links name real files within the selected root.

    Resolve from the citing note's directory, never by filename similarity.
    Unindexed local navigation files are allowed without adding them to the
    scientific corpus. This does not check URL availability or anchor semantics.
    """
    root = corpus.root.resolve()
    for note in corpus:
        for link in find_markdown_links(note.body):
            destination = (root / note.path.parent / link.path).resolve()
            if not destination.is_relative_to(root) or not destination.is_file():
                yield Diagnostic(
                    code="broken-link",
                    severity="error",
                    path=note.path,
                    message=f"relative Markdown target `{link.target}` is missing or outside the selected root",
                    extra={"slug": note.slug, "target": link.target},
                )
