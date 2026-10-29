"""Source-preserving focus over a *recorded* research question.

This is a read-only bridge from the existing Red Cup question recorder to
research-corpus/program-planner. It neither creates a question nor certifies
a mathematical or empirical result.
"""
from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path

from research_corpus import RELATION_KEYS
from research_corpus.corpus import Corpus, Note
from research_corpus.frontmatter import parse_note

from .analysis import (
    in_edges_index, question_blockers, question_clusters, question_readiness,
)

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


def _read_question(question_file: Path):
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
    return source, raw, frontmatter, body, match.group(1).strip()


def focus_recorded_question(
    corpus: Corpus, question_file: Path,
    previous_question_file: Path | None = None,
) -> dict:
    """Join exact research links without rewriting claims or inferring novelty.

    Optional explicit predecessor comparisons retain actual literal changes,
    not an assistant-selected predecessor or a semantic novelty score.
    """
    source, raw, frontmatter, body, question = _read_question(question_file)
    title = frontmatter["title"]

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

    result = {
        "kind": "program-planner.recorded-question-focus/v1",
        "source": {
            "path": str(source),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "title": title,
            "status": frontmatter.get("status"),
            "active": frontmatter.get("status") in OPEN_STATUSES,
            # The complete body is carried, not summarized into a theory.
            "body": body,
            "question": question,
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
    if previous_question_file is not None:
        previous, original, _, _, previous_question = _read_question(
            previous_question_file
        )
        # Align complete source tokens so a repeated letter cannot fragment
        # the actual newly introduced claim ("energy-backed", for example).
        # Every displayed span is still an exact slice of an original source.
        before_tokens = list(re.finditer(r"\S+", previous_question))
        after_tokens = list(re.finditer(r"\S+", question))
        matcher = difflib.SequenceMatcher(
            None,
            [m.group() for m in before_tokens],
            [m.group() for m in after_tokens],
            autojunk=False,
        )
        additions: list[str] = []
        removals: list[str] = []
        for operation, i1, i2, j1, j2 in matcher.get_opcodes():
            if operation in ("replace", "insert") and j2 > j1:
                additions.append(
                    question[after_tokens[j1].start():after_tokens[j2 - 1].end()]
                )
            if operation in ("replace", "delete") and i2 > i1:
                removals.append(
                    previous_question[
                        before_tokens[i1].start():before_tokens[i2 - 1].end()
                    ]
                )
        result["source_comparison"] = {
            "prior_path": str(previous),
            "prior_sha256": hashlib.sha256(original).hexdigest(),
            "prior_question": previous_question,
            "literal_added_spans": additions,
            "literal_removed_spans": removals,
            "predecessor_selected_by_caller": True,
            "semantic_novelty_assessed": False,
        }
    return result


def focus_recorded_program(corpus: Corpus, question_files: list[Path]) -> dict:
    """Read a bounded original-source question family as one research program.

    Reuse the original planner's question-cluster analysis on only explicitly
    selected first-class questions and the original configured research
    concepts/theorems. Neither lexical search nor authored prose adds edges.
    """
    if not (2 <= len(question_files) <= 32):
        raise ValueError("a program requires 2–32 explicitly selected questions")

    selected: dict[str, Note] = {}
    addresses: set[Path] = set()
    for given in question_files:
        source, _, fm, body, _ = _read_question(given)
        if source in addresses:
            raise ValueError(f"duplicate source question: {source}")
        addresses.add(source)
        slug = source.stem
        if slug in selected:
            raise ValueError(f"slug collision among source questions: {slug}")
        prior = corpus.notes.get(slug)
        if prior is not None and (corpus.root / prior.path).resolve() != source:
            raise ValueError(f"slug collision with existing corpus source: {slug}")
        # Retain exact recorded source; do not make new file or graph authority.
        selected[slug] = Note(
            slug=slug, dir="questions", kind="question",
            fm=fm, body=body, path=source,
        )

    # Non-selected old questions are not silently admitted as part of this
    # particular new program. All other pre-existing research stays available
    # as explicitly configured prior resources.
    qualified = {
        slug: note for slug, note in corpus.items()
        if note.kind != "question"
    }
    qualified.update(selected)
    joined = Corpus(
        root=corpus.root, config=corpus.config, notes=qualified,
        parse_errors=list(corpus.parse_errors),
        bib_keys=set(corpus.bib_keys),
    )
    idx = in_edges_index(joined)
    reports = {
        slug: focus_recorded_question(joined, note.path)
        for slug, note in sorted(selected.items())
    }
    clusters = question_clusters(joined, idx)
    represented = []
    for group in clusters:
        qids = sorted(group["questions"])
        represented.append({
            "question_slugs": qids,
            "shared_not_firm_dependencies": [
                {"original_reference": dep, "questions": sorted(qs)}
                for dep, qs in group["shared_blockers"]
            ],
        })

    return {
        "kind": "program-planner.recorded-question-program/v1",
        "input_selection": "explicit-original-files-only",
        "source_question_count": len(selected),
        "source_questions": reports,
        "dependency_components": represented,
        "program_readout": {
            "original_corpus_root": str(corpus.root.resolve()),
            "configured_prior_nonquestion_resources": len(qualified) - len(selected),
            "unresolved_source_links_remain_unresolved": True,
            "graph_readiness_is_not_scientific_acceptance": True,
            "corpus_parse_errors": len(corpus.parse_errors),
        },
        "receiving": {
            "scientific_proof": "not-assessed",
            "engineering_consumer_installation": "not-assessed",
            "operational_work": "not-assessed",
            "independent_beneficiary_acceptance": "not-assessed",
            "holistic_structure_received": "not-assessed",
        },
    }
