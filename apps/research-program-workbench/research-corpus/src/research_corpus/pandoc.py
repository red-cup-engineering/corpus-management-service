"""Optional local Pandoc reading shared by Workbench consumers."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


MARKDOWN_READER = "markdown-auto_identifiers"


class PandocError(RuntimeError):
    pass


def read_pandoc(text: str, source: str, target: str, *options: str) -> str:
    """Use the same Markdown dialect and a bounded process without external assets."""
    try:
        result = subprocess.run(
            ["pandoc", "--sandbox", "--from", source, "--to", target, *options],
            input=text, encoding="utf-8", capture_output=True, timeout=30, check=True,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise PandocError(f"could not read {source} with Pandoc: {exc}") from exc
    return result.stdout


def read_pandoc_json(text: str, source: str, target: str):
    try:
        return json.loads(read_pandoc(text, source, target))
    except ValueError as exc:
        raise PandocError(f"could not decode Pandoc {target}: {exc}") from exc


def tex_fallbacks(text: str) -> tuple[str, ...]:
    """Read native MathML fallback records; unrelated Pandoc warnings stay separate."""
    with TemporaryDirectory(prefix="workbench-tex-") as temp:
        log = Path(temp) / "pandoc.json"
        read_pandoc(text, MARKDOWN_READER, "html", "--mathml", f"--log={log}")
        try:
            records = json.loads(log.read_text(encoding="utf-8"))
            if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
                raise ValueError("expected a Pandoc log array")
            return tuple(str(row["contents"]) for row in records
                         if row.get("type") == "CouldNotConvertTeXMath")
        except (KeyError, OSError, ValueError) as exc:
            raise PandocError(f"could not decode native Pandoc math diagnostics: {exc}") from exc
