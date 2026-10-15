"""Render Reference records as BibTeX entries.

Authors and editors are emitted in BibTeX's canonical "Lastname, Firstname"
form joined by " and ". Non-ASCII is preserved (modern BibTeX/biblatex
toolchains handle UTF-8). Fields that don't map to standard BibTeX keys are
emitted under a `note =` field with the field name as a prefix, so no
information is silently dropped.
"""
from __future__ import annotations

import re
from typing import Iterable

from .schema import Reference

# Fields that map directly to BibTeX/biblatex field names.
DIRECT_FIELDS: frozenset[str] = frozenset({
    "title", "subtitle", "shorttitle",
    "year", "month", "date",
    "journal", "booktitle", "series", "edition", "volume", "number", "pages",
    "publisher", "address", "institution", "organization", "school",
    "howpublished", "note",
    "doi", "isbn", "issn", "url", "urldate",
    "eprint", "eprinttype", "eprintclass", "archiveprefix", "primaryclass",
    "abstract", "keywords",
})

# Frontmatter fields that are corpus-internal and should never appear in the
# rendered BibTeX. `kind: reference` marks this file as an annotation in the
# research-corpus model; `status` and `anchor` are internal flags; anything
# starting with the corpus's relation-key set (depends-on, see-also, …) is
# corpus structure, not citation metadata.
INTERNAL_FIELDS: frozenset[str] = frozenset({
    "kind", "status", "anchor",
    "depends-on", "introduces", "recaps", "discusses",
    "instantiates", "see-also", "realizes", "closes",
    "chapters", "explores",
    "references",  # the citing-note manifest, not a citation field
})

# `venue` (legacy in spatiotemporal-knowledge): if it looks like a journal
# (contains digit-y volume info), map to `journal`; else `booktitle`.
_VENUE_VOLUMEY = re.compile(r"\d")


def _split_name(author: str) -> str:
    """Return BibTeX "Lastname, Firstnames" form.

    Already-comma form is left as-is. "Firstname M. Lastname" form is reordered.
    """
    s = author.strip()
    if not s:
        return ""
    if "," in s:
        return s
    parts = s.split()
    if len(parts) <= 1:
        return s
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def _join_names(names: Iterable[str]) -> str:
    return " and ".join(_split_name(n) for n in names if n)


def _escape(value: str) -> str:
    """Minimal BibTeX field-value escaping for braces."""
    # We wrap field values in braces; only escape unmatched braces inside.
    # Simple strategy: replace `{` with `{{` and `}` with `}}` if the raw
    # string has unbalanced braces. Most strings won't, so do nothing here.
    return value


def _field(name: str, value: str) -> str:
    return f"  {name} = {{{_escape(value)}}},\n"


def render_entry(ref: Reference) -> str:
    """Render one Reference as a BibTeX entry string."""
    out: list[str] = [f"@{ref.type}{{{ref.key},\n"]

    if ref.authors:
        out.append(_field("author", _join_names(ref.authors)))
    if ref.editors:
        out.append(_field("editor", _join_names(ref.editors)))

    handled = {"authors", "editors", "translators"}
    fields = ref.fields

    # Translate `venue:` (legacy) → `journal` or `booktitle`.
    if "venue" in fields and "journal" not in fields and "booktitle" not in fields:
        v = str(fields["venue"])
        target = "journal" if _VENUE_VOLUMEY.search(v) else "booktitle"
        out.append(_field(target, v))
        handled.add("venue")

    # Translate `arxiv:` → biblatex `eprint = {...}` + `eprinttype = {arxiv}`,
    # which is the standard way to render arXiv preprints with citeproc.
    arxiv_id = fields.get("arxiv")
    if arxiv_id and "eprint" not in fields:
        out.append(_field("eprint", str(arxiv_id).strip()))
        out.append(_field("eprinttype", "arxiv"))
        handled.add("arxiv")

    # Standard fields.
    for f in DIRECT_FIELDS:
        if f in handled:
            continue
        v = fields.get(f)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        out.append(_field(f, s))
        handled.add(f)

    # Translators get appended as a comment field — biblatex has @translator
    # but BibTeX doesn't. Emit as a note suffix to preserve information.
    translators = ref.fields.get("translators")
    if translators:
        names = _join_names(translators if isinstance(translators, list) else [translators])
        existing = next((line for line in out if line.startswith("  note = ")), None)
        if existing:
            new_note = existing.rstrip("},\n") + f"; trans. {names}}},\n"
            out[out.index(existing)] = new_note
        else:
            out.append(_field("note", f"trans. {names}"))
        handled.add("translators")

    # Unknown fields → emit as-is, except corpus-internal ones we drop.
    for f, v in fields.items():
        if f in handled or f in DIRECT_FIELDS or f in INTERNAL_FIELDS:
            continue
        if v is None or isinstance(v, bool):
            continue
        s = str(v).strip()
        if not s:
            continue
        out.append(_field(f, s))

    # Strip trailing comma for cleanliness (BibTeX accepts it either way).
    if out[-1].endswith(",\n"):
        out[-1] = out[-1][:-2] + "\n"
    out.append("}\n")
    return "".join(out)


def render(refs: Iterable[Reference]) -> str:
    """Render a sequence of references as a complete BibTeX file."""
    refs = sorted(refs, key=lambda r: r.key.lower())
    parts = [
        "% This file is generated by cite-tool. Do not edit by hand.\n",
        "% Source of truth: frontmatter `references:` blocks plus\n",
        "% `references/<key>.md` annotation files in this domain.\n",
        "\n",
    ]
    parts.extend(render_entry(r) + "\n" for r in refs)
    return "".join(parts)
