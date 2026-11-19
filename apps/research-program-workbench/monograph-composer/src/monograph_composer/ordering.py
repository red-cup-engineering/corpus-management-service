"""Chapter assignment for monographs: parts, anchor-introduces, fallbacks."""
from __future__ import annotations

import re

from research_corpus import transitive_deps
from research_corpus.corpus import Corpus

ANCHOR_KINDS = frozenset({"definition", "concept", "morphism"})
PART_RE = re.compile(r"part-(\d+)")


def part_assignments(corpus: Corpus) -> tuple[dict[str, int], list[str]]:
    """Each part-narrative declares its chapters via `chapters: [...]`.

    Returns:
      chapter_to_part: chapter slug → part number
      part_narrative_slugs: part-narrative slugs in book order
    """
    part_narratives: list[str] = []
    chapter_to_part: dict[str, int] = {}
    for slug, n in corpus.items():
        if n.kind != "narrative":
            continue
        if n.fm.get("chapters"):
            part_narratives.append(slug)

    def part_num(s: str) -> int:
        m = PART_RE.search(s)
        return int(m.group(1)) if m else 999

    part_narratives.sort(key=part_num)
    for slug in part_narratives:
        pn = part_num(slug)
        for ch in corpus[slug].fm.get("chapters") or []:
            chapter_to_part[ch] = pn
    return chapter_to_part, part_narratives


def assign_chapters(
    order: list[str],
    corpus: Corpus,
) -> tuple[dict[str | None, list[str]], list[str], dict[int, str]]:
    """Group `order` slugs by chapter.

    Returns:
      chapter_content: chapter-slug | None → list of slugs in order
      chapter_order: chapter slugs (narratives) in declared book order
      part_num_to_narrative: part number → part-narrative slug
    """
    chapter_to_part, part_narrative_slugs = part_assignments(corpus)
    part_num_to_narrative: dict[int, str] = {}
    for slug in part_narrative_slugs:
        m = PART_RE.search(slug)
        if m:
            part_num_to_narrative[int(m.group(1))] = slug

    chapter_order: list[str] = []
    for pn_slug in sorted(part_num_to_narrative.values(),
                          key=lambda s: int(PART_RE.search(s).group(1))):
        for ch in corpus[pn_slug].fm.get("chapters") or []:
            chapter_order.append(ch)
    chapter_rank = {s: i for i, s in enumerate(chapter_order)}

    anchor_to_chapter: dict[str, str] = {}
    for ch in chapter_order:
        for t in (corpus[ch].fm.get("introduces") or []):
            if t in corpus and t not in anchor_to_chapter \
                    and corpus[t].kind in ANCHOR_KINDS:
                anchor_to_chapter[t] = ch
    chapter_intros = set(anchor_to_chapter.keys())

    tdeps_cache: dict[str, set[str]] = {}

    def tdeps(s: str) -> set[str]:
        if s not in tdeps_cache:
            tdeps_cache[s] = transitive_deps(s, corpus.notes)
        return tdeps_cache[s]

    anchor_tdeps = {a: tdeps(a) for a in chapter_intros}

    dependents: dict[str, set[str]] = {s: set() for s in corpus.notes}
    for s in corpus.notes:
        for d in (corpus[s].fm.get("depends-on") or []):
            if d in dependents:
                dependents[d].add(s)

    chapter_cache: dict[str, str | None] = {}

    def assign(slug: str, _stack: tuple[str, ...] = ()) -> str | None:
        if slug in chapter_cache:
            return chapter_cache[slug]
        if slug in _stack:
            return None
        if slug in chapter_rank:
            chapter_cache[slug] = slug
            return slug
        if slug in anchor_to_chapter:
            chapter_cache[slug] = anchor_to_chapter[slug]
            return anchor_to_chapter[slug]

        n = corpus[slug]
        closes_target = n.fm.get("closes")
        if closes_target in anchor_to_chapter:
            ch = anchor_to_chapter[closes_target]
            chapter_cache[slug] = ch
            return ch

        if n.kind == "narrative":
            for key in ("introduces", "recaps", "discusses"):
                targets = n.fm.get(key) or []
                tc = [assign(t, _stack + (slug,)) for t in targets if t in corpus]
                tc = [c for c in tc if c is not None]
                if tc:
                    pick = (min if key == "introduces" else max)(
                        tc,
                        key=lambda c: chapter_rank.get(
                            c, len(chapter_rank) if key == "introduces" else -1),
                    )
                    chapter_cache[slug] = pick
                    return pick
            chapter_cache[slug] = None
            return None

        # Upstream rule (preferred): earliest chapter-anchor that uses slug.
        used_by = [a for a in chapter_intros if slug in anchor_tdeps[a]]
        if used_by:
            ch = min((anchor_to_chapter[a] for a in used_by),
                     key=lambda c: chapter_rank.get(c, len(chapter_rank)))
            chapter_cache[slug] = ch
            return ch

        # Downstream rule: closest anchor in slug's deps; on tie, latest chapter.
        uses = [a for a in tdeps(slug) if a in anchor_to_chapter]
        if uses:
            dist: dict[str, int] = {slug: 0}
            queue = [slug]
            while queue:
                next_q = []
                for s in queue:
                    for d in (corpus[s].fm.get("depends-on") or []):
                        if d in corpus and d not in dist:
                            dist[d] = dist[s] + 1
                            next_q.append(d)
                queue = next_q
            anchor_dist = {a: dist[a] for a in uses if a in dist}
            min_d = min(anchor_dist.values())
            closest = [a for a, d in anchor_dist.items() if d == min_d]
            ch = max((anchor_to_chapter[a] for a in closest),
                     key=lambda c: chapter_rank.get(c, -1))
            chapter_cache[slug] = ch
            return ch

        # Fallback 1: recurse via deps.
        for d in (n.fm.get("depends-on") or []):
            if d in corpus:
                ch = assign(d, _stack + (slug,))
                if ch is not None:
                    chapter_cache[slug] = ch
                    return ch
        # Fallback 2: recurse via dependents.
        dep_chapters: list[str] = []
        for d in dependents.get(slug, ()):
            ch = assign(d, _stack + (slug,))
            if ch is not None:
                dep_chapters.append(ch)
        if dep_chapters:
            ch = min(dep_chapters, key=lambda c: chapter_rank.get(c, len(chapter_rank)))
            chapter_cache[slug] = ch
            return ch
        chapter_cache[slug] = None
        return None

    skip = set(part_narrative_slugs)
    chapter_content: dict[str | None, list[str]] = {None: []}
    for ch in chapter_order:
        chapter_content[ch] = []
    for s in order:
        if s in skip:
            continue
        if s in chapter_rank:
            continue
        ch = assign(s)
        chapter_content.setdefault(ch, []).append(s)

    return chapter_content, chapter_order, part_num_to_narrative
