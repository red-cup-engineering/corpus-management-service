"""Walk a domain root, collect Reference entries from frontmatter.

The `references:` key in any note's frontmatter is the source of truth for
what that note cites. Each note is self-contained: full citation metadata
lives next to the prose that uses it. The bib is the union of every
note's `references:` blocks, deduped by key.

A `references/` directory at the domain root is **optional**. When it
exists, its `*.md` files are research notes about cited works — anything
in those files' frontmatter that overlaps with citation fields is folded
into the bib for fields the inline declarations didn't carry, but the
directory can be deleted with no loss to the bib for any cited key.

Returns (references, issues). Inline-vs-inline conflicts are warnings,
first-occurrence wins.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import yaml

from .schema import COMMON_FIELDS, Reference, SchemaIssue

FM_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)

# Frontmatter fields that describe the *note* in the research corpus, not the
# *cited work*. Stripped from Reference.fields so they don't trip the schema's
# "unknown field" warning or leak into the rendered BibTeX.
_INTERNAL_FIELDS = frozenset({
    "kind", "status", "anchor",
    "depends-on", "introduces", "recaps", "discusses",
    "instantiates", "see-also", "realizes", "closes",
    "chapters", "explores",
    "references",  # the citing-note manifest, not a citation field
})


def _parse_frontmatter(path: Path) -> tuple[dict, str] | None:
    text = path.read_text()
    m = FM_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return fm, m.group(2)


def _entry_to_reference(entry: dict, *, source_path: str,
                        declared_inline: bool,
                        default_key: str | None = None) -> tuple[Reference | None, list[SchemaIssue]]:
    issues: list[SchemaIssue] = []
    key = entry.get("key") or default_key
    if not key:
        issues.append(SchemaIssue(
            "error", "missing-key", "<unknown>", source_path,
            "reference entry has no `key` field",
        ))
        return None, issues
    ref_type = entry.get("type")
    if not ref_type:
        # Heuristic: presence of `journal` ⇒ article; `booktitle` ⇒ inproceedings;
        # otherwise `misc`. Soft warning so the user sees the inferred type.
        if entry.get("journal"):
            ref_type = "article"
        elif entry.get("booktitle"):
            ref_type = "inproceedings"
        else:
            ref_type = "misc"
        issues.append(SchemaIssue(
            "warning", "inferred-type", key, source_path,
            f"no `type` field; inferred `{ref_type}` from other fields",
        ))
    fields = {k: v for k, v in entry.items()
              if k not in ("key", "type") and k not in _INTERNAL_FIELDS}
    return Reference(
        key=str(key), type=str(ref_type), fields=fields,
        source_path=source_path, declared_inline=declared_inline,
    ), issues


def _collect_extras(root: Path) -> tuple[list[Reference], list[SchemaIssue]]:
    """Read every `<root>/references/*.md` annotation file."""
    refs: list[Reference] = []
    issues: list[SchemaIssue] = []
    refs_dir = root / "references"
    if not refs_dir.is_dir():
        return refs, issues
    for p in sorted(refs_dir.glob("*.md")):
        if p.name == "README.md":
            continue
        parsed = _parse_frontmatter(p)
        if parsed is None:
            issues.append(SchemaIssue(
                "error", "frontmatter-parse", p.stem,
                str(p.relative_to(root)),
                "cannot parse frontmatter",
            ))
            continue
        fm, _ = parsed
        # The kind: reference field is conventional; we don't require it
        # but skip annotations where it's explicitly something else.
        if fm.get("kind") not in (None, "reference"):
            continue
        ref, errs = _entry_to_reference(
            fm,
            source_path=str(p.relative_to(root)),
            declared_inline=False,
            default_key=p.stem,
        )
        issues.extend(errs)
        if ref is not None:
            refs.append(ref)
    return refs, issues


def _collect_inline(root: Path,
                    lib_dirs: tuple[str, ...]) -> tuple[list[Reference], list[SchemaIssue]]:
    """Walk all notes in `lib_dirs` and harvest their frontmatter `references:`."""
    refs: list[Reference] = []
    issues: list[SchemaIssue] = []
    for d in lib_dirs:
        if d == "references":
            continue
        dir_path = root / d
        if not dir_path.is_dir():
            continue
        for p in sorted(dir_path.glob("*.md")):
            if p.name == "README.md":
                continue
            parsed = _parse_frontmatter(p)
            if parsed is None:
                continue
            fm, _ = parsed
            inline = fm.get("references")
            if not inline:
                continue
            if not isinstance(inline, list):
                issues.append(SchemaIssue(
                    "error", "references-not-list", "<inline>",
                    str(p.relative_to(root)),
                    "frontmatter `references:` must be a list of mappings",
                ))
                continue
            for entry in inline:
                if not isinstance(entry, dict):
                    issues.append(SchemaIssue(
                        "error", "references-entry-not-mapping", "<inline>",
                        str(p.relative_to(root)),
                        f"each `references:` entry must be a mapping; got {type(entry).__name__}",
                    ))
                    continue
                ref, errs = _entry_to_reference(
                    entry,
                    source_path=str(p.relative_to(root)),
                    declared_inline=True,
                )
                issues.extend(errs)
                if ref is not None:
                    refs.append(ref)
    return refs, issues


def merge(annotations: list[Reference],
          inlines: list[Reference]) -> tuple[dict[str, Reference], list[SchemaIssue]]:
    """Build the cite-key index from inline `references:` declarations,
    optionally folding in any `references/<key>.md` data for fields the
    inline declarations didn't carry.

    For each cite-key:
      1. Collect every inline declaration for the key. First wins; later
         conflicting declarations are reported as `inline-mismatch` warnings.
      2. If the optional `references/` directory has a file for the key,
         fold its frontmatter fields in for any missing fields only.
         Inline values always win on overlap. A key that appears only in
         `references/` (no inline citation) is included silently — the
         user's research notes might predate any citation of the source.
    """
    issues: list[SchemaIssue] = []
    by_key: dict[str, Reference] = {}

    inline_by_key: dict[str, list[Reference]] = defaultdict(list)
    for r in inlines:
        inline_by_key[r.key].append(r)

    for key, group in inline_by_key.items():
        first = group[0]
        by_key[key] = first
        for r in group[1:]:
            for f in COMMON_FIELDS:
                if f in ("key", "type"):
                    continue
                fv = first.fields.get(f)
                rv = r.fields.get(f)
                if rv is not None and fv is not None and rv != fv:
                    issues.append(SchemaIssue(
                        "warning", "inline-mismatch", key, r.source_path,
                        f"inline `{f}` differs from `{first.source_path}`: "
                        f"{rv!r} vs {fv!r}",
                    ))

    extras: dict[str, list[Reference]] = defaultdict(list)
    for r in annotations:
        extras[r.key].append(r)

    for key, group in extras.items():
        if len(group) > 1:
            paths = ", ".join(g.source_path or "?" for g in group)
            issues.append(SchemaIssue(
                "error", "duplicate-research-note", key, None,
                f"multiple research-note files for `{key}`: {paths}",
            ))
        extra = group[0]
        if key in by_key:
            inline = by_key[key]
            merged_fields = {**extra.fields, **inline.fields}
            by_key[key] = Reference(
                key=key,
                type=inline.type or extra.type,
                fields=merged_fields,
                source_path=inline.source_path,
                declared_inline=True,
            )
        else:
            by_key[key] = extra

    return by_key, issues


def load(root: Path,
         lib_dirs: tuple[str, ...]) -> tuple[dict[str, Reference], list[SchemaIssue]]:
    """Walk `root`, collect references, merge."""
    extras, extra_issues = _collect_extras(root)
    inlines, inl_issues = _collect_inline(root, lib_dirs)
    merged, merge_issues = merge(extras, inlines)

    # Per-reference schema validation runs over the merged set.
    from .schema import validate
    schema_issues: list[SchemaIssue] = []
    for ref in merged.values():
        schema_issues.extend(validate(ref))

    return merged, [*extra_issues, *inl_issues, *merge_issues, *schema_issues]
