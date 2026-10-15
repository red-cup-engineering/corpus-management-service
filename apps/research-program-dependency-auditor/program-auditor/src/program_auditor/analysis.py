from __future__ import annotations

import re
from typing import Mapping

from research_corpus import (
    LINK_RE,
    ancestors as ancestors_set,
    descendants as descendants_set,
    descendant_counts,
    foundation_distance,
    reverse_depends_on,
)
from research_corpus.corpus import Corpus

SECTION_RE = re.compile(r"^(#{2,6})\s+(.+?)(?:\s*\{#[^}]+\})?\s*$", re.MULTILINE)

# H2 headings that introduce informational / forward-pointer sections —
# references inside these are not load-bearing dependencies.
INFORMATIONAL_HEADING_PATTERNS = [
    r"^position in\b",
    r"^connection(s)? to\b",
    r"^connection(s)? with\b",
    r"^connect(s|ion) to\b",
    r"^comparison with\b",
    r"^comparison to\b",
    r"^reading\b",
    r"^what this gives\b",
    r"^what this proves\b",
    r"^what is established\b",
    r"^what is settled\b",
    r"^what is proved\b",
    r"^what.s actually proved\b",
    r"^what.s open\b",
    r"^what.s still open\b",
    r"^what.s missing\b",
    r"^what.s left\b",
    r"^what is missing\b",
    r"^open question(s)?\b",
    r"^open work\b",
    r"^open(s)? to\b",
    r"^status remarks\b",
    r"^status by regime\b",
    r"^future direction(s)?\b",
    r"^downstream consequence(s)?\b",
    r"^downstream(\s|$)",
    r"^remark(s)?(\s|$)",
    r"^conjecture(s)?(\s|$)",
    r"^open conjecture(s)?\b",
    r"^higher.degree\b",
    r"^higher.cell\b",
    r"^higher dimension(s)?\b",
    r"^cosheaf-side\b",
    r"^cosheaf side\b",
    r"^refined classification\b",
    r"^refinement under\b",
    r"^why\b",
    r"^non.degeneracy criterion\b",
    r"^application(s)?\b",
    r"^specialization to\b",
    r"^specialisation to\b",
    r"^when\b",
    r"^a concrete positive case\b",
    r"^side observation\b",
    r"^cardinality boundary\b",
    r"^the boundary at\b",
]
INFORMATIONAL_HEADING_RE = re.compile(
    "|".join(INFORMATIONAL_HEADING_PATTERNS), re.IGNORECASE,
)


def _split_into_sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    cursor = 0
    last_heading = ""
    for m in SECTION_RE.finditer(body):
        if len(m.group(1)) != 2:
            continue
        sections.append((last_heading, body[cursor:m.start()]))
        last_heading = m.group(2).strip()
        cursor = m.end()
    sections.append((last_heading, body[cursor:]))
    return sections


def _is_informational(heading: str) -> bool:
    if not heading:
        return False
    return bool(INFORMATIONAL_HEADING_RE.match(heading.strip()))


def load_bearing_links(body: str, self_slug: str) -> set[str]:
    """Slug references in non-informational sections of `body`."""
    out: set[str] = set()
    for heading, content in _split_into_sections(body):
        if _is_informational(heading):
            continue
        for m in LINK_RE.finditer(content):
            slug = m.group(2)
            if slug != self_slug:
                out.add(slug)
    return out


def all_body_links(body: str, self_slug: str) -> set[str]:
    return {m[1] for m in LINK_RE.findall(body) if m[1] != self_slug}


def crossref_vs_depends_on(corpus: Corpus,
                           rev: Mapping[str, list[str]] | None = None,
                           *,
                           section_filter: bool = True,
                           drop_descendants: bool = True,
                           drop_siblings: bool = True,
                           drop_kinds: tuple[str, ...] = ("narrative", "question"),
                           skip_citing_kinds: tuple[str, ...] = (
                               "narrative", "question", "reference"),
                           ) -> dict[str, dict]:
    """Per-note: classify body-link targets relative to the citing note's
    `depends-on`. Buckets:
      - body_not_in_deps_unrelated: outside neighborhood (highest signal)
      - body_not_in_deps_sibling:   in a sibling/cousin lineage
      - body_not_in_deps_ancestor:  transitive ancestor (dependency implicit)
      - deps_not_in_body:           depends-on lists M but body never cites it
    """
    if rev is None:
        rev = reverse_depends_on(corpus.notes)
    out: dict[str, dict] = {}
    for slug, n in corpus.items():
        if skip_citing_kinds and n.kind in skip_citing_kinds:
            continue
        body_links = (load_bearing_links if section_filter else all_body_links)(n.body, slug)
        body_links = {b for b in body_links if b in corpus}
        if drop_kinds:
            body_links = {b for b in body_links if corpus[b].kind not in drop_kinds}
        deps = set(n.fm.get("depends-on") or []) & corpus.slugs()

        anc = ancestors_set(slug, corpus.notes) if drop_descendants else set()
        descs = descendants_set(slug, rev) if (drop_descendants and rev is not None) else set()

        sibling_closure: set[str] = set()
        if drop_siblings and rev is not None:
            for d in deps:
                sibling_closure |= descendants_set(d, rev)
            sibling_closure.discard(slug)
            sibling_closure -= descs

        through_ancestor: list[str] = []
        sibling: list[str] = []
        unrelated: list[str] = []

        for m in body_links - deps:
            if drop_descendants and m in descs:
                continue
            if m in anc:
                through_ancestor.append(m)
            elif drop_siblings and m in sibling_closure:
                sibling.append(m)
            else:
                unrelated.append(m)

        deps_not_in_body = sorted(deps - body_links)
        if unrelated or sibling or through_ancestor or deps_not_in_body:
            out[slug] = {
                "body_not_in_deps_unrelated": sorted(unrelated),
                "body_not_in_deps_sibling": sorted(sibling),
                "body_not_in_deps_ancestor": sorted(through_ancestor),
                "deps_not_in_body": deps_not_in_body,
                "body_not_in_deps": sorted(unrelated + sibling + through_ancestor),
            }
    return out


def descendant_count_map(corpus: Corpus) -> dict[str, int]:
    return descendant_counts(corpus.notes)


def foundation_distance_map(corpus: Corpus) -> dict[str, int]:
    return foundation_distance(corpus.notes)
