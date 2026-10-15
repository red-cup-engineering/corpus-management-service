from __future__ import annotations

import re
from typing import Iterator

from research_corpus import Corpus, Diagnostic

PROOF_HEADING_RE = re.compile(r"^##+ Proof", re.MULTILINE)
PROOF_END_RE = re.compile(r"\$\\square\$")

THEOREM_KINDS = ("theorem", "conjecture", "lemma", "proposition", "corollary")


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """Theorems/conjectures/etc. carry a status; proved ones have a Proof
    section and a $\\square$ end-of-proof marker."""
    for note in corpus:
        if note.kind not in THEOREM_KINDS:
            continue
        status = note.fm.get("status")
        if not status:
            yield Diagnostic(
                code="missing-status",
                severity="warning",
                path=note.path,
                message=f"`{note.slug}` ({note.kind}) has no status",
                extra={"slug": note.slug},
            )
            continue
        if status == "proved":
            if not PROOF_HEADING_RE.search(note.body):
                yield Diagnostic(
                    code="missing-proof",
                    severity="error",
                    path=note.path,
                    message="status: proved — no Proof heading",
                    extra={"slug": note.slug, "reason": "no Proof heading"},
                )
            elif not PROOF_END_RE.search(note.body):
                yield Diagnostic(
                    code="missing-proof",
                    severity="error",
                    path=note.path,
                    message="status: proved — no $\\square$ marker",
                    extra={"slug": note.slug, "reason": "no $\\square$ marker"},
                )
        elif status in ("sketch", "draft"):
            yield Diagnostic(
                code="wip-theorem",
                severity="warning",
                path=note.path,
                message=f"`{note.slug}` — {status}",
                extra={"slug": note.slug, "status": status},
            )
        else:
            yield Diagnostic(
                code="missing-status",
                severity="warning",
                path=note.path,
                message=f"`{note.slug}` has unrecognized status `{status}`",
                extra={"slug": note.slug, "status": status},
            )
