from __future__ import annotations

import re
from pathlib import Path

import yaml

FM_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


class FrontmatterError(Exception):
    pass


def _parse_note(text: str) -> tuple[dict, str, int]:
    """Split a note and retain the one-based source line of the body."""
    m = FM_RE.match(text)
    if not m:
        raise FrontmatterError("no frontmatter block")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise FrontmatterError(f"YAML error: {e}") from e
    if not isinstance(fm, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    return fm, m.group(2), text.count("\n", 0, m.start(2)) + 1


def parse_note(text: str) -> tuple[dict, str]:
    """Return frontmatter and body; invalid YAML or a missing block refuses."""
    fm, body, _ = _parse_note(text)
    return fm, body


def parse_file(path: Path) -> tuple[dict, str]:
    return parse_note(path.read_text())


def parse_file_with_body_line(path: Path) -> tuple[dict, str, int]:
    return _parse_note(path.read_text())
