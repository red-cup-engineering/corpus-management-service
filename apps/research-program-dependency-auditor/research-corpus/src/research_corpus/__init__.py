"""Parse and graph a frontmatter-markdown research library.

Public surface:

    from research_corpus import Corpus, Note, Diagnostic, ProgramConfig
    from research_corpus import load, find_root, RELATION_KEYS
"""
from .config import ProgramConfig, find_root
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
from .links import LINK_RE, find_cross_refs
from .citations import CITE_RE, parse_bib_keys, parse_bib_diagnostics

__all__ = [
    "Corpus",
    "Note",
    "Diagnostic",
    "ProgramConfig",
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
    "find_cross_refs",
    "CITE_RE",
    "parse_bib_keys",
    "parse_bib_diagnostics",
]
