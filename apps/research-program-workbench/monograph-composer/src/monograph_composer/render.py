"""Markdown rendering: kind-prefixed headings, demotion, link rewriting."""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Mapping

from research_corpus import find_markdown_links, resolve_link_slug
from research_corpus.corpus import Corpus, Note
from research_corpus.links import prose_links_text

KIND_LABEL: dict[str, str] = {
    "concept": "Concept",
    "definition": "Definition",
    "morphism": "Definition",
    "theorem": "Theorem",
    "lemma": "Lemma",
    "proposition": "Proposition",
    "corollary": "Corollary",
    "example": "Example",
    "question": "Open problem",
    "conjecture": "Conjecture",
}

H1_RE = re.compile(r"^# (.+?)(?:\s*\{#[^}]+\})?\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#+)(?=\s)", re.MULTILINE)
LEAN_SECTION_RE = re.compile(
    r"^## +Lean\b.*?(?=^#{1,2} |\Z)", re.MULTILINE | re.DOTALL,
)


def strip_lean_sections(body: str) -> str:
    """Remove H2 sections whose heading starts with 'Lean'. Lean mechanization
    is internal bookkeeping, not part of the published monograph."""
    return LEAN_SECTION_RE.sub("", body).rstrip() + "\n"


def extract_title_and_body(body: str, *, strip_lean: bool = True) -> tuple[str, str]:
    m = H1_RE.search(body if strip_lean else prose_links_text(body))
    if not m:
        return "", (strip_lean_sections(body) if strip_lean else body).strip()
    # The mask locates a real heading, but its capture lengths cannot recover
    # trailing inline code: masked code is indistinguishable from whitespace.
    m = H1_RE.match(body, m.start())
    assert m is not None
    title = m.group(1).strip()
    rest = body[: m.start()] + body[m.end():]
    return title, (strip_lean_sections(rest) if strip_lean else rest).strip()


def demote_headings(body: str, by: int, *, prose_only: bool = False) -> str:
    if by <= 0:
        return body
    if not prose_only:
        return HEADING_RE.sub(lambda m: "#" * (len(m.group(1)) + by), body)
    for match in reversed(list(HEADING_RE.finditer(prose_links_text(body)))):
        body = body[:match.start()] + "#" * by + body[match.start():]
    return body


def rewrite_links(body: str, all_slugs: set[str], *,
                   source_path: PurePosixPath | None = None,
                   path_slugs: Mapping[str, str] | None = None) -> str:
    # Apply backwards so offsets remain those of the original prose. The same
    # scanner as validation preserves code examples and handles nested paths.
    for link in reversed(find_markdown_links(body)):
        target = (resolve_link_slug(link, source_path, path_slugs)
                  if source_path is not None and path_slugs is not None else link.slug)
        if target in all_slugs:
            replacement = f"[{link.text}](#{link.fragment or target})"
            body = body[:link.start] + replacement + body[link.end:]
    return body


def render_preface(narr: Note, all_slugs: set[str], *, path_slugs=None) -> str:
    """Positionless overview narrative: H2, body subsections demoted by 1."""
    title, rest = extract_title_and_body(narr.body)
    rest = demote_headings(rest, 1)
    rest = rewrite_links(rest, all_slugs, source_path=narr.path, path_slugs=path_slugs)
    return f"## {title} {{#{narr.slug}}}\n\n{rest}\n"


def render_part(narr: Note, all_slugs: set[str], *, path_slugs=None) -> str:
    """Part narrative: H2."""
    title, rest = extract_title_and_body(narr.body)
    rest = demote_headings(rest, 1)
    rest = rewrite_links(rest, all_slugs, source_path=narr.path, path_slugs=path_slugs)
    return f"## {title} {{#{narr.slug}}}\n\n{rest}\n"


def render_chapter(narr: Note, all_slugs: set[str], *, path_slugs=None) -> str:
    """Chapter narrative: H3 inside a part."""
    title, rest = extract_title_and_body(narr.body)
    rest = demote_headings(rest, 2)
    rest = rewrite_links(rest, all_slugs, source_path=narr.path, path_slugs=path_slugs)
    return f"### {title} {{#{narr.slug}}}\n\n{rest}\n"


def render_block(note: Note, all_slugs: set[str], *, path_slugs=None) -> str:
    """Inline content block: H4, kind-prefixed."""
    title, rest = extract_title_and_body(note.body)
    rest = demote_headings(rest, 3)
    rest = rewrite_links(rest, all_slugs, source_path=note.path, path_slugs=path_slugs)
    label = KIND_LABEL.get(note.kind, note.kind.capitalize())
    badge = ""
    status = note.fm.get("status")
    if note.kind in ("theorem", "lemma", "proposition", "corollary", "conjecture") \
            and status and status != "proved":
        badge = f" [{status.upper()}]"
    if note.kind == "narrative":
        heading = f"#### {title} {{#{note.slug}}}"
    else:
        heading = f"#### {label}{badge}: {title} {{#{note.slug}}}"
    return f"{heading}\n\n{rest}\n"


