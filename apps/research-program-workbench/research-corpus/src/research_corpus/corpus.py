from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .citations import parse_bib_keys
from .config import ProgramConfig, load_config
from .diagnostics import Diagnostic
from .frontmatter import FrontmatterError, parse_file


@dataclass
class Note:
    slug: str
    dir: str
    kind: str
    fm: dict
    body: str
    path: Path  # path relative to corpus root

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


def load(root: Path | None = None, *, config: ProgramConfig | None = None) -> Corpus:
    """Load a corpus from `root`. If `config` is omitted, read research.toml from `root`.

    Walks each configured lib_dir, parses every `.md` (skipping README.md), and
    indexes notes by slug. Parse failures are recorded as Diagnostics rather
    than raised — the caller decides how to surface them.
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
            if p.name == "README.md" or p.is_symlink():
                continue
            rel = p.relative_to(root)
            try:
                fm, body = parse_file(p)
            except FrontmatterError as e:
                parse_errors.append(Diagnostic(
                    code="frontmatter-parse",
                    severity="error",
                    path=rel,
                    message=str(e),
                ))
                continue
            # Science notes declare `type`; the recovered toolkit also accepts
            # its original `kind`. Conflicting declarations need source repair.
            declared_type = fm.get("type")
            legacy_kind = fm.get("kind")
            kind = declared_type if declared_type is not None else legacy_kind
            if kind is None:
                kind = Path(d).name.rstrip("s")
            if (not isinstance(kind, str) or not kind.strip()
                    or (declared_type is not None and legacy_kind is not None
                        and declared_type != legacy_kind)):
                parse_errors.append(Diagnostic(
                    code="frontmatter-kind",
                    severity="error",
                    path=rel,
                    message="type and kind must be nonempty strings and agree when both are present",
                ))
                continue
            slug = p.stem
            if slug in notes:
                parse_errors.append(Diagnostic(
                    code="slug-collision",
                    severity="error",
                    path=rel,
                    message=f"slug `{slug}` already declared by {notes[slug].path}",
                ))
                continue
            notes[slug] = Note(
                slug=slug,
                dir=d,
                kind=kind,
                fm=fm,
                body=body,
                path=rel,
            )

    bib_keys = parse_bib_keys(config.bib_path)

    return Corpus(
        root=root,
        config=config,
        notes=notes,
        parse_errors=parse_errors,
        bib_keys=bib_keys,
    )
