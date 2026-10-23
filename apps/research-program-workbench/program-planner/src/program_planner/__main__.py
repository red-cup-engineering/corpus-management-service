from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_corpus import find_root, load
from research_corpus.config import load_config

from research_corpus.frontmatter import FrontmatterError

from .analysis import in_edges_index
from .focus import focus_recorded_question
from .render import render


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="program-planner")
    ap.add_argument("--root", type=Path, default=None,
                    help="research program root (default: walk up from CWD)")
    ap.add_argument("--out", type=Path, default=None,
                    help="report path (default: from research.toml [plan] output)")
    ap.add_argument("--question-file", type=Path, default=None,
                    help="read-only focus on an EXISTING first-class research question; emits JSON to stdout")
    args = ap.parse_args(argv)

    root = args.root.resolve() if args.root else find_root()
    config = load_config(root)
    corpus = load(root=root, config=config)
    if args.question_file is not None:
        if args.out is not None:
            ap.error("--out is for the batch report; focused question readout goes to stdout")
        try:
            focused = focus_recorded_question(corpus, args.question_file)
        except (OSError, UnicodeError, ValueError, FrontmatterError) as error:
            print(f"program-planner: source question refused: {error}", file=sys.stderr)
            return 2
        print(json.dumps(focused, sort_keys=True, ensure_ascii=False,
                         indent=2, default=str))
        return 0

    idx = in_edges_index(corpus)

    out_path = args.out.resolve() if args.out else (root / config.plan.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(corpus, idx))

    print(f"program-planner: {len(corpus)} notes scanned", file=sys.stderr)
    try:
        rel = out_path.relative_to(root)
    except ValueError:
        rel = out_path
    print(f"  report: {rel}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
