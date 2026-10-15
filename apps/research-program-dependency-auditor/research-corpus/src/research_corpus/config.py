from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class PlanConfig:
    output: str = "tools/build/research-program.md"


@dataclass
class AuditConfig:
    output: str = "tools/build/dependency-audit.md"


@dataclass
class ProgramConfig:
    root: Path
    lib_dirs: tuple[str, ...] = DEFAULT_LIB_DIRS
    bib: str = "references.bib"
    validate: ValidateConfig = field(default_factory=ValidateConfig)
    compose: ComposeConfig = field(default_factory=ComposeConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)

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
        ),
        plan=PlanConfig(
            output=plan.get("output", "tools/build/research-program.md"),
        ),
        audit=AuditConfig(
            output=audit.get("output", "tools/build/dependency-audit.md"),
        ),
    )
