"""Cite-key generation following Better BibTeX's `[auth][year][shorttitle]`.

The default cite-key is `<firstauthor-lastname><year><veryshorttitle>`,
lowercase ASCII, alphanumeric only, no separators. Collisions append a/b/c.

Examples:
  Arnold (1995), "Remarks on eigenvalues..."  → arnold1995remarks
  Bik & Draisma (2020), "Euclidean distance"  → bik2020euclidean
  V. I. Arnold (1995), "Hermitian stratification" → arnold1995hermitian
  van der Waerden (1927), "Beweis"            → vanderwaerden1927beweis
  No author, 2024, "Some title"               → notitle2024some  (fallback: 'untitled' if also no title)
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# Title words skipped when picking a "veryshorttitle".
_TITLE_STOPWORDS = frozenset({
    "a", "an", "the",
    "and", "or", "but", "for", "nor", "so", "yet",
    "of", "in", "on", "at", "to", "from", "by", "with", "about", "as",
    "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those",
    "some", "any", "no",
    "via", "using",
    "n", "non",  # very short prefixes
})


def _ascii(s: str) -> str:
    """Strip diacritics and non-ASCII; lowercase; keep alphanumerics only."""
    nfkd = unicodedata.normalize("NFKD", s)
    out = "".join(c for c in nfkd if not unicodedata.combining(c))
    out = out.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "", out).lower()


def extract_lastname(author: str) -> str:
    """Best-effort lastname extraction.

    - "Lastname, Firstname"     → "Lastname"
    - "Firstname M. Lastname"   → "Lastname" (last whitespace token after stripping initials)
    - "van der Waerden, Bartel" → "van der Waerden" (everything before the comma)
    """
    s = author.strip()
    if "," in s:
        return s.split(",", 1)[0].strip()
    parts = s.split()
    if not parts:
        return ""
    # Drop trailing dotted initials (rare, but handles "Smith J.")
    while len(parts) > 1 and re.fullmatch(r"[A-Z]\.?", parts[-1]):
        parts.pop()
    return parts[-1]


def _veryshorttitle(title: str, max_len: int = 12) -> str:
    """First significant word of `title`, truncated to `max_len` chars."""
    if not title:
        return ""
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", title)
    for w in words:
        if w.lower() in _TITLE_STOPWORDS:
            continue
        return _ascii(w)[:max_len]
    return _ascii(words[0])[:max_len] if words else ""


def base_key(authors: Iterable[str] | None,
             year: int | str | None,
             title: str | None) -> str:
    """Generate a cite-key without collision suffix.

    Returns "" if nothing usable is provided (caller decides to fall back to
    `misc<year>` or `untitled<n>`).
    """
    author_part = ""
    if authors:
        first = next(iter(authors), None)
        if first:
            author_part = _ascii(extract_lastname(first))

    year_part = ""
    if year is not None and str(year).strip():
        year_part = _ascii(str(year))[:4]  # take 4-digit year prefix

    title_part = _veryshorttitle(title or "")

    if not author_part and not title_part:
        return ""
    return f"{author_part}{year_part}{title_part}"


def disambiguate(key: str, existing: set[str]) -> str:
    """If `key` is already in `existing`, append a/b/c/... until unique.

    Mirrors Better BibTeX's collision-suffix behavior.
    """
    if key not in existing:
        return key
    # a, b, ..., z, aa, ab, ...
    from string import ascii_lowercase
    n = 0
    while True:
        suffix = ""
        m = n
        # base-26 with a=0
        while True:
            suffix = ascii_lowercase[m % 26] + suffix
            m //= 26
            if m == 0:
                break
            m -= 1
        cand = f"{key}{suffix}"
        if cand not in existing:
            return cand
        n += 1


def generate(authors: Iterable[str] | None,
             year: int | str | None,
             title: str | None,
             existing: set[str] | None = None) -> str:
    """Generate a unique cite-key. `existing` carries already-used keys."""
    base = base_key(authors, year, title)
    if not base:
        # Last-ditch fallback.
        year_part = _ascii(str(year))[:4] if year else ""
        base = f"misc{year_part}" if year_part else "untitled"
    if existing is None:
        return base
    return disambiguate(base, existing)
