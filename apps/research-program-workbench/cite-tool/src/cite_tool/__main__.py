from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_citations import load, render

# We import research-corpus lazily so cite-tool stays usable even in domains
# that don't (yet) have research-corpus installed — the only thing we need
# from it is `find_root` + the lib_dirs config.

DEFAULT_LIB_DIRS = (
    "concepts", "objects", "morphisms", "theorems",
    "examples", "narratives", "questions", "references",
)


def _resolve_root_and_config(root_arg: Path | None):
    """Discover project root + config. Falls back to a static lib_dirs list
    if research-corpus isn't importable in this environment.
    """
    try:
        from research_corpus import find_root
        from research_corpus.config import load_config
        root = root_arg.resolve() if root_arg else find_root()
        config = load_config(root)
        return root, config.lib_dirs, config
    except ImportError:
        if root_arg is None:
            print("error: research-corpus not installed; pass --root explicitly",
                  file=sys.stderr)
            sys.exit(2)
        return root_arg.resolve(), DEFAULT_LIB_DIRS, None


def _summarize(refs, issues, root: Path, *, label: str) -> None:
    print(f"{label}: {len(refs)} references collected from {root}", file=sys.stderr)
    by_severity: dict[str, int] = {}
    for i in issues:
        by_severity[i.severity] = by_severity.get(i.severity, 0) + 1
    if by_severity:
        bits = ", ".join(f"{n} {sev}" for sev, n in sorted(by_severity.items()))
        print(f"  schema issues: {bits}", file=sys.stderr)


def cmd_generate(args) -> int:
    root, lib_dirs, _ = _resolve_root_and_config(args.root)
    refs, issues = load(root, tuple(lib_dirs))
    _summarize(refs, issues, root, label="cite-tool generate")
    errors = [i for i in issues if i.severity == "error"]
    if args.verbose or errors:
        for i in issues:
            if args.verbose or i.severity == "error":
                print(f"  {i.severity}/{i.code} {i.key} ({i.source_path}): {i.message}",
                      file=sys.stderr)
    if errors:
        print("  refusing to replace references.bib with an invalid or partial projection",
              file=sys.stderr)
        return 1

    out_path = args.out.resolve() if args.out else (root / "references.bib")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(refs.values()))
    try:
        rel = out_path.relative_to(root)
    except ValueError:
        rel = out_path
    print(f"  wrote: {rel}", file=sys.stderr)
    return 0


def cmd_check(args) -> int:
    root, lib_dirs, _ = _resolve_root_and_config(args.root)
    refs, issues = load(root, tuple(lib_dirs))
    _summarize(refs, issues, root, label="cite-tool check")
    n_errors = sum(1 for i in issues if i.severity == "error")
    if args.verbose or n_errors:
        for i in issues:
            if not args.verbose and i.severity != "error":
                continue
            print(f"  {i.severity}/{i.code} {i.key} ({i.source_path}): {i.message}",
                  file=sys.stderr)
    return 1 if n_errors else 0


def cmd_list(args) -> int:
    root, lib_dirs, _ = _resolve_root_and_config(args.root)
    refs, _ = load(root, tuple(lib_dirs))
    for key in sorted(refs):
        r = refs[key]
        title = (r.fields.get("title") or "")[:80]
        print(f"{key}\t{r.type}\t{title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cite-tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=None,
                        help="research project root (default: walk up from CWD)")
    common.add_argument("-v", "--verbose", action="store_true")

    p_gen = sub.add_parser("generate", parents=[common],
                           help="write merged references.bib to disk")
    p_gen.add_argument("--out", type=Path, default=None,
                       help="output path (default: <root>/references.bib)")
    p_gen.set_defaults(func=cmd_generate)

    p_check = sub.add_parser("check", parents=[common],
                             help="validate without writing")
    p_check.set_defaults(func=cmd_check)

    p_list = sub.add_parser("list", parents=[common],
                            help="list collected references")
    p_list.set_defaults(func=cmd_list)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
