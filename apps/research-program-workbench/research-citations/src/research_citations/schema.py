"""Reference schema: types and per-type required/optional fields.

Mirrors biblatex's expanded entry-type set. The schema is enforced softly:
unknown fields warn (configurable in the validator), missing required fields
are errors. Authors and editors are normalized to lists of strings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Reference types we accept. Extends BibTeX with biblatex's commonly-used
# additions (online, software, dataset, report, thesis).
TYPES: frozenset[str] = frozenset({
    "article", "book", "booklet", "inbook", "incollection",
    "inproceedings", "manual", "mastersthesis", "phdthesis", "thesis",
    "misc", "proceedings", "techreport", "report", "unpublished",
    "online", "software", "dataset", "patent", "inreference",
})

# Fields recognized for any type. Anything else triggers a warning when the
# strict schema check runs. Includes biblatex extras (eprint, eprinttype, ...).
COMMON_FIELDS: frozenset[str] = frozenset({
    "key", "type",
    "authors", "editors", "translators",
    "title", "subtitle", "shorttitle",
    "year", "month", "date",
    "journal", "booktitle", "series", "edition", "volume", "number", "pages",
    "publisher", "address", "institution", "organization", "school",
    "howpublished", "note",
    "doi", "isbn", "issn", "url", "urldate",
    "eprint", "eprinttype", "eprintclass", "archiveprefix", "primaryclass",
    "abstract", "keywords",
    "venue",  # legacy; mapped to journal/booktitle on render
})

# Required fields per type. Missing → error. Authors/editors are accepted
# interchangeably for several types; we only require "an author or editor"
# rather than authors specifically.
REQUIRED: dict[str, tuple[str, ...]] = {
    "article":        ("title", "year"),
    "book":           ("title", "year"),
    "booklet":        ("title",),
    "inbook":         ("title", "year"),
    "incollection":   ("title", "year", "booktitle"),
    "inproceedings":  ("title", "year", "booktitle"),
    "manual":         ("title",),
    "mastersthesis":  ("title", "year", "school"),
    "phdthesis":      ("title", "year", "school"),
    "thesis":         ("title", "year"),
    "misc":           (),
    "proceedings":    ("title", "year"),
    "techreport":     ("title", "year"),
    "report":         ("title", "year"),
    "unpublished":    ("title",),
    "online":         ("title",),
    "software":       ("title",),
    "dataset":        ("title",),
    "patent":         ("title", "year"),
    "inreference":    ("title", "year"),
}


@dataclass
class Reference:
    """A normalized reference entry."""
    key: str
    type: str
    fields: dict[str, Any]
    source_path: str | None = None  # the .md file declaring this reference
    declared_inline: bool = False   # True if from a citing note's `references:`,
                                    # False if from a `references/<key>.md` file

    @property
    def authors(self) -> list[str]:
        v = self.fields.get("authors") or []
        return _normalize_name_list(v)

    @property
    def editors(self) -> list[str]:
        v = self.fields.get("editors") or []
        return _normalize_name_list(v)

    @property
    def title(self) -> str:
        return str(self.fields.get("title") or "")

    @property
    def year(self) -> int | str | None:
        return self.fields.get("year")


def _normalize_name_list(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return []


@dataclass
class SchemaIssue:
    """A single schema problem found on a reference."""
    severity: str  # "error" or "warning"
    code: str
    key: str
    source_path: str | None
    message: str


def validate(ref: Reference) -> list[SchemaIssue]:
    """Check a reference against the schema. Returns a list of issues."""
    issues: list[SchemaIssue] = []
    if ref.type not in TYPES:
        issues.append(SchemaIssue(
            "warning", "unknown-type", ref.key, ref.source_path,
            f"unknown reference type `{ref.type}` (accepted: {sorted(TYPES)})",
        ))
    required = REQUIRED.get(ref.type, ())
    for f in required:
        v = ref.fields.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            issues.append(SchemaIssue(
                "error", "missing-required", ref.key, ref.source_path,
                f"missing required field `{f}` for type `{ref.type}`",
            ))
    # No author/editor on book/article-like types is suspicious but not fatal —
    # warn so it's surfaced.
    has_author_or_editor = bool(ref.authors or ref.editors)
    if ref.type in ("article", "book", "incollection", "inproceedings", "thesis",
                    "phdthesis", "mastersthesis") and not has_author_or_editor:
        issues.append(SchemaIssue(
            "warning", "missing-author", ref.key, ref.source_path,
            f"no `authors` or `editors` field for type `{ref.type}`",
        ))
    # Unknown fields → warn.
    for f in ref.fields:
        if f not in COMMON_FIELDS:
            issues.append(SchemaIssue(
                "warning", "unknown-field", ref.key, ref.source_path,
                f"unknown field `{f}` (will be passed to BibTeX as-is)",
            ))
    return issues
