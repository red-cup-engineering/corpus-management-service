from __future__ import annotations

import re
import posixpath
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping
from urllib.parse import unquote, urlsplit

# Capture groups: 1 = link text, 2 = target slug, 3 = optional fragment (#anchor).
LINK_RE = re.compile(
    r"\[([^\]]+)\]\((?:\.\./[a-z]+/)?([A-Za-z0-9\-]+)\.md(#[A-Za-z0-9\-]+)?\)"
)

# Compatibility regex with only the slug captured, used by orphan/unresolved scans.
SLUG_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?:\.\./[a-z]+/)?([A-Za-z0-9\-]+)\.md(?:#[A-Za-z0-9\-]+)?\)"
)

# Inline Markdown links with plain or angle-bracket destinations and an optional
# quoted title. Keep the original three-group LINK_RE public contract above for
# external callers; in-tree consumers use the source-path-aware records below.
_INLINE_LINK_RE = re.compile(
    r'(?<![!\\])\[([^\]\n]+)\]\('
    r'(<[^>\n]+>|[^\s()]+)'
    r'(?:[ \t]+(?:"[^"\n]*"|\x27[^\x27\n]*\x27))?[ \t]*\)'
)
_MASK_START_RE = re.compile(
    r"^ {0,3}(?P<fence>`{3,}|~{3,})[^\n]*(?:\n|$)"
    r"|(?P<comment><!--)|(?P<code>`+)", re.MULTILINE,
)


@dataclass(frozen=True)
class MarkdownLink:
    text: str
    target: str
    path: str
    fragment: str
    start: int
    end: int

    @property
    def slug(self) -> str:
        return PurePosixPath(self.path).stem


def _mask(text: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in text)


def prose_links_text(body: str) -> str:
    """Mask code and HTML comments in source order, preserving offsets.

    A comment opener within code is literal; backticks and fences within an
    HTML comment are literal too. Independent substitution passes cannot
    preserve that precedence.
    """
    result = list(body)
    cursor = 0
    while match := _MASK_START_RE.search(body, cursor):
        if fence := match["fence"]:
            closer = re.compile(
                r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence))
                + r",}[ \t]*(?:\n|$)", re.MULTILINE,
            ).search(body, match.end())
            end = closer.end() if closer else len(body)
        elif match["comment"]:
            closing = body.find("-->", match.end())
            end = closing + 3 if closing != -1 else len(body)
        else:
            closer = re.compile(
                r"(?<!`)" + re.escape(match["code"]) + r"(?!`)"
            ).search(body, match.end())
            if closer is None:
                cursor = match.end()
                continue
            end = closer.end()
        result[match.start():end] = _mask(body[match.start():end])
        cursor = end
    return "".join(result)


def find_markdown_links(body: str) -> list[MarkdownLink]:
    """Return relative .md prose links, preserving exact destination and span.

    These are file references, not slug lookups. Network/root-relative URLs and
    fragment-only links are outside this local-file check. Reference-style links
    and HTML anchors are not covered by this inline-link grammar.
    """
    links: list[MarkdownLink] = []
    for match in _INLINE_LINK_RE.finditer(prose_links_text(body)):
        target = match[2]
        if target.startswith("<"):
            target = target[1:-1]
        try:
            url = urlsplit(target)
        except ValueError:
            continue
        if url.scheme or url.netloc or url.path.startswith("/"):
            continue
        path = unquote(url.path)
        if not path.endswith(".md"):
            continue
        links.append(MarkdownLink(
            text=body[match.start(1):match.end(1)], target=target, path=path,
            fragment=url.fragment,
            start=match.start(), end=match.end(),
        ))
    return links


def resolve_link_slug(link: MarkdownLink, source_path: PurePosixPath,
                      path_slugs: Mapping[str, str]) -> str | None:
    """Resolve one source-relative link to an indexed path, without file I/O."""
    path = posixpath.normpath(posixpath.join(str(source_path.parent), link.path))
    return path_slugs.get(path)


def find_cross_refs(body: str, *, source_path: PurePosixPath | None = None,
                    path_slugs: Mapping[str, str] | None = None) -> list[str]:
    """Read relative Markdown links; optionally resolve their exact corpus paths.

    The one-argument legacy API returns candidate slugs. Graph consumers supply
    source_path and path_slugs so a same-named unindexed file is not a graph edge.
    """
    links = find_markdown_links(body)
    if source_path is None or path_slugs is None:
        return [link.slug for link in links]
    return [slug for link in links
            if (slug := resolve_link_slug(link, source_path, path_slugs)) is not None]
