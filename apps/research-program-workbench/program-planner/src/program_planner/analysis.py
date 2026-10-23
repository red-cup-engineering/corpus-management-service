"""Graph analyses over a research corpus.

Where the validator asks "is what we have correct?", the planner asks "what
does what we have demand we write next?". Each analysis applies a rule of
demand or enablement to the frontmatter graph.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from research_corpus import RELATION_KEYS, find_cross_refs
from research_corpus.corpus import Corpus

THEOREM_KINDS = ("theorem", "lemma", "proposition", "corollary")
ANCHOR_KINDS = ("definition", "concept", "morphism")


def out_edges(note, body_links: bool = True) -> set[str]:
    edges: set[str] = set()
    for k in RELATION_KEYS:
        v = note.fm.get(k)
        if isinstance(v, list):
            edges.update(v)
        elif isinstance(v, str):
            edges.add(v)
    if body_links:
        edges.update(find_cross_refs(note.body))
    return edges


def in_edges_index(corpus: Corpus) -> dict[str, set[str]]:
    """slug → set of slugs that point to it."""
    idx: dict[str, set[str]] = defaultdict(set)
    for slug, n in corpus.items():
        for tgt in out_edges(n):
            if tgt in corpus:
                idx[tgt].add(slug)
    return idx


def explored_refs(note) -> list[str]:
    """A single referenced slug is one relation, not its characters."""
    raw = note.fm.get("explores")
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, str) and r]
    return []


def open_questions(corpus: Corpus) -> list[str]:
    return [s for s, n in corpus.items()
            if n.kind == "question"
            and n.fm.get("status") in (None, "open", "partial", "partially-addressed")]


def proven_theorems_about(slug: str, corpus: Corpus,
                          idx: dict[str, set[str]]) -> int:
    count = 0
    for s in idx.get(slug, ()):
        n = corpus[s]
        if n.kind in THEOREM_KINDS and n.fm.get("status") == "proved":
            count += 1
    return count


def entity_firmness(slug: str, corpus: Corpus, idx: dict[str, set[str]]) -> str:
    if slug not in corpus:
        return "missing"
    n = corpus[slug]
    if n.kind in THEOREM_KINDS:
        return "firm" if n.fm.get("status") == "proved" else "sketch"
    if n.kind in ANCHOR_KINDS:
        return "firm" if proven_theorems_about(slug, corpus, idx) >= 1 else "loose"
    return "firm"


def question_blockers(q: str, corpus: Corpus, idx: dict[str, set[str]]) -> dict:
    explored = explored_refs(corpus[q])
    out: dict[str, list] = {"firm": [], "sketch": [], "loose": [], "missing": []}
    for ent in explored:
        f = entity_firmness(ent, corpus, idx)
        if f == "sketch":
            out["sketch"].append((ent, corpus[ent].fm.get("status") or "open"))
        elif f == "missing":
            out["missing"].append(ent)
        elif f == "loose":
            out["loose"].append(ent)
        else:
            out["firm"].append(ent)
    return out


def question_readiness(blockers: dict) -> str:
    if blockers["missing"]:
        return "needs-construction"
    if blockers["sketch"] or blockers["loose"]:
        return "blocked"
    if blockers["firm"]:
        return "answerable"
    return "unanchored"


def question_readiness_view(corpus: Corpus, idx: dict[str, set[str]]) -> dict[str, list]:
    tiers: dict[str, list] = {
        "answerable": [], "blocked": [],
        "needs-construction": [], "unanchored": [],
    }
    for q in open_questions(corpus):
        b = question_blockers(q, corpus, idx)
        tiers[question_readiness(b)].append((q, b))
    for tier in tiers.values():
        tier.sort(key=lambda x: x[0])
    return tiers


def question_clusters(corpus: Corpus, idx: dict[str, set[str]]) -> list[dict]:
    open_q = open_questions(corpus)
    q_blockers: dict[str, set[str]] = {}
    for q in open_q:
        b = question_blockers(q, corpus, idx)
        non_firm: set[str] = set()
        non_firm.update(e for e, _ in b["sketch"])
        non_firm.update(b["loose"])
        non_firm.update(b["missing"])
        q_blockers[q] = non_firm

    parent: dict[str, str] = {q: q for q in open_q}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    blocker_to_qs: dict[str, list[str]] = defaultdict(list)
    for q, blockers in q_blockers.items():
        for b in blockers:
            blocker_to_qs[b].append(q)
    for qs in blocker_to_qs.values():
        for i in range(1, len(qs)):
            union(qs[0], qs[i])

    components: dict[str, set[str]] = defaultdict(set)
    for q in open_q:
        components[find(q)].add(q)

    out: list[dict] = []
    for comp in components.values():
        shared: list[tuple[str, set[str]]] = []
        for b, qs in blocker_to_qs.items():
            qs_in = [q for q in qs if q in comp]
            if len(qs_in) >= 2:
                shared.append((b, set(qs_in)))
        shared.sort(key=lambda x: (-len(x[1]), x[0]))
        out.append({"questions": comp, "shared_blockers": shared})
    out.sort(key=lambda c: (-len(c["questions"]), sorted(c["questions"])[0]))
    return out


def enablement_frontier(corpus: Corpus,
                        idx: dict[str, set[str]]) -> list[tuple[str, dict]]:
    demands: dict[str, dict] = {}
    for q in open_questions(corpus):
        for ent in explored_refs(corpus[q]):
            if ent not in corpus:
                continue
            char = proven_theorems_about(ent, corpus, idx)
            d = demands.setdefault(ent, {"questions": [], "characterizing_theorems": char})
            d["questions"].append(q)
    frontier = [(e, d) for e, d in demands.items()
                if d["characterizing_theorems"] < 3]
    frontier.sort(key=lambda x: (-len(x[1]["questions"]),
                                 x[1]["characterizing_theorems"]))
    return frontier


def demand_clusters(corpus: Corpus,
                    idx: dict[str, set[str]]
                    ) -> list[tuple[str, set[str], str, float]]:
    shared: dict[str, set[str]] = defaultdict(set)
    for q in open_questions(corpus):
        for e in explored_refs(corpus[q]):
            shared[e].add(q)
    out = []
    for e, qs in shared.items():
        if len(qs) < 2:
            continue
        firmness = entity_firmness(e, corpus, idx)
        weight = 1.0 if firmness != "firm" else 0.3
        leverage = len(qs) * weight
        out.append((e, qs, firmness, leverage))
    out.sort(key=lambda x: (-x[3], -len(x[1]), x[0]))
    return out


def realizers_index(corpus: Corpus) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = defaultdict(list)
    for s, n in corpus.items():
        if n.kind in ("definition", "morphism"):
            rs = n.fm.get("realizes") or []
        elif n.kind == "example":
            rs = n.fm.get("instantiates") or []
        else:
            continue
        if isinstance(rs, str):
            rs = [rs]
        for r in rs:
            idx[r].append(s)
    return idx


def realization_gaps(corpus: Corpus) -> dict:
    realizers = realizers_index(corpus)
    unrealized = [s for s, n in corpus.items()
                  if n.kind == "concept" and not realizers.get(s)]
    unanchored = [s for s, n in corpus.items()
                  if n.kind in ("definition", "morphism")
                  and not (n.fm.get("realizes") or [])]
    multi = [(s, realizers[s]) for s in realizers
             if len(realizers[s]) >= 2
             and corpus.notes.get(s) is not None
             and corpus[s].kind == "concept"]
    return {
        "unrealized_concepts": sorted(unrealized),
        "unanchored_constructions": sorted(unanchored),
        "multi_realized": sorted(multi, key=lambda x: -len(x[1])),
    }


_SECTION_RE = re.compile(r"^##+ \S", re.MULTILINE)


def split_candidates(corpus: Corpus) -> list[dict]:
    out: list[dict] = []
    for s, n in corpus.items():
        if n.kind != "concept":
            continue
        sections = _SECTION_RE.findall(n.body)
        deps = (n.fm.get("depends-on") or [])
        if len(sections) >= 4 and len(deps) >= 4:
            out.append({"slug": s, "n_sections": len(sections), "n_deps": len(deps)})
    out.sort(key=lambda c: (-c["n_sections"], c["slug"]))
    return out


def unnamed_ancestor_candidates(corpus: Corpus,
                                limit: int = 15
                                ) -> list[tuple[str, str, set[str], float]]:
    open_q = open_questions(corpus)
    explored = {q: set(explored_refs(corpus[q])) for q in open_q}
    out = []
    for i, q1 in enumerate(open_q):
        e1 = explored[q1]
        if not e1:
            continue
        for q2 in open_q[i + 1:]:
            e2 = explored[q2]
            if not e2:
                continue
            jac = len(e1 & e2) / len(e1 | e2)
            if 0.2 <= jac <= 0.5:
                out.append((q1, q2, e1 & e2, jac))
    out.sort(key=lambda x: -x[3])
    return out[:limit]


def loose_concepts(corpus: Corpus,
                   idx: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    primitives, candidates = [], []
    for s, n in corpus.items():
        if n.kind != "concept":
            continue
        if proven_theorems_about(s, corpus, idx) > 0:
            continue
        type_ = n.fm.get("type", "")
        if type_ in ("entity", "predicate-section"):
            primitives.append(s)
        else:
            candidates.append(s)
    return sorted(primitives), sorted(candidates)


def load_bearing_pillars(corpus: Corpus,
                         idx: dict[str, set[str]],
                         min_theorems: int = 5) -> list[tuple[str, int]]:
    out = []
    for s, n in corpus.items():
        if n.kind not in ANCHOR_KINDS:
            continue
        c = proven_theorems_about(s, corpus, idx)
        if c >= min_theorems:
            out.append((s, c))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out


def isolated_morphisms(corpus: Corpus, idx: dict[str, set[str]]) -> list[str]:
    out = []
    for s, n in corpus.items():
        if n.kind != "morphism":
            continue
        if proven_theorems_about(s, corpus, idx) == 0:
            out.append(s)
    return sorted(out)
