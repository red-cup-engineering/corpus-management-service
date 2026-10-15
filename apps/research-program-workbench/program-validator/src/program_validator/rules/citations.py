from __future__ import annotations

from typing import Iterator

from research_corpus import CITE_RE, Corpus, Diagnostic


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Pandoc `[@key]` citations resolve; references/ filesystem is consistent."""
    bib_keys = corpus.bib_keys
    cited: set[str] = set()

    for note in corpus:
        for key in CITE_RE.findall(note.body):
            if key not in bib_keys:
                yield Diagnostic(
                    code="broken-citation",
                    severity="error",
                    path=note.path,
                    message=f"cites missing bib key `{key}`",
                    extra={"slug": note.slug, "key": key},
                )
            else:
                cited.add(key)

    refs_dir = corpus.root / "references"
    sources_dir = refs_dir / "sources"
    has_bib = corpus.bib_path.is_file()

    if refs_dir.is_dir():
        ann_keys = {p.stem for p in refs_dir.glob("*.md") if p.name != "README.md"}
        # Only flag annotations as orphans when a bib actually exists. A
        # project that uses annotation-only references (no centralized
        # references.bib) is a legitimate style — the annotations *are* the
        # references — and every annotation would otherwise hard-fail.
        if has_bib:
            for stem in sorted(ann_keys - bib_keys):
                yield Diagnostic(
                    code="orphan-annotation",
                    severity="error",
                    path=refs_dir.relative_to(corpus.root) / f"{stem}.md",
                    message=f"annotation file without bib entry: `{stem}`",
                    extra={"key": stem},
                )
            for key in sorted(cited - ann_keys):
                yield Diagnostic(
                    code="missing-annotation",
                    severity="warning",
                    path=None,
                    message=f"cited bib key without annotation file: `{key}`",
                    extra={"key": key},
                )

    if sources_dir.is_dir() and has_bib:
        pdf_keys = {p.stem for p in sources_dir.glob("*.pdf")}
        for stem in sorted(pdf_keys - bib_keys):
            yield Diagnostic(
                code="orphan-pdf",
                severity="error",
                path=sources_dir.relative_to(corpus.root) / f"{stem}.pdf",
                message=f"source PDF without bib entry: `{stem}`",
                extra={"key": stem},
            )
