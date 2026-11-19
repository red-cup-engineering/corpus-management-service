from __future__ import annotations

from research_corpus.corpus import Corpus

from . import analysis as A


def render(corpus: Corpus,
           crossref: dict[str, dict],
           crossref_aggressive: dict[str, dict],
           descendants: dict[str, int],
           foundation: dict[str, int]) -> str:
    notes = corpus.notes
    lines: list[str] = []
    lines.append("# Dependency-graph audit\n")
    lines.append(f"Notes scanned: **{len(notes)}**.")
    edges = sum(len([d for d in (n.fm.get("depends-on") or []) if d in notes])
                for n in corpus)
    lines.append(f"Dependency edges (resolved): **{edges}**.")
    lines.append("")

    unrelated_pairs = sum(len(v["body_not_in_deps_unrelated"]) for v in crossref.values())
    sibling_pairs = sum(len(v["body_not_in_deps_sibling"]) for v in crossref.values())
    ancestor_pairs = sum(len(v["body_not_in_deps_ancestor"]) for v in crossref.values())
    deps_missing = sum(len(v["deps_not_in_body"]) for v in crossref.values())
    body_missing_aggressive = sum(
        len(v["body_not_in_deps"]) for v in crossref_aggressive.values()
    )

    lines.append("## Cross-ref vs depends-on consistency\n")
    lines.append(
        "Body links classified by their relation to the citing note's `depends-on`:\n"
        "- *direct*: in `depends-on` (good)\n"
        "- *descendant*: M's proof depends on N (forward-pointer, dropped)\n"
        "- *ancestor*: M is a transitive ancestor of N via `depends-on` (dependency implicit)\n"
        "- *sibling*: M is reachable from one of N's direct deps but is neither an ancestor nor descendant (a 'see also' relative)\n"
        "- *unrelated*: none of the above (highest-priority signal)\n"
    )
    n_unrel_notes = sum(1 for v in crossref.values() if v["body_not_in_deps_unrelated"])
    n_sib_notes = sum(1 for v in crossref.values() if v["body_not_in_deps_sibling"])
    n_anc_notes = sum(1 for v in crossref.values() if v["body_not_in_deps_ancestor"])
    n_dep_notes = sum(1 for v in crossref.values() if v["deps_not_in_body"])
    lines.append(
        f"- **Unrelated body references**: **{unrelated_pairs} pairs** "
        f"across {n_unrel_notes} notes. "
        f"Most likely real missing dependencies or stray cross-references."
    )
    lines.append(
        f"- **Sibling body references**: **{sibling_pairs} pairs** "
        f"across {n_sib_notes} notes. "
        f"Mostly 'see also' / specialization cites — usually benign."
    )
    lines.append(
        f"- **Ancestor body references**: **{ancestor_pairs} pairs** "
        f"across {n_anc_notes} notes. "
        f"Lower priority — transitive dependency is present."
    )
    lines.append(
        f"- `depends-on` lists a note but body never cites it: **{deps_missing} pairs** "
        f"across {n_dep_notes} notes.\n"
    )
    dropped = body_missing_aggressive - unrelated_pairs - sibling_pairs - ancestor_pairs
    lines.append(
        f"*Filter context: {body_missing_aggressive} unfiltered → "
        f"{unrelated_pairs} unrelated + {sibling_pairs} sibling + {ancestor_pairs} ancestor "
        f"({dropped} pairs dropped as forward-pointers/informational).*\n"
    )

    unrelated_notes = [(slug, v) for slug, v in crossref.items()
                       if v["body_not_in_deps_unrelated"]]
    if unrelated_notes:
        unrelated_notes.sort(key=lambda x: (-descendants.get(x[0], 0), x[0]))
        lines.append("### Unrelated body references (highest priority)\n")
        lines.append(
            "Body cites a note that's not in `depends-on`, not a descendant, not a "
            "transitive ancestor, and not a sibling. Either the note IS a real "
            "dependency that should be listed, OR it's an arbitrary cross-reference.\n"
        )
        for slug, v in unrelated_notes[:50]:
            n = corpus[slug]
            d = descendants.get(slug, 0)
            refs = ", ".join(f"`{r}`" for r in v["body_not_in_deps_unrelated"][:8])
            more = (f" (+{len(v['body_not_in_deps_unrelated']) - 8} more)"
                    if len(v["body_not_in_deps_unrelated"]) > 8 else "")
            lines.append(
                f"- `{slug}` (descendants={d}, kind={n.kind}, "
                f"status={n.fm.get('status') or '—'}): {refs}{more}"
            )
        if len(unrelated_notes) > 50:
            lines.append(f"\n*(+ {len(unrelated_notes) - 50} more notes with unrelated body refs)*")
        lines.append("")

    lines.append("## Top 20 load-bearing notes (most descendants)\n")
    lines.append(
        "These are the notes with the most transitive dependents — an error "
        "in any of them propagates farthest. Worth re-checking the proofs / "
        "definitions are tight.\n"
    )
    top = sorted(descendants.items(), key=lambda x: -x[1])[:20]
    lines.append("| Rank | Note | Descendants | Kind | Status |")
    lines.append("|---:|---|---:|---|---|")
    for i, (slug, count) in enumerate(top, 1):
        n = corpus[slug]
        st = n.fm.get("status") or "—"
        lines.append(f"| {i} | `{slug}` | {count} | {n.kind} | {st} |")
    lines.append("")

    if foundation:
        max_dist = max(foundation.values())
        avg_dist = sum(foundation.values()) / len(foundation)
        lines.append("## Foundation-distance\n")
        lines.append(
            f"Longest dependency chain from an atomic note (empty `depends-on`) "
            f"to a leaf: **{max_dist}** edges."
        )
        lines.append(
            f"Average distance: **{avg_dist:.1f}** edges across "
            f"{len(foundation)} notes.\n"
        )
        far = sorted(foundation.items(), key=lambda x: -x[1])[:10]
        lines.append("### Top 10 deepest notes (longest distance from atoms)\n")
        lines.append("| Note | Distance |")
        lines.append("|---|---:|")
        for slug, d in far:
            lines.append(f"| `{slug}` | {d} |")
        lines.append("")

    return "\n".join(lines) + "\n"
