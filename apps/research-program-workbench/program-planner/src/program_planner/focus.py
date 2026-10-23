"""Source-preserving focus over a *recorded* research question.

This is a read-only bridge from the existing Red Cup question recorder to
research-corpus/program-planner. It neither creates a question nor certifies
a mathematical or empirical result.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from research_corpus import RELATION_KEYS
from research_corpus.corpus import Corpus, Note
from research_corpus.frontmatter import parse_note

from .analysis import in_edges_index, question_blockers, question_readiness

QUESTION_SECTION = re.compile(
    r"(?ms)^## Question[ \t]*\n\n(.*?)(?=^##[ \t]+|\Z)"
)
OPEN_STATUSES = frozenset({"open", "partial", "partially-addressed"})


def _references(frontmatter: dict, key: str) -> list[str]:
    """Preserve exact source spellings: no basename/fuzzy/case-fold joins."""
    raw = frontmatter.get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        raise ValueError(f"{key} must be a string or list of strings")
    if any(not isinstance(x, str) or not x.strip() for x in values):
        raise ValueError(f"{key} contains an empty or non-string reference")
    return list(values)


def focus_recorded_question(corpus: Corpus, question_file: Path) -> dict:
    """Read an existing question; join ONLY exact present corpus references.

    This is a conditional research PROGRAM readout: a source-grounded inquiry
    with a dependency frontier, not a research result or fulfilled HITS.
    """
    source = question_file.expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix != ".md":
        raise ValueError("question source must be an existing Markdown file")
    raw = source.read_bytes()
    frontmatter, body = parse_note(raw.decode("utf-8"))
    if frontmatter.get("type") != "question":
        raise ValueError("source is not a first-class type: question")
    match = QUESTION_SECTION.search(body)
    if match is None or not match.group(1).strip():
        raise ValueError("recorded question has no nonempty ## Question section")
    title = frontmatter.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("recorded question has no title")

    slug = source.stem
    prior = corpus.notes.get(slug)
    if prior is not None and (corpus.root / prior.path).resolve() != source:
        raise ValueError(
            f"slug collision: {slug} has a different original corpus source"
        )

    relations = {
        key: _references(frontmatter, key)
        for key in RELATION_KEYS
    }
    # In-memory read-only join. No new research note, graph edge, or theorem.
    focused = Note(slug=slug, dir="questions", kind="question",
                   fm=frontmatter, body=body, path=source)
    joined = Corpus(root=corpus.root, config=corpus.config,
                    notes={**corpus.notes, slug: focused},
                    parse_errors=list(corpus.parse_errors),
                    bib_keys=set(corpus.bib_keys))
    idx = in_edges_index(joined)
    blockers = question_blockers(slug, joined, idx)
    structural_readiness = question_readiness(blockers)

    examined: dict[str, dict] = {}
    unresolved: dict[str, list[str]] = {}
    for key, references in relations.items():
        for ref in references:
            if ref == slug:
                unresolved.setdefault(key, []).append(ref)
            elif ref in corpus:
                n = corpus[ref]
                examined.setdefault(ref, {
                    "path": str(n.path),
                    "kind": n.kind,
                    "declared_status": n.fm.get("status"),
                })
            else:
                unresolved.setdefault(key, []).append(ref)

    claimed_sources = {}
    for key in ("source-message", "originating-request", "source", "source-issue"):
        if key in frontmatter:
            claimed_sources[key] = frontmatter[key]

    return {
        "kind": "program-planner.recorded-question-focus/v1",
        "source": {
            "path": str(source),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "title": title,
            "status": frontmatter.get("status"),
            "active": frontmatter.get("status") in OPEN_STATUSES,
            # The complete body is carried, not summarized into a theory.
            "body": body,
            "question": match.group(1).strip(),
            "claimed_origin": claimed_sources,
            "origin_witness_verified": False,
        },
        "research_program": {
            "declared_relations": {k: v for k, v in relations.items() if v},
            "exact_matched_prior_resources": examined,
            "unresolved_exact_references": unresolved,
            "structural_readiness": structural_readiness,
            "readiness_is_only_a_frontmatter_graph_readout": True,
            "corpus_parse_errors": len(corpus.parse_errors),
        },
        "receiving": {
            "mathematical_proof": "not-assessed",
            "engineering_implementation": "not-assessed",
            "operating_effect": "not-assessed",
            "independent_scientific_receiving": "not-assessed",
            "whole_structure_received": "not-assessed",
        },
    }
