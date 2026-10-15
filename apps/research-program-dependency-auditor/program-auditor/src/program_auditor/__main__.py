from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_corpus import find_root, load, reverse_depends_on
from research_corpus.config import load_config

from .analysis import (
    crossref_vs_depends_on,
    descendant_count_map,
    foundation_distance_map,
)
from .render import render


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="program-auditor")
    ap.add_argument("--root", type=Path, default=None,
                    help="research program root (default: walk up from CWD)")
    ap.add_argument("--out", type=Path, default=None,
                    help="report path (default: from research.toml [audit] output)")
    args = ap.parse_args(argv)

    root = args.root.resolve() if args.root else find_root()
    config = load_config(root)
    corpus = load(root=root, config=config)

    rev = reverse_depends_on(corpus.notes)
    descendants = descendant_count_map(corpus)
    foundation = foundation_distance_map(corpus)
    crossref = crossref_vs_depends_on(
        corpus, rev=rev,
        section_filter=True, drop_descendants=True, drop_siblings=True,
    )
    crossref_aggressive = crossref_vs_depends_on(
        corpus, rev=rev,
        section_filter=False, drop_descendants=False, drop_siblings=False,
    )

    out_path = args.out.resolve() if args.out else (root / config.audit.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(corpus, crossref, crossref_aggressive,
                               descendants, foundation))

    unrelated_pairs = sum(len(v["body_not_in_deps_unrelated"]) for v in crossref.values())
    sibling_pairs = sum(len(v["body_not_in_deps_sibling"]) for v in crossref.values())
    ancestor_pairs = sum(len(v["body_not_in_deps_ancestor"]) for v in crossref.values())
    unrelated_notes = sum(1 for v in crossref.values() if v["body_not_in_deps_unrelated"])
    body_missing_aggressive = sum(len(v["body_not_in_deps"]) for v in crossref_aggressive.values())
    print(f"program-auditor: {len(corpus)} notes scanned", file=sys.stderr)
    print("  body refs not in deps:", file=sys.stderr)
    print(f"    unrelated (highest signal): {unrelated_pairs} pairs across {unrelated_notes} notes",
          file=sys.stderr)
    print(f"    sibling: {sibling_pairs} pairs (mostly 'see also' cites)", file=sys.stderr)
    print(f"    ancestor: {ancestor_pairs} pairs (transitive deps)", file=sys.stderr)
    print(f"    unfiltered total: {body_missing_aggressive} pairs", file=sys.stderr)
    try:
        rel = out_path.relative_to(root)
    except ValueError:
        rel = out_path
    print(f"  report: {rel}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
