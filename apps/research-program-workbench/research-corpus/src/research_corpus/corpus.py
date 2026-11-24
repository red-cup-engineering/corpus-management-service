from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .citations import parse_bib_keys
from .config import ProgramConfig, load_config
from .diagnostics import Diagnostic
from .frontmatter import FrontmatterError, parse_file_with_body_line


@dataclass
class Note:
    slug: str
    dir: str
    kind: str
    fm: dict
    body: str
    path: Path  # path relative to corpus root
    body_start_line: int = 1

    # Legacy dict-style access — the original tools indexed notes as dicts;
    # the validator/composer ports keep that idiom for line-by-line parity.
    def __getitem__(self, key: str):
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


@dataclass
class Corpus:
    root: Path
    config: ProgramConfig
    notes: dict[str, Note] = field(default_factory=dict)
    parse_errors: list[Diagnostic] = field(default_factory=list)
    bib_keys: set[str] = field(default_factory=set)

    def __iter__(self):
        return iter(self.notes.values())

    def __len__(self) -> int:
        return len(self.notes)

    def __contains__(self, slug: str) -> bool:
        return slug in self.notes

    def __getitem__(self, slug: str) -> Note:
        return self.notes[slug]

    def items(self):
        return self.notes.items()

    def values(self):
        return self.notes.values()

    def slugs(self) -> set[str]:
        return set(self.notes.keys())

    @property
    def path_slugs(self) -> dict[str, str]:
        return {note.path.as_posix(): slug for slug, note in self.notes.items()}

    @property
    def bib_path(self) -> Path:
        return self.config.bib_path


def _is_explicit_file(root: Path, relative: Path) -> bool:
    """An exact member must not traverse a linked component below the root."""
    current = root
    try:
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                return False
        return current.is_file()
    except OSError:
        return False


def load(root: Path | None = None, *, config: ProgramConfig | None = None) -> Corpus:
    """Load a corpus from `root`. If `config` is omitted, read research.toml from `root`.

    Reads shallow library directories (skipping README.md) and exact configured
    files without recursion. Paths are parsed once and indexed by slug.
    Parse failures are recorded as Diagnostics rather than raised.
    """
    if config is None:
        if root is None:
            from .config import find_root
            root = find_root()
        config = load_config(root)
    else:
        root = config.root

    notes: dict[str, Note] = {}
    parse_errors: list[Diagnostic] = []

    explicit = {Path(item.path): item.default_kind for item in config.files}
    seen: set[Path] = set()

    def admit(rel: Path, directory: str, default_kind: str) -> None:
        if rel in seen:
            return
        seen.add(rel)
        if rel in explicit:
            if not _is_explicit_file(root, rel):
                parse_errors.append(Diagnostic(
                    code="corpus-file",
                    severity="error",
                    path=rel,
                    message="configured corpus file is missing, linked, or not a regular file",
                ))
                return
            default_kind = explicit[rel]
        try:
            fm, body, body_start_line = parse_file_with_body_line(root / rel)
        except FrontmatterError as e:
            parse_errors.append(Diagnostic(
                code="frontmatter-parse",
                severity="error",
                path=rel,
                message=str(e),
            ))
            return
        # Science notes declare `type`; the recovered toolkit also accepts
        # its original `kind`. Conflicting declarations need source repair.
        declared_type = fm.get("type")
        legacy_kind = fm.get("kind")
        kind = declared_type if declared_type is not None else legacy_kind
        if kind is None:
            kind = default_kind
        if (not isinstance(kind, str) or not kind.strip()
                or (declared_type is not None and legacy_kind is not None
                    and declared_type != legacy_kind)):
            parse_errors.append(Diagnostic(
                code="frontmatter-kind",
                severity="error",
                path=rel,
                message="type and kind must be nonempty strings and agree when both are present",
            ))
            return
        slug = rel.stem
        if slug in notes:
            parse_errors.append(Diagnostic(
                code="slug-collision",
                severity="error",
                path=rel,
                message=f"slug `{slug}` already declared by {notes[slug].path}",
            ))
            return
        notes[slug] = Note(
            slug=slug,
            dir=directory,
            kind=kind,
            fm=fm,
            body=body,
            path=rel,
            body_start_line=body_start_line,
        )

    for d in config.lib_dirs:
        dir_path = root / d
        if not dir_path.resolve().is_relative_to(root.resolve()):
            parse_errors.append(Diagnostic(
                code="corpus-directory",
                severity="error",
                path=Path(d),
                message="configured corpus directory leaves the selected root",
            ))
            continue
        if not dir_path.is_dir():
            continue
        for p in sorted(dir_path.glob("*.md")):
            if p.name != "README.md" and not p.is_symlink():
                rel = p.relative_to(root)
                admit(rel, d, Path(d).name.rstrip("s"))

    for path, default_kind in explicit.items():
        admit(path, path.parent.as_posix(), default_kind)

    bib_keys = parse_bib_keys(config.bib_path)

    return Corpus(
        root=root,
        config=config,
        notes=notes,
        parse_errors=parse_errors,
        bib_keys=bib_keys,
    )
