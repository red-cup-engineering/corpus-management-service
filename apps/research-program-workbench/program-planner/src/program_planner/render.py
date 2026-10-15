from __future__ import annotations

from research_corpus.corpus import Corpus

from . import analysis as A


def render(corpus: Corpus, idx: dict[str, set[str]]) -> str:
    readiness = A.question_readiness_view(corpus, idx)
    qclusters = A.question_clusters(corpus, idx)
    frontier = A.enablement_frontier(corpus, idx)
    clusters = A.demand_clusters(corpus, idx)
    realization = A.realization_gaps(corpus)
    splits = A.split_candidates(corpus)
    ancestors = A.unnamed_ancestor_candidates(corpus)
    primitives, loose = A.loose_concepts(corpus, idx)
    isolated = A.isolated_morphisms(corpus, idx)
    pillars = A.load_bearing_pillars(corpus, idx)

    out: list[str] = []
    out.append("# Research-program report")
    out.append("")
    out.append(
        f"Generated from the frontmatter graph of {len(corpus)} notes. "
        "Each section is a flag for the mathematician to consider — not a "
        "directive. The graph proposes; the mathematician disposes."
    )
    out.append("")

    out.append("## Question readiness")
    out.append("")
    out.append(
        "Each open question, classified by the maturity of its `explores:` "
        "entities. *Answerable* = every explored entity is a proved theorem "
        "or a definition / concept / morphism with at least one characterizing "
        "theorem. *Blocked* = some explored entity is at sketch / draft "
        "status, or is a definition / concept / morphism with no characterizing "
        "theorems yet. *Needs construction* = some explored entity has no "
        "note in the corpus."
    )
    out.append("")
    counts = {tier: len(qs) for tier, qs in readiness.items()}
    out.append(
        f"**Tally:** {counts['answerable']} answerable · "
        f"{counts['blocked']} blocked · "
        f"{counts['needs-construction']} need new construction"
        + (f" · {counts['unanchored']} unanchored" if counts['unanchored'] else "")
        + "."
    )
    out.append("")

    if readiness["answerable"]:
        out.append("### Answerable now")
        out.append("")
        for q, _ in readiness["answerable"]:
            out.append(f"- `{q}`")
        out.append("")
    if readiness["blocked"]:
        out.append("### Blocked on sketches / loose entities")
        out.append("")
        for q, b in readiness["blocked"]:
            blockers = []
            for ent, status in b["sketch"]:
                blockers.append(f"`{ent}` ({status})")
            for ent in b["loose"]:
                blockers.append(f"`{ent}` (loose)")
            out.append(f"- **`{q}`** — blocked on: {', '.join(blockers)}")
        out.append("")
    if readiness["needs-construction"]:
        out.append("### Need new construction")
        out.append("")
        for q, b in readiness["needs-construction"]:
            missing = ", ".join(f"`{e}`" for e in b["missing"])
            other = []
            for ent, status in b["sketch"]:
                other.append(f"`{ent}` ({status})")
            for ent in b["loose"]:
                other.append(f"`{ent}` (loose)")
            line = f"- **`{q}`** — missing: {missing}"
            if other:
                line += f" · also blocked on: {', '.join(other)}"
            out.append(line)
        out.append("")
    if readiness["unanchored"]:
        out.append("### Unanchored (no `explores:`)")
        out.append("")
        for q, _ in readiness["unanchored"]:
            out.append(f"- `{q}`")
        out.append("")

    out.append("## Question clusters")
    out.append("")
    out.append(
        "Connected components of the open-question graph where two "
        "questions are linked iff they share a not-firm explored entity. "
        "Multi-question components are roadmap *spines* — clusters of "
        "questions gated by the same upstream work. Singletons are "
        "independent questions in the parallel *fan*."
    )
    out.append("")
    multi = [c for c in qclusters if len(c["questions"]) >= 2]
    singletons = [c for c in qclusters if len(c["questions"]) == 1]
    if multi:
        for i, c in enumerate(multi, start=1):
            qs = sorted(c["questions"])
            out.append(f"### Spine {i} ({len(qs)} questions)")
            out.append("")
            for q in qs:
                out.append(f"- `{q}`")
            out.append("")
            if c["shared_blockers"]:
                out.append("Shared not-firm blockers (resolving these unblocks the spine):")
                out.append("")
                for b, blocking_qs in c["shared_blockers"][:8]:
                    firmness = A.entity_firmness(b, corpus, idx)
                    out.append(f"- `{b}` ({firmness}, blocks {len(blocking_qs)} of {len(qs)})")
                out.append("")
    if singletons:
        out.append(f"### Independent ({len(singletons)} questions)")
        out.append("")
        out.append(
            "Open questions sharing no not-firm blockers with any other "
            "open question — answerable or advanceable in parallel."
        )
        out.append("")
        for c in singletons:
            (q,) = c["questions"]
            out.append(f"- `{q}`")
        out.append("")

    out.append("## Enablement frontier")
    out.append("")
    out.append(
        "Entities explored by open questions but loosely characterized "
        "(fewer than 3 proven theorems pointing at them). Writing theorems "
        "on these would unblock the listed questions. Sorted by unblock-count."
    )
    out.append("")
    for ent, d in frontier[:20]:
        kind = corpus[ent].kind
        n_thm = d["characterizing_theorems"]
        plural = "s" if n_thm != 1 else ""
        out.append(f"### `{ent}` ({kind}, {n_thm} characterizing theorem{plural})")
        out.append("")
        for q in sorted(d["questions"]):
            out.append(f"- explored by `{q}`")
        out.append("")

    out.append("## Demand clusters (bottleneck entities)")
    out.append("")
    out.append(
        "Entities shared across multiple open questions, leverage-weighted. "
        "Leverage = (questions exploring it) × firmness-weight: 1.0 if the "
        "entity is itself not firm (sketch theorem / loose definition / "
        "missing slug), 0.3 if firm. A not-firm bottleneck shared by many "
        "questions is the highest leverage move on the board."
    )
    out.append("")
    for ent, qs, firmness, leverage in clusters[:15]:
        kind = corpus[ent].kind if ent in corpus else "—"
        out.append(
            f"- **`{ent}`** ({kind}, {firmness}, leverage {leverage:.1f}) — "
            f"explored by {len(qs)} questions: {', '.join(sorted(qs))}"
        )
    out.append("")

    out.append("## Realization graph")
    out.append("")
    out.append(
        "The `realizes:` relation is the convention's bridge between concepts "
        "(roles) and objects/morphisms (realizations of those roles). A concept "
        "without realizers is a role nobody has constructed; a construction "
        "without a `realizes:` declaration is unanchored conceptually."
    )
    out.append("")
    out.append(
        f"**Concepts without realizers ({len(realization['unrealized_concepts'])}):** "
        "roles described but no declared realization in the corpus. Either "
        "implicit demand for an object/morphism that realizes them, or the "
        "concept is currently aspirational."
    )
    out.append("")
    if realization["unrealized_concepts"]:
        out.append(", ".join(f"`{s}`" for s in realization["unrealized_concepts"]))
    out.append("")
    out.append(
        f"**Constructions without `realizes:` ({len(realization['unanchored_constructions'])}):** "
        "objects/morphisms not declaring which concept they realize. Either "
        "they don't realize a named concept (legitimate — not every construction "
        "needs to), or they realize one but the link is undeclared (implicit "
        "demand to declare it)."
    )
    out.append("")
    if realization["multi_realized"]:
        out.append(
            "**Concepts with multiple realizations** "
            "(robust concepts earning their cross-construction keep):"
        )
        out.append("")
        for c, rs in realization["multi_realized"][:10]:
            out.append(f"- `{c}` realized by: {', '.join(f'`{r}`' for r in rs)}")
        out.append("")

    out.append("## Concept-splitting candidates")
    out.append("")
    out.append(
        "Concepts whose body has 4+ distinct named sections AND a "
        "depends-on chain of 4+ entries — both signals together suggest "
        "the body is doing structurally-distinct work that may want "
        "splitting into finer concepts."
    )
    out.append("")
    if splits:
        for c in splits:
            out.append(f"- `{c['slug']}` — {c['n_sections']} sections, {c['n_deps']} deps")
    else:
        out.append("*(no candidates surfaced this run)*")
    out.append("")

    out.append("## Possible unnamed common ancestors")
    out.append("")
    out.append(
        "Pairs of open questions whose `explores:` sets overlap moderately "
        "(Jaccard 0.2–0.5). The intersection may be a missing entity that "
        "would unify the questions and reframe both."
    )
    out.append("")
    if ancestors:
        for q1, q2, common, jac in ancestors:
            shared = ", ".join(f"`{c}`" for c in sorted(common))
            out.append(f"- `{q1}` ↔ `{q2}` (Jaccard {jac:.2f}). Shared: {shared}")
    else:
        out.append("*(no candidates surfaced this run)*")
    out.append("")

    out.append("## Concepts without characterizing theorems")
    out.append("")
    out.append(
        f"Primitives (notional anchors, expected to be loose): "
        f"{', '.join(f'`{p}`' for p in primitives) if primitives else '*(none)*'}."
    )
    out.append("")
    if loose:
        out.append(
            "Non-primitive concepts with no proven theorem about them — "
            "implicit demand for characterization or candidates for splitting:"
        )
        out.append("")
        for c in loose:
            out.append(f"- `{c}`")
        out.append("")
    else:
        out.append("Every non-primitive concept has at least one characterizing theorem.")
        out.append("")

    out.append("## Load-bearing pillars")
    out.append("")
    out.append(
        "Definitions, concepts, and morphisms depended on by 5+ proven "
        "theorems — the structural center of gravity. Changes here ripple "
        "through the corpus."
    )
    out.append("")
    for s, c in pillars[:15]:
        out.append(f"- `{s}` ({corpus[s].kind}) — {c} theorems")
    out.append("")

    out.append("## Morphisms without characterizing theorems")
    out.append("")
    out.append(
        f"{len(isolated)} morphisms have no proven theorem about them. "
        "A morphism without theorems is a definition without consequences — "
        "either the consequences are baked into theorems about its source/"
        "target instead, or the morphism is awaiting characterization."
    )
    out.append("")
    for m in isolated:
        out.append(f"- `{m}`")
    out.append("")

    return "\n".join(out)
