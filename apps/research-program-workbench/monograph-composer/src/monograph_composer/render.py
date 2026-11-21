"""Markdown rendering: kind-prefixed headings, demotion, link rewriting."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping
from urllib.parse import quote

from research_corpus import find_markdown_links, relation_targets
from research_corpus.links import MarkdownLink
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
LEADING_NOTE_HEADING_RE = re.compile(
    r"\A(?:[ \t]*\n)* {0,3}#{1,6}[ \t]+(?P<title>.*?\S)[ \t]+"
    r"\{#(?P<anchor>[^}\s]+)\}[ \t]*(?:\n|$)"
)
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


@dataclass(frozen=True)
class ReaderTargets:
    root: Path
    indexed: Mapping[str, str]
    emitted: set[str]
    output_dir: Path | None

    def destination(self, source_path: PurePosixPath, link: MarkdownLink) -> str | None:
        relative = PurePosixPath(link.path)
        if source_path.is_absolute() or relative.is_absolute():
            return None
        parts = (*source_path.parent.parts, *relative.parts)
        target = self.root
        try:
            for i, part in enumerate(parts):
                if part == "..":
                    if target == self.root:
                        return None
                    target = target.parent
                    continue
                target /= part
                if target.is_symlink() or (i < len(parts) - 1 and not target.is_dir()):
                    return None
            if not target.is_file():
                return None
        except (OSError, ValueError):
            return None

        slug = self.indexed.get(target.relative_to(self.root).as_posix())
        boundary = re.search(r"[?#]", link.target)
        if slug in self.emitted and boundary is None:
            return "#" + slug
        if self.output_dir is None:
            return None
        # Only the document wrapper is guaranteed to exist in the reader.
        # A file's query/section still belongs to the original file.
        path = quote(Path(os.path.relpath(target, self.output_dir)).as_posix())
        return path + (link.target[boundary.start():] if boundary else "")


def rewrite_links(body: str, source_path: PurePosixPath, targets: ReaderTargets) -> str:
    # Apply backwards so offsets remain those of the original prose. Replacing
    # just the target retains formatting, angle delimiters, and optional title.
    for link in reversed(find_markdown_links(body)):
        replacement = targets.destination(source_path, link)
        if replacement is not None:
            start = link.start + len(link.text) + len("[](")
            if body[start] == "<":
                start += 1
            body = body[:start] + replacement + body[start + len(link.target):]
    return body


def _render_note_contents(
    note: Note, targets: ReaderTargets, heading_offset: int, *,
    strip_lean: bool = True,
) -> tuple[str, str]:
    """Receive a leading same-ID title at the existing canonical wrapper."""
    leading = LEADING_NOTE_HEADING_RE.match(note.body)
    if leading is not None and leading["anchor"] == note.slug:
        title = leading["title"]
        rest = note.body[leading.end():]
        if strip_lean:
            # Preserve headings inside literal code in a promoted note too.
            for section in reversed(list(LEAN_SECTION_RE.finditer(prose_links_text(rest)))):
                rest = rest[:section.start()] + rest[section.end():]
        rest = demote_headings(rest.strip(), heading_offset, prose_only=True)
    else:
        title, rest = extract_title_and_body(note.body, strip_lean=strip_lean)
        rest = demote_headings(rest, heading_offset, prose_only=not strip_lean)
    return (rewrite_links(title, note.path, targets),
            rewrite_links(rest, note.path, targets))


def render_preface(narr: Note, targets: ReaderTargets) -> str:
    """Positionless overview narrative: H2, body subsections demoted by 1."""
    title, rest = _render_note_contents(narr, targets, 1)
    return f"## {title} {{#{narr.slug}}}\n\n{rest}\n"


def render_part(narr: Note, targets: ReaderTargets) -> str:
    """Part narrative: H2."""
    title, rest = _render_note_contents(narr, targets, 1)
    return f"## {title} {{#{narr.slug}}}\n\n{rest}\n"


def render_chapter(narr: Note, targets: ReaderTargets) -> str:
    """Chapter narrative: H3 inside a part."""
    title, rest = _render_note_contents(narr, targets, 2)
    return f"### {title} {{#{narr.slug}}}\n\n{rest}\n"


def render_block(note: Note, targets: ReaderTargets) -> str:
    """Inline content block: H4, kind-prefixed."""
    title, rest = _render_note_contents(note, targets, 3)
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


def render_question(note: Note, targets: ReaderTargets) -> str:
    title, rest = _render_note_contents(note, targets, 3)
    label = KIND_LABEL["question"]
    status = note.fm.get("status", "open")
    badge = f" [{status.upper()}]" if status != "open" else ""
    explores = relation_targets(note.fm, "explores")
    explores_links = ", ".join(f"[{e}](#{e})" for e in explores if e in targets.emitted)
    explores_line = f"*Explores: {explores_links}*\n\n" if explores_links else ""
    heading = f"#### {label}{badge}: {title} {{#{note.slug}}}"
    return f"{heading}\n\n{explores_line}{rest}\n"


def question_slugs(corpus: Corpus) -> list[str]:
    return sorted(
        s for s, n in corpus.items()
        if n.kind == "question" and n.fm.get("status") in (None, "open", "partial")
    )


def render_appendix_questions(corpus: Corpus, targets: ReaderTargets, questions: list[str]) -> str:
    if not questions:
        return ""
    parts = ["### Open questions {#appendix-open-questions}", ""]
    parts.append(
        "Open mathematical and program-shaping questions, indexed by the "
        "entities they explore. Each question's `explores:` list points to "
        "the objects, concepts, or theorems that situate the inquiry.\n"
    )
    for s in questions:
        parts.append(render_question(corpus[s], targets))
        parts.append("")
    return "\n".join(parts)


def further_reading_slugs(corpus: Corpus) -> list[str]:
    """Uncited legacy reference notes; cited works belong to citeproc."""
    from research_corpus import CITE_RE
    cited: set[str] = set()
    for n in corpus:
        if n.dir != "references":
            cited.update(CITE_RE.findall(n.body))
    return [s for s, n in sorted(corpus.items()) if n.dir == "references" and s not in cited]


def render_appendix_further_reading(corpus: Corpus, targets: ReaderTargets, refs: list[str]) -> str:
    if not refs:
        return ""
    parts = ["### Further reading {#appendix-further-reading}", ""]
    parts.append(
        "Works in the program's intellectual environment that situate the "
        "machinery but aren't directly cited on any specific claim. Each "
        "entry summarises the work and its relevance.\n"
    )
    for s in refs:
        n = corpus[s]
        title, rest = _render_note_contents(n, targets, 3)
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


def render_appendix_source_notes(corpus: Corpus, targets: ReaderTargets, slugs: list[str]) -> str:
    """Keep nested typed source notes accessible without treating them as BibTeX.

    The primary order excludes reference notes. Every nested typed annotation
    therefore needs its own anchored body, even when another note cites its key.
    Source limitations (including headings about Lean) are part of that body.
    """
    if not slugs:
        return ""
    parts = ["### Source notes {#appendix-source-notes}", "",
             "Source annotations retain the inspected material, its scope and "
             "its relation to this research.\n"]
    for slug in slugs:
        note = corpus[slug]
        title, rest = _render_note_contents(note, targets, 3, strip_lean=False)
        title = title or note.fm.get("title") or note.fm.get("name") or slug
        parts.extend([f"#### {title} {{#{slug}}}", "", rest, ""])
    return "\n".join(parts)
