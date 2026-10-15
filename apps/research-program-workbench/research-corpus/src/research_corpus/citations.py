from __future__ import annotations

import re
from pathlib import Path

CITE_RE = re.compile(r"\[@([a-z][a-z0-9\-]*\d{4}[a-z]?)\]")
_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([A-Za-z0-9\-]+)\s*,")


def parse_bib_keys(bib_path: Path) -> set[str]:
    """Cite-keys declared in a BibTeX file. Comment entries are skipped."""
    if not bib_path.is_file():
        return set()
    keys: set[str] = set()
    for m in _BIB_ENTRY_RE.finditer(bib_path.read_text()):
        if m.group(1).lower() == "comment":
            continue
        keys.add(m.group(2))
    return keys


def parse_bib_diagnostics(bib_path: Path) -> list[str]:
    """Brace-imbalance and duplicate-cite-key issues in `bib_path`.

    Returns a list of human-readable error strings; empty if clean. Returns
    empty if the file does not exist (the caller decides whether that's an
    error in their context).
    """
    if not bib_path.is_file():
        return []
    text = bib_path.read_text()
    errors: list[str] = []
    if text.count("{") != text.count("}"):
        errors.append(
            f"brace imbalance: {text.count('{')} open vs {text.count('}')} close"
        )
    seen: set[str] = set()
    dups: set[str] = set()
    for m in _BIB_ENTRY_RE.finditer(text):
        if m.group(1).lower() == "comment":
            continue
        k = m.group(2)
        if k in seen:
            dups.add(k)
        seen.add(k)
    if dups:
        errors.append(f"duplicate cite-keys: {sorted(dups)}")
    return errors
