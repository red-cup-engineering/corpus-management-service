from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_corpus import Corpus, Diagnostic, find_root, load
from research_corpus.config import load_config

from .rules import (
    bib, citations, coverage, cross_refs, cycles, lean as lean_rule, orphans,
    proofs, status_consistency, stubs, symbols,
)
from .report import render

# Codes that escalate to a non-zero exit. Soft warnings (stubs, orphans,
# wip-theorems, missing-annotation, missing-status, symbol-collision) do not.
HARD_CODES = {
    "frontmatter-parse",
    "slug-collision",
    "bib-error",
    "broken-link",
    "broken-citation",
    "orphan-annotation",
    "orphan-pdf",
    "missing-proof",
    "cycle",
    "status-inconsistency",
    "cite-not-in-manifest",
    "manifest-key-unresolved",
    "lean-build-failed",
    "lean-lemma-missing",
    "lean-module-missing",
}

DEFAULT_RULES = (
    bib, cross_refs, citations, proofs, cycles, status_consistency,
    coverage, stubs, orphans, symbols,
)


def collect(corpus: Corpus, *, run_lean: bool) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = list(corpus.parse_errors)
    for rule in DEFAULT_RULES:
        diagnostics.extend(rule.check(corpus))
    if run_lean:
        diagnostics.extend(lean_rule.check(corpus))
    return diagnostics


def _diagnostic_to_jsonable(d: Diagnostic) -> dict:
    return {
        "code": d.code,
        "severity": d.severity,
        "message": d.message,
        "path": str(d.path) if d.path is not None else None,
        "line": d.line,
        "extra": d.extra,
    }


def _summary(diagnostics: list[Diagnostic]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for d in diagnostics:
        counts[d.code] = counts.get(d.code, 0) + 1
    return sorted(counts.items())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="program-validator")
    ap.add_argument("--root", type=Path, default=None,
                    help="research program root (default: walk up from CWD)")
    ap.add_argument("--no-lean", action="store_true",
                    help="skip Lean proof validation")
    ap.add_argument("--format", choices=("md", "json"), default="md",
                    help="report format written to stdout when --report is omitted")
    ap.add_argument("--report", type=Path, default=None,
                    help="write the markdown report here (default: <root>/tools/build/wip-report.md)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress per-code summary on stderr")
    args = ap.parse_args(argv)

    root = args.root.resolve() if args.root else find_root()
    config = load_config(root)
    corpus = load(root=root, config=config)

    diagnostics = collect(corpus, run_lean=not args.no_lean)

    if args.format == "json":
        payload = {
            "root": str(root),
            "total_notes": len(corpus),
            "diagnostics": [_diagnostic_to_jsonable(d) for d in diagnostics],
        }
        print(json.dumps(payload, indent=2))
    else:
        report_path = args.report or (root / "tools" / "build" / "wip-report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render(corpus, diagnostics))
        if not args.quiet:
            print(f"program-validator: {len(corpus)} notes scanned",
                  file=sys.stderr)
            for code, n in _summary(diagnostics):
                print(f"  {n} {code}", file=sys.stderr)
            try:
                rel = report_path.relative_to(root)
            except ValueError:
                rel = report_path
            print(f"  report: {rel}", file=sys.stderr)

    hard = any(d.code in HARD_CODES for d in diagnostics)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
