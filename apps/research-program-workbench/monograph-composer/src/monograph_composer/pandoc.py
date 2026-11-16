"""Pandoc invocation: citeproc expansion of [@key] citations against a bib."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


MARKDOWN_READER = "markdown-auto_identifiers"


class PandocError(RuntimeError):
    pass


def ensure_pandoc() -> None:
    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        raise PandocError("pandoc not found on PATH (try: apt install pandoc)")


def _parsed_json(text: str, source: str, target: str):
    try:
        result = subprocess.run(
            ["pandoc", "--sandbox", "--from", source, "--to", target],
            input=text, encoding="utf-8", capture_output=True, timeout=30, check=True,
        )
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise PandocError(f"could not parse citation input as {source}: {exc}") from exc


def _citation_ids(document) -> set[str]:
    remaining = [document]
    keys = set()
    while remaining:
        node = remaining.pop()
        if isinstance(node, dict):
            if node.get("t") == "Cite":
                keys.update(item["citationId"] for item in node["c"][0])
            remaining.extend(node.values())
        elif isinstance(node, list):
            remaining.extend(node)
    # Pandoc uses '*' in nocite to select all records, not as a citekey.
    return keys - {"*"}


def unresolved_citations(composed: str, bibliography: str | None) -> tuple[str, ...]:
    """Use the rendering engine's Markdown and BibLaTeX readers, not key guesses."""
    requested = _citation_ids(_parsed_json(composed, MARKDOWN_READER, "json"))
    if not requested:
        return ()
    available = set()
    if bibliography is not None:
        records = _parsed_json(bibliography, "biblatex", "csljson")
        available = {record["id"] for record in records}
    return tuple(sorted(requested - available))


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
        "--from", MARKDOWN_READER,
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
