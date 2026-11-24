from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

CONFIG_FILENAME = "research.toml"

DEFAULT_LIB_DIRS = (
    "concepts", "objects", "morphisms", "theorems",
    "examples", "narratives", "questions", "references",
)


@dataclass
class ValidateConfig:
    min_body_chars: int = 200
    lean_dir: str | None = "lean"


@dataclass
class ComposeConfig:
    output: str = "tools/build/monograph.md"
    title: str | None = None
    subtitle: str | None = None
    require_resolved_citations: bool = False


@dataclass
class PlanConfig:
    output: str = "tools/build/research-program.md"


@dataclass
class AuditConfig:
    output: str = "tools/build/dependency-audit.md"


@dataclass(frozen=True)
class VocabularyConfig:
    scheme: str
    namespace: str
    document_base_url: str
    output: str
    members: tuple[str, ...]


def _vocabulary_config(value: object) -> VocabularyConfig | None:
    if value is None:
        return None
    fields = {"scheme", "namespace", "document_base_url", "output", "members"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("[vocabulary] requires exactly " + ", ".join(sorted(fields)))
    for key in fields - {"members"}:
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"vocabulary.{key} must be a nonempty string")
    members = value["members"]
    if (not isinstance(members, list) or not members
            or any(not isinstance(item, str) or not item for item in members)):
        raise ValueError("vocabulary.members must be a nonempty array of paths")
    return VocabularyConfig(
        scheme=value["scheme"], namespace=value["namespace"],
        document_base_url=value["document_base_url"], output=value["output"],
        members=tuple(members),
    )


@dataclass(frozen=True)
class CorpusFile:
    path: str
    default_kind: str

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path) if isinstance(self.path, str) else PurePosixPath()
        if (not path.parts or path.is_absolute() or path.as_posix() != self.path
                or any(part.startswith(".") for part in path.parts) or path.suffix != ".md"
                or PureWindowsPath(self.path).drive or path.name == "README.md"
                or "\\" in self.path or any(ord(c) < 32 or ord(c) == 127 for c in self.path)):
            raise ValueError("corpus.files path must be an exact nonhidden root-relative research .md path (not README.md)")
        if (not isinstance(self.default_kind, str) or not self.default_kind
                or self.default_kind != self.default_kind.strip()
                or any(ord(c) < 32 or ord(c) == 127 for c in self.default_kind)):
            raise ValueError("corpus.files default_kind must be a nonempty plain string")


def _corpus_files(value: object) -> tuple[CorpusFile, ...]:
    if not isinstance(value, list):
        raise ValueError("corpus.files must be an array of tables")
    files = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "default_kind"}:
            raise ValueError("each corpus.files entry requires exactly path and default_kind")
        files.append(CorpusFile(path=item["path"], default_kind=item["default_kind"]))
    return tuple(files)


@dataclass
class ProgramConfig:
    root: Path
    lib_dirs: tuple[str, ...] = DEFAULT_LIB_DIRS
    bib: str = "references.bib"
    validate: ValidateConfig = field(default_factory=ValidateConfig)
    compose: ComposeConfig = field(default_factory=ComposeConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    vocabulary: VocabularyConfig | None = None
    files: tuple[CorpusFile, ...] = ()

    def __post_init__(self) -> None:
        by_path: dict[str, CorpusFile] = {}
        for item in self.files:
            if not isinstance(item, CorpusFile):
                raise ValueError("corpus.files requires CorpusFile selections")
            previous = by_path.setdefault(item.path, item)
            if previous.default_kind != item.default_kind:
                raise ValueError(f"conflicting corpus.files defaults for {item.path}")
        self.files = tuple(by_path[path] for path in sorted(by_path))

    @property
    def bib_path(self) -> Path:
        return self.root / self.bib

    @property
    def output_path(self) -> Path:
        return self.root / self.compose.output

    @property
    def lean_dir_path(self) -> Path | None:
        return (self.root / self.validate.lean_dir) if self.validate.lean_dir else None


def find_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default: CWD) looking for research.toml.

    Raises FileNotFoundError if no ancestor contains research.toml.
    """
    p = (start or Path.cwd()).resolve()
    for cand in (p, *p.parents):
        if (cand / CONFIG_FILENAME).is_file():
            return cand
    raise FileNotFoundError(
        f"no {CONFIG_FILENAME} found in {p} or any ancestor"
    )


def load_config(root: Path) -> ProgramConfig:
    """Load research.toml from `root`. Missing file → defaults."""
    cfg_path = root / CONFIG_FILENAME
    data: dict = {}
    if cfg_path.is_file():
        data = tomllib.loads(cfg_path.read_text())

    corpus = data.get("corpus", {}) or {}
    validate = data.get("validate", {}) or {}
    compose = data.get("compose", {}) or {}
    plan = data.get("plan", {}) or {}
    audit = data.get("audit", {}) or {}
    program = data.get("program", {}) or {}
    require_resolved_citations = compose.get("require_resolved_citations", False)
    if not isinstance(require_resolved_citations, bool):
        raise ValueError("compose.require_resolved_citations must be a boolean")

    return ProgramConfig(
        root=root,
        lib_dirs=tuple(corpus.get("lib_dirs", DEFAULT_LIB_DIRS)),
        bib=corpus.get("bib", "references.bib"),
        validate=ValidateConfig(
            min_body_chars=int(validate.get("min_body_chars", 200)),
            lean_dir=validate.get("lean_dir", "lean"),
        ),
        compose=ComposeConfig(
            output=compose.get("output", "tools/build/monograph.md"),
            title=program.get("title") or compose.get("title"),
            subtitle=program.get("subtitle") or compose.get("subtitle"),
            require_resolved_citations=require_resolved_citations,
        ),
        plan=PlanConfig(
            output=plan.get("output", "tools/build/research-program.md"),
        ),
        audit=AuditConfig(
            output=audit.get("output", "tools/build/dependency-audit.md"),
        ),
        vocabulary=_vocabulary_config(data.get("vocabulary")),
        files=_corpus_files(corpus.get("files", [])),
    )
