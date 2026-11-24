"""Topo sort of primary content; narratives placed by positioning relations."""
from __future__ import annotations

from research_corpus import relation_targets, topo_sort
from research_corpus.corpus import Corpus


def order_corpus(corpus: Corpus) -> list[str]:
    """Topo-sort primary content; place narratives by positioning relations.

    Questions and reference notes are pulled out of the spine — they go to
    appendices, not the topo order.
    """
    primary: list[str] = []
    narratives: list[str] = []
    for slug, n in corpus.items():
        if n.kind == "narrative":
            narratives.append(slug)
        elif n.kind in ("question", "reference"):
            continue
        else:
            primary.append(slug)

    deps = {s: relation_targets(corpus[s].fm, "depends-on") for s in corpus.notes}
    order = topo_sort(primary, deps)

    for narr in sorted(narratives):
        fm = corpus[narr].fm
        for role, key in (("introduces", "introduces"),
                          ("recaps", "recaps"),
                          ("discusses", "discusses")):
            targets = relation_targets(fm, key)
            in_order = [t for t in targets if t in order]
            if not in_order:
                continue
            if role == "introduces":
                idx = min(order.index(t) for t in in_order)
            else:
                idx = max(order.index(t) for t in in_order) + 1
            order.insert(idx, narr)
            break
        else:
            order.append(narr)

    return order
