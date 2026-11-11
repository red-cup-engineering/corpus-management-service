"""Parse and graph a frontmatter-markdown research library.

Public surface:

    from research_corpus import Corpus, Note, Diagnostic, ProgramConfig
    from research_corpus import load, find_root, RELATION_KEYS
"""
from .config import ProgramConfig, VocabularyConfig, find_root
from .corpus import Corpus, Note, load
from .diagnostics import Diagnostic
from .graph import (
    RELATION_KEYS,
    ancestors,
    descendants,
    descendant_counts,
    detect_cycles,
    foundation_distance,
    reverse_depends_on,
    topo_sort,
    transitive_deps,
)
from .links import LINK_RE, MarkdownLink, find_cross_refs, find_markdown_links, resolve_link_slug
from .citations import CITE_RE, parse_bib_keys, parse_bib_diagnostics

__all__ = [
    "Corpus",
    "Note",
    "Diagnostic",
    "ProgramConfig",
    "VocabularyConfig",
    "load",
    "find_root",
    "RELATION_KEYS",
    "ancestors",
    "descendants",
    "descendant_counts",
    "detect_cycles",
    "foundation_distance",
    "reverse_depends_on",
    "topo_sort",
    "transitive_deps",
    "LINK_RE",
    "MarkdownLink",
    "find_cross_refs",
    "find_markdown_links",
    "resolve_link_slug",
    "CITE_RE",
    "parse_bib_keys",
    "parse_bib_diagnostics",
]