def render_question(note: Note, all_slugs: set[str], *, path_slugs=None) -> str:
    title, rest = extract_title_and_body(note.body)
    rest = demote_headings(rest, 3)
    rest = rewrite_links(rest, all_slugs, source_path=note.path, path_slugs=path_slugs)
    label = KIND_LABEL["question"]
    status = note.fm.get("status", "open")
    badge = f" [{status.upper()}]" if status != "open" else ""
    explores = note.fm.get("explores") or []
    explores_links = ", ".join(f"[{e}](#{e})" for e in explores if e in all_slugs)
    explores_line = f"*Explores: {explores_links}*\n\n" if explores_links else ""
    heading = f"#### {label}{badge}: {title} {{#{note.slug}}}"
    return f"{heading}\n\n{explores_line}{rest}\n"


def render_appendix_questions(corpus: Corpus, all_slugs: set[str]) -> str:
    questions = sorted(
        s for s, n in corpus.items()
        if n.kind == "question"
        and n.fm.get("status") in (None, "open", "partial")
    )
    if not questions:
        return ""
    parts = ["### Open questions {#appendix-open-questions}", ""]
    parts.append(
        "Open mathematical and program-shaping questions, indexed by the "
        "entities they explore. Each question's `explores:` list points to "
        "the objects, concepts, or theorems that situate the inquiry.\n"
    )
    for s in questions:
        parts.append(render_question(corpus[s], all_slugs, path_slugs=corpus.path_slugs))
        parts.append("")
    return "\n".join(parts)


def render_appendix_further_reading(corpus: Corpus, all_slugs: set[str]) -> str:
    """Reference notes that aren't directly cited via [@key] — bibliographic
    background that situates the program. Cited works appear in the citeproc-
    generated References section."""
    from research_corpus import CITE_RE
    cited: set[str] = set()
    for n in corpus:
        if n.dir == "references":
            continue
        cited.update(CITE_RE.findall(n.body))
    refs = [(s, n) for s, n in sorted(corpus.items())
            if n.dir == "references" and s not in cited]
    if not refs:
        return ""
    parts = ["### Further reading {#appendix-further-reading}", ""]
    parts.append(
        "Works in the program's intellectual environment that situate the "
        "machinery but aren't directly cited on any specific claim. Each "
        "entry summarises the work and its relevance.\n"
    )
    for s, n in refs:
        title, rest = extract_title_and_body(n.body)
        rest = demote_headings(rest, 3)
        rest = rewrite_links(rest, all_slugs, source_path=n.path, path_slugs=corpus.path_slugs)
        fm = n.fm
        authors = fm.get("authors") or []
        year = fm.get("year") or ""
        ref_title = fm.get("title") or title or s
        if isinstance(authors, list) and authors:
            author_str = ", ".join(authors)
            display = f"{author_str} ({year}) — *{ref_title}*" if year else f"{author_str} — *{ref_title}*"
        else:
            display = title or s
        parts.append(f"#### {display} {{#{s}}}")
        parts.append("")
        parts.append(rest)
        parts.append("")
    return "\n".join(parts)


def source_note_slugs(corpus: Corpus) -> list[str]:
    """Typed source annotations outside the legacy root references directory."""
    return sorted(s for s, note in corpus.items()
                  if note.kind == "reference" and note.dir != "references")


def render_appendix_source_notes(corpus: Corpus, all_slugs: set[str]) -> str:
    """Keep nested typed source notes accessible without treating them as BibTeX.

    The primary order excludes reference notes. Every nested typed annotation
    therefore needs its own anchored body, even when another note cites its key.
    Source limitations (including headings about Lean) are part of that body.
    """
    slugs = source_note_slugs(corpus)
    if not slugs:
        return ""
    parts = ["### Source notes {#appendix-source-notes}", "",
             "Source annotations retain the inspected material, its scope and "
             "its relation to this research.\n"]
    for slug in slugs:
        note = corpus[slug]
        title, rest = extract_title_and_body(note.body, strip_lean=False)
        title = title or note.fm.get("title") or note.fm.get("name") or slug
        rest = rewrite_links(demote_headings(rest, 3, prose_only=True), all_slugs,
                             source_path=note.path, path_slugs=corpus.path_slugs)
        parts.extend([f"#### {title} {{#{slug}}}", "", rest, ""])
    return "\n".join(parts)
