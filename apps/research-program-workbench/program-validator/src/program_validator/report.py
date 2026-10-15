"""Render Diagnostics into the WIP markdown report."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from research_corpus import Corpus, Diagnostic

# Section title and ordering for the WIP report. Codes not listed here still
# appear at the bottom under "Other".
SECTIONS: list[tuple[str, str]] = [
    ("frontmatter-parse",   "Parse errors"),
    ("slug-collision",      "Slug collisions"),
    ("bib-error",           "references.bib errors"),
    ("broken-link",         "Broken cross-references"),
    ("broken-citation",     "Broken citations"),
    ("orphan-annotation",   "Orphan annotation files (references/<key>.md without bib entry)"),
    ("orphan-pdf",          "Orphan source PDFs (references/sources/<key>.pdf without bib entry)"),
    ("missing-annotation",  "Cited bib keys without annotation files"),
    ("symbol-collision",    "Symbol collisions (frontmatter `symbol:`)"),
    ("cycle",               "Cycles in depends-on"),
    ("status-inconsistency", "Status inconsistencies (proved → unproved)"),
    ("cite-not-in-manifest", "Body cites missing from frontmatter `references:`"),
    ("manifest-key-unresolved", "Manifest keys without an annotation or inline declaration"),
    ("missing-status",      "Theorems missing status"),
    ("missing-proof",       "Theorems with status: proved but no proof section"),
    ("wip-theorem",         "WIP theorems (sketch / draft)"),
    ("stub",                "Stubs (body below threshold)"),
    ("orphan",              "Orphans (no incoming refs)"),
]

LEAN_CODES = {
    "lean-build-failed", "lean-source-frontier", "lean-lemma-missing",
    "lean-module-missing", "lean-no-dir", "lean-lake-missing", "lean-lake-timeout",
}


def group(diagnostics: Iterable[Diagnostic]) -> dict[str, list[Diagnostic]]:
    out: dict[str, list[Diagnostic]] = defaultdict(list)
    for d in diagnostics:
        out[d.code].append(d)
    return out


def render(corpus: Corpus, diagnostics: list[Diagnostic]) -> str:
    grouped = group(diagnostics)
    lines: list[str] = []
    title = corpus.config.compose.title or corpus.root.name
    lines.append(f"# Library status report — {title}\n")
    lines.append(f"Total notes: {len(corpus)}\n")

    def section(title: str, items: list[Diagnostic]) -> None:
        lines.append(f"## {title} ({len(items)})\n")
        if not items:
            lines.append("*(none)*\n")
            return
        for d in items:
            prefix = f"`{d.path}`: " if d.path is not None else ""
            lines.append(f"- {prefix}{d.message}")
        lines.append("")

    for code, title in SECTIONS:
        section(title, grouped.get(code, []))

    lean_items = [d for c in LEAN_CODES for d in grouped.get(c, [])]
    section("Lean source observations (not a proof-realization verdict)", lean_items)

    rendered_codes = {c for c, _ in SECTIONS} | LEAN_CODES
    other_codes = [c for c in grouped if c not in rendered_codes]
    if other_codes:
        items = [d for c in other_codes for d in grouped[c]]
        section("Other", items)

    lines.append(_lean_coupling_section(corpus))
    return "\n".join(lines)


def _lean_coupling_section(corpus: Corpus) -> str:
    proved_kinds = ("theorem", "conjecture", "lemma", "proposition", "corollary")
    lean_coupled = sorted(s for s, n in corpus.items() if n.fm.get("lean"))
    proved = sorted(s for s, n in corpus.items()
                    if n.kind in proved_kinds and n.fm.get("status") == "proved")
    proved_with_lean = sorted(s for s in proved if corpus[s].fm.get("lean"))

    out = [f"## Lean coupling ({len(lean_coupled)} prose notes carry `lean:`)\n"]
    if proved:
        pct = 100.0 * len(proved_with_lean) / len(proved)
        out.append(
            f"Proved theorems with Lean: {len(proved_with_lean)} / "
            f"{len(proved)} ({pct:.0f}%).\n"
        )
    if lean_coupled:
        out.append("Notes carrying a `lean:` ref:\n")
        for s in lean_coupled:
            out.append(f"- `{s}`")
        out.append("")
    return "\n".join(out)
