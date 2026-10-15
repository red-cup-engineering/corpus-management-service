from __future__ import annotations

import re

# Capture groups: 1 = link text, 2 = target slug, 3 = optional fragment (#anchor).
LINK_RE = re.compile(
    r"\[([^\]]+)\]\((?:\.\./[a-z]+/)?([A-Za-z0-9\-]+)\.md(#[A-Za-z0-9\-]+)?\)"
)

# Compatibility regex with only the slug captured, used by orphan/unresolved scans.
SLUG_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?:\.\./[a-z]+/)?([A-Za-z0-9\-]+)\.md(?:#[A-Za-z0-9\-]+)?\)"
)


def find_cross_refs(body: str) -> list[str]:
    """Return target slugs of every internal cross-reference in `body`."""
    return SLUG_LINK_RE.findall(body)
