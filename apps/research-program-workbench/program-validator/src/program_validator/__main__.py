from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path

from research_corpus import Corpus, Diagnostic, find_root, load
from research_corpus.config import load_config

from .rules import (
    bib, citations, coverage, cross_refs, cycles, lean as lean_rule, orphans,
    math_rendering, proofs, status_consistency, stubs, symbols,
)
from .report import render

# Codes that escalate to a non-zero exit. Soft warnings (stubs, orphans,
# wip-theorems, missing-annotation, missing-status, symbol-collision) do not.
HARD_CODES = {
    "frontmatter-parse",
    "frontmatter-kind",
    "corpus-directory",
    "corpus-file",
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
    "tex-rendering",
    "tex-check-unavailable",
}

DEFAULT_RULES = (
    bib, cross_refs, citations, proofs, cycles, status_consistency,
    coverage, stubs, orphans, symbols,
)


def collect(
    corpus: Corpus, *, run_lean: bool, check_math: bool = False,
    math_reader: math_rendering.TexReader = math_rendering.tex_fallbacks,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = list(corpus.parse_errors)
    for rule in DEFAULT_RULES:
        diagnostics.extend(rule.check(corpus))
    if run_lean:
        diagnostics.extend(lean_rule.check(corpus))
    if check_math:
        diagnostics.extend(math_rendering.check(corpus, read=math_reader))
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


def compare_diagnostics(
    current: list[Diagnostic], current_root: Path,
    baseline: list[Diagnostic], baseline_root: Path,
) -> dict[str, list[dict]]:
    """Compare diagnostic occurrences, not checkout paths or moved line numbers."""
    def indexed(rows: list[Diagnostic], root: Path) -> tuple[Counter, dict]:
        counts, examples = Counter(), {}
        for diagnostic in rows:
            row = _diagnostic_to_jsonable(diagnostic)
            if diagnostic.path is not None:
                path = diagnostic.path
                if path.is_absolute() and path.is_relative_to(root):
                    path = path.relative_to(root)
                row["path"] = path.as_posix()
            identity = {key: value for key, value in row.items() if key != "line"}
            fingerprint = json.dumps(identity, sort_keys=True, ensure_ascii=False)
            counts[fingerprint] += 1
            examples[fingerprint] = row
        return counts, examples

    present, current_rows = indexed(current, current_root)
    before, old_rows = indexed(baseline, baseline_root)
    return {
        "added": [current_rows[key] for key in sorted(present - before)
                  for _ in range(present[key] - before[key])],
        "resolved": [old_rows[key] for key in sorted(before - present)
                     for _ in range(before[key] - present[key])],
    }


def compare_scope(current: Corpus, baseline: Corpus, *, run_lean: bool) -> dict:
    """Distinguish diagnostics resolved by a repair from changes in coverage."""
    def validation_inputs(corpus: Corpus) -> dict:
        config = corpus.config
        inputs = {
            "lib_dirs": config.lib_dirs,
            "files": config.files,
            "bib": config.bib,
            "min_body_chars": config.validate.min_body_chars,
        }
        if run_lean:
            inputs["lean_dir"] = config.validate.lean_dir
        return inputs

    active, original = set(current.path_slugs), set(baseline.path_slugs)
    a, b = validation_inputs(current), validation_inputs(baseline)
    return {
        "different_inputs": sorted(key for key in a if a[key] != b[key]),
        "added_note_paths": sorted(active - original),
        "removed_note_paths": sorted(original - active),
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
    ap.add_argument("--check-math", action="store_true",
                    help="verify rendered TeX with local Pandoc MathML output")
    ap.add_argument("--format", choices=("md", "json"), default="md",
                    help="report format written to stdout when --report is omitted")
    ap.add_argument("--report", type=Path, default=None,
                    help="write the markdown report here (default: <root>/tools/build/wip-report.md)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress per-code summary on stderr")
    ap.add_argument("--baseline-root", type=Path, default=None,
                    help="append a diagnostic comparison against another corpus root to JSON")
    args = ap.parse_args(argv)
    if args.baseline_root is not None and (args.format != "json" or args.report is not None):
        ap.error("--baseline-root requires --format json without --report")

    root = args.root.resolve() if args.root else find_root()
    baseline_root = args.baseline_root.resolve() if args.baseline_root is not None else None
    if baseline_root is not None:
        if not root.is_dir() or not baseline_root.is_dir():
            ap.error("both comparison roots must be existing directories")
        if baseline_root == root:
            ap.error("--baseline-root must be a separate corpus checkout")
    config = load_config(root)
    corpus = load(root=root, config=config)

    math_reader = (math_rendering.cached_reader() if args.check_math
                   else math_rendering.tex_fallbacks)
    diagnostics = collect(corpus, run_lean=not args.no_lean, check_math=args.check_math,
                          math_reader=math_reader)

    if args.format == "json":
        payload = {
            "root": str(root),
            "total_notes": len(corpus),
            "diagnostics": [_diagnostic_to_jsonable(d) for d in diagnostics],
        }
        if baseline_root is not None:
            baseline = load(root=baseline_root, config=load_config(baseline_root))
            payload["baseline"] = {
                "root": str(baseline_root),
                "total_notes": len(baseline),
                "scope": compare_scope(corpus, baseline, run_lean=not args.no_lean),
                **compare_diagnostics(
                    diagnostics, root,
                    collect(baseline, run_lean=not args.no_lean, check_math=args.check_math,
                            math_reader=math_reader),
                    baseline_root,
                ),
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
