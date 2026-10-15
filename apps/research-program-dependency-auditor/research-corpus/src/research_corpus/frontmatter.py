from __future__ import annotations

import re
from pathlib import Path

import yaml

FM_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


class FrontmatterError(Exception):
    pass


def parse_note(text: str) -> tuple[dict, str]:
    """Split a note into (frontmatter dict, body).

    Raises FrontmatterError if no frontmatter block is found or YAML is invalid.
    """
    m = FM_RE.match(text)
    if not m:
        raise FrontmatterError("no frontmatter block")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise FrontmatterError(f"YAML error: {e}") from e
    if not isinstance(fm, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    return fm, m.group(2)


def parse_file(path: Path) -> tuple[dict, str]:
    return parse_note(path.read_text())
