from __future__ import annotations

import bisect
from collections import defaultdict, deque
from typing import Iterable, Mapping

# Frontmatter relations that count as outgoing edges in the math-edge graph.
RELATION_KEYS: tuple[str, ...] = (
    "depends-on", "introduces", "recaps", "discusses",
    "instantiates", "see-also", "realizes", "closes",
    "chapters", "explores",
)


def outgoing(fm: Mapping, keys: Iterable[str] = RELATION_KEYS) -> list[str]:
    """Flatten relation values from a single frontmatter dict into a list of slugs."""
    out: list[str] = []
    for k in keys:
        v = fm.get(k)
        if isinstance(v, list):
            out.extend(s for s in v if isinstance(s, str))
        elif isinstance(v, str):
            out.append(v)
    return out


def transitive_deps(slug: str, notes: Mapping[str, Mapping]) -> set[str]:
    """All slugs reachable from `slug` via `depends-on` edges."""
    seen: set[str] = set()
    stack: list[str] = list((notes[slug].get("fm") or {}).get("depends-on") or [])
    while stack:
        d = stack.pop()
        if d in seen or d not in notes:
            continue
        seen.add(d)
        stack.extend((notes[d].get("fm") or {}).get("depends-on") or [])
    return seen


def _depends_on(notes: Mapping[str, Mapping], slug: str) -> list[str]:
    return list((notes[slug].get("fm") or {}).get("depends-on") or [])


def reverse_depends_on(notes: Mapping[str, Mapping]) -> dict[str, list[str]]:
    """{slug: [dependents]} — who depends on this note."""
    rev: dict[str, list[str]] = defaultdict(list)
    for slug in notes:
        for dep in _depends_on(notes, slug):
            if dep in notes:
                rev[dep].append(slug)
    return dict(rev)


def descendants(slug: str, rev: Mapping[str, Iterable[str]]) -> set[str]:
    """Transitive descendants of slug in the depends-on graph (via `rev`)."""
    seen: set[str] = set()
    queue = deque([slug])
    while queue:
        cur = queue.popleft()
        for nxt in rev.get(cur, ()):
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append(nxt)
    return seen


def ancestors(slug: str, notes: Mapping[str, Mapping]) -> set[str]:
    """Transitive ancestors of slug in the depends-on graph."""
    seen: set[str] = set()
    queue: deque[str] = deque([slug])
    while queue:
        cur = queue.popleft()
        if cur not in notes:
            continue
        for prv in _depends_on(notes, cur):
            if prv in seen or prv not in notes:
                continue
            seen.add(prv)
            queue.append(prv)
    return seen


def descendant_counts(notes: Mapping[str, Mapping],
                      rev: Mapping[str, Iterable[str]] | None = None
                      ) -> dict[str, int]:
    """Transitive-descendant count per slug. High count = load-bearing."""
    if rev is None:
        rev = reverse_depends_on(notes)
    return {slug: len(descendants(slug, rev)) for slug in notes}


def foundation_distance(notes: Mapping[str, Mapping]) -> dict[str, int]:
    """Longest path from an atomic note (empty depends-on) to each note.

    Computed via Kahn's algorithm; cyclic components (if any) are skipped —
    callers should detect cycles separately.
    """
    indeg: dict[str, int] = {slug: 0 for slug in notes}
    for slug in notes:
        for dep in _depends_on(notes, slug):
            if dep in notes:
                indeg[slug] += 1

    queue = deque([s for s, d in indeg.items() if d == 0])
    dist: dict[str, int] = {s: 0 for s in queue}
    rev = reverse_depends_on(notes)
    while queue:
        cur = queue.popleft()
        for nxt in rev.get(cur, ()):
            cand = dist[cur] + 1
            if cand > dist.get(nxt, -1):
                dist[nxt] = cand
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    return dist


def detect_cycles(notes: Mapping[str, Mapping]) -> list[list[str]]:
    """Cycles in the depends-on graph: self-loops + SCCs of size > 1.

    Iterative Tarjan to avoid recursion depth limits on dense graphs.
    """
    cycles: list[list[str]] = []
    for slug in notes:
        if slug in _depends_on(notes, slug):
            cycles.append([slug])

    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strong_connect(v: str) -> None:
        work: list[tuple[str, Iterable[str]]] = [
            (v, iter(_depends_on(notes, v)) if v in notes else iter(())),
        ]
        indices[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        while work:
            cur, succs = work[-1]
            advanced = False
            for w in succs:
                if w not in notes:
                    continue
                if w not in indices:
                    indices[w] = index_counter[0]
                    lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(_depends_on(notes, w))))
                    advanced = True
                    break
                elif w in on_stack:
                    lowlink[cur] = min(lowlink[cur], indices[w])
            if advanced:
                continue
            if lowlink[cur] == indices[cur]:
                comp: list[str] = []
                while True:
                    x = stack.pop()
                    on_stack.discard(x)
                    comp.append(x)
                    if x == cur:
                        break
                if len(comp) > 1:
                    sccs.append(comp)
            work.pop()
            if work:
                parent_cur, _ = work[-1]
                lowlink[parent_cur] = min(lowlink[parent_cur], lowlink[cur])

    for slug in notes:
        if slug not in indices:
            strong_connect(slug)

    cycles.extend(sccs)
    return cycles


def topo_sort(items: Iterable[str], deps: Mapping[str, Iterable[str]]) -> list[str]:
    """As-late-as-possible (just-in-time) topological sort.

    Each item is placed at the latest position consistent with the dep graph —
    immediately before its earliest dependent. A primitive used only by one
    theorem appears right before that theorem, not at the top of the book.
    """
    items = set(items)
    dependents: dict[str, set[str]] = {s: set() for s in items}
    for s in items:
        for d in deps.get(s, []) or []:
            if d in dependents:
                dependents[d].add(s)

    remaining = {s: set(dependents[s]) for s in items}
    queue = sorted(s for s in items if not remaining[s])
    process_order: list[str] = []
    while queue:
        s = queue.pop(0)
        process_order.append(s)
        for d in deps.get(s, []) or []:
            if d in remaining:
                remaining[d].discard(s)
                if not remaining[d]:
                    bisect.insort(queue, d)

    # Cycle handling: append leftovers alphabetically.
    for s in sorted(items):
        if s not in process_order:
            process_order.append(s)

    final: list[str] = []
    pos: dict[str, int] = {}
    for s in process_order:
        min_dep_pos = None
        for u in dependents[s]:
            if u in pos and (min_dep_pos is None or pos[u] < min_dep_pos):
                min_dep_pos = pos[u]
        if min_dep_pos is None:
            final.append(s)
            pos[s] = len(final) - 1
        else:
            final.insert(min_dep_pos, s)
            for k, v in pos.items():
                if v >= min_dep_pos:
                    pos[k] = v + 1
            pos[s] = min_dep_pos

    return final
