"""Pandoc invocation: citeproc expansion of [@key] citations against a bib."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


class PandocError(RuntimeError):
    pass


def ensure_pandoc() -> None:
    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        raise PandocError("pandoc not found on PATH (try: apt install pandoc)")


def run(composed: Path, bib: Path | None, output: Path) -> None:
    """Run pandoc, write final monograph to `output`.

    When `bib` is provided and the file exists, --citeproc + --bibliography
    expand `[@key]` citations and append a References section. When `bib` is
    None or missing, pandoc just normalizes the markdown.
    """
    has_bib = bib is not None and bib.is_file()
    cmd = [
        "pandoc", str(composed),
        # Disable auto-id generation so internal headings ("Proof", "Remark",
        # …) don't auto-slugify into the same identifier as a real anchored
        # note and shadow the explicit `{#slug}` anchor.
        "--from", "markdown-auto_identifiers",
        "--to", "commonmark_x-gfm_auto_identifiers",
        "--wrap=preserve",
        "-o", str(output),
    ]
    if has_bib:
        cmd[-2:-2] = ["--citeproc", "--bibliography", str(bib)]
    subprocess.run(cmd, check=True)
    if has_bib:
        # Pandoc 3.1 emits the bibliography heading at H1 regardless of
        # `reference-section-level`; demote to H3 so it nests inside Supplements.
        text = output.read_text()
        text = text.replace(
            "# References {#bibliography .unnumbered}",
            "### References {#bibliography .unnumbered}",
        )
        output.write_text(text)
