from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from research_corpus import find_root, load
from research_corpus.config import load_config
from research_dagger import order_corpus

from .ordering import assign_chapters
from .pandoc import PandocError, ensure_pandoc, run as run_pandoc
from .render import (
    render_appendix_further_reading,
    render_appendix_questions,
    render_block,
    render_chapter,
    render_part,
    render_preface,
)


def _generate_bib(corpus, build_dir: Path) -> Path | None:
    """Generate a references.bib from the citation corpus into build_dir.

    Returns the bib path on success, None when no references exist or when
    research-citations is unavailable. Errors are surfaced to stderr but
    don't abort the composer — the legacy bib path can take over.
    """
    try:
        from research_citations import load as load_citations
        from research_citations import render as render_bib
    except ImportError:
        return None
    refs, issues = load_citations(corpus.root, tuple(corpus.config.lib_dirs))
    if not refs:
        return None
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        print(f"composer: {len(errors)} citation errors; not regenerating bib",
              file=sys.stderr)
        for i in errors[:5]:
            print(f"  {i.code}: {i.key} ({i.source_path}): {i.message}",
                  file=sys.stderr)
        return None
    bib_path = build_dir / "references.bib"
    bib_path.write_text(render_bib(refs.values()))
    print(f"composer: generated {bib_path} ({len(refs)} references)",
          file=sys.stderr)
    return bib_path


def _yaml_preamble(title: str | None, subtitle: str | None,
                   bib_relpath: str | None) -> list[str]:
    out = ["---"]
    if title:
        out.append(f"title: {title}")
    if subtitle:
        out.append(f"subtitle: {subtitle}")
    if bib_relpath:
        out += [
            f"bibliography: {bib_relpath}",
            "link-citations: true",
            "reference-section-title: References",
            "reference-section-level: 3",
        ]
    out += ["---", ""]
    return out


def build_composed(corpus, order, chapter_content, chapter_order, part_num_to_narrative,
                   *, title: str | None, subtitle: str | None,
                   bib_relpath: str | None) -> str:
    notes = corpus.notes
    all_slugs = corpus.slugs()
    parts = _yaml_preamble(title, subtitle, bib_relpath)

    # Preliminaries: notes with no chapter assignment.
    for s in chapter_content.get(None, []):
        if notes[s].kind == "narrative":
            parts.append(render_preface(notes[s], all_slugs))
        else:
            parts.append(render_block(notes[s], all_slugs))
        parts.append("")

    for part_num in sorted(part_num_to_narrative):
        pn_slug = part_num_to_narrative[part_num]
        parts.append(render_part(notes[pn_slug], all_slugs))
        parts.append("")
        for ch in notes[pn_slug].fm.get("chapters") or []:
            parts.append(render_chapter(notes[ch], all_slugs))
            parts.append("")
            for s in chapter_content.get(ch, []):
                parts.append(render_block(notes[s], all_slugs))
                parts.append("")

    appendix = render_appendix_questions(corpus, all_slugs)
    further = render_appendix_further_reading(corpus, all_slugs)
    if appendix or further:
        parts.append("## Supplements {#supplements}")
        parts.append("")
    if appendix:
        parts.append(appendix)
        parts.append("")
    if further:
        parts.append(further)
        parts.append("")

    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="monograph-composer")
    ap.add_argument("--root", type=Path, default=None,
                    help="research program root (default: walk up from CWD)")
    ap.add_argument("--out", type=Path, default=None,
                    help="output monograph path (default: from research.toml [compose] output)")
    ap.add_argument("--diagnose", action="store_true",
                    help="print the linear order with chapter markers")
    ap.add_argument("--no-pandoc", action="store_true",
                    help="skip pandoc step; only emit composed.md and manifest.txt")
    args = ap.parse_args(argv)

    root = args.root.resolve() if args.root else find_root()
    config = load_config(root)
    corpus = load(root=root, config=config)

    out_path = args.out.resolve() if args.out else config.output_path
    build_dir = root / "tools" / "build"
    composed_path = build_dir / "composed.md"
    manifest_path = build_dir / "manifest.txt"
    build_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not args.no_pandoc:
        try:
            ensure_pandoc()
        except PandocError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    order = order_corpus(corpus)
    chapter_content, chapter_order, part_num_to_narrative = assign_chapters(order, corpus)

    manifest_lines: list[str] = []
    for s in order:
        n = corpus[s]
        marker = " "
        if n.kind == "narrative" and n.fm.get("position") == "chapter":
            marker = "C"
        manifest_lines.append(f"{marker} {n.dir}/{s}\t{n.kind}")
    manifest_path.write_text("\n".join(manifest_lines) + "\n")

    # Generate a fresh references.bib from the citation corpus to a build-dir
    # location, replacing any hand-edited references.bib at the project root.
    # Falls back gracefully when research-citations is unavailable, or when
    # the project has neither annotation files nor inline `references:`.
    generated_bib = _generate_bib(corpus, build_dir)
    bib_target = generated_bib or (config.bib_path if config.bib_path.is_file() else None)
    bib_relpath = (os.path.relpath(bib_target, composed_path.parent)
                   if bib_target is not None else None)
    composed = build_composed(
        corpus, order, chapter_content, chapter_order, part_num_to_narrative,
        title=config.compose.title,
        subtitle=config.compose.subtitle,
        bib_relpath=bib_relpath,
    )
    composed_path.write_text(composed)

    print(f"manifest:    {manifest_path}  ({len(order)} entries)")
    print(f"composed.md: {composed_path}  ({len(composed):,} chars)")

    if args.diagnose:
        print()
        print("ORDER (C = chapter):")
        for line in manifest_lines:
            print("  " + line)

    if args.no_pandoc:
        return 0

    run_pandoc(composed_path, bib_target, out_path)
    print(f"monograph:   {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
