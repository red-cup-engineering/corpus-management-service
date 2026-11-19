from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Iterator

from research_corpus import Corpus, Diagnostic

LEAN_DECL_RE = re.compile(
    r"\b(theorem|lemma|example|def|structure|class|abbrev|inductive)\s+{name}\b"
)
NEXT_DECL_RE = re.compile(
    r"\n(theorem|lemma|example|def|structure|class|abbrev|inductive|namespace|end)\b"
)

# Hard-failing codes — the validator's exit code goes nonzero on these.
HARD_CODES = {
    "lean-build-failed",
    "lean-lemma-missing",
    "lean-module-missing",
}


def _collect_refs(corpus: Corpus) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for note in corpus:
        ref = note.fm.get("lean")
        if not ref:
            continue
        refs = ref if isinstance(ref, list) else [ref]
        for r in refs:
            out.append((note.slug, r))
    return out


def _ensure_elan(env: dict[str, str]) -> None:
    elan_bin = Path.home() / ".elan" / "bin"
    if elan_bin.is_dir() and str(elan_bin) not in env.get("PATH", "").split(":"):
        env["PATH"] = f"{elan_bin}:{env.get('PATH', '')}"


def check(corpus: Corpus) -> Iterator[Diagnostic]:
    """For each note carrying `lean:`, run `lake build` and verify the named
    declaration exists, and flag source-level `sorry` only as a frontier observation. This does not certify realization; the Obsmetrologia theorem auditor owns axiom budgets."""
    refs = _collect_refs(corpus)
    if not refs:
        return

    lean_dir = corpus.config.lean_dir_path
    if lean_dir is None or not lean_dir.is_dir():
        for slug, ref in refs:
            yield Diagnostic(
                code="lean-no-dir",
                severity="warning",
                path=corpus.notes[slug].path,
                message=f"lean: {ref} but lean directory not present",
                extra={"slug": slug, "ref": ref},
            )
        return

    env = os.environ.copy()
    _ensure_elan(env)
    try:
        proc = subprocess.run(
            ["lake", "build"], cwd=lean_dir, env=env,
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError:
        for slug, ref in refs:
            yield Diagnostic(
                code="lean-lake-missing",
                severity="warning",
                path=corpus.notes[slug].path,
                message="lake binary not on PATH; cannot validate Lean proofs",
                extra={"slug": slug, "ref": ref},
            )
        return
    except subprocess.TimeoutExpired:
        for slug, ref in refs:
            yield Diagnostic(
                code="lean-lake-timeout",
                severity="warning",
                path=corpus.notes[slug].path,
                message="lake build timed out",
                extra={"slug": slug, "ref": ref},
            )
        return

    build_ok = proc.returncode == 0
    build_out = (proc.stdout + proc.stderr)[-2000:]

    for slug, ref in refs:
        if not build_ok:
            yield Diagnostic(
                code="lean-build-failed",
                severity="error",
                path=corpus.notes[slug].path,
                message=f"lake build failed; tail:\n{build_out}",
                extra={"slug": slug, "ref": ref},
            )
            continue

        parts = ref.split(".")
        if len(parts) < 2:
            yield Diagnostic(
                code="lean-module-missing",
                severity="error",
                path=corpus.notes[slug].path,
                message=f"lean ref `{ref}`: not in Module.lemma form",
                extra={"slug": slug, "ref": ref},
            )
            continue
        lemma = parts[-1]
        lean_file = lean_dir.joinpath(*parts[:-1]).with_suffix(".lean")
        if not lean_file.exists():
            yield Diagnostic(
                code="lean-module-missing",
                severity="error",
                path=corpus.notes[slug].path,
                message=f"lean ref `{ref}`: file {lean_file.name} not found",
                extra={"slug": slug, "ref": ref},
            )
            continue
        content = lean_file.read_text()
        decl_re = re.compile(
            LEAN_DECL_RE.pattern.format(name=re.escape(lemma)),
            re.MULTILINE,
        )
        m = decl_re.search(content)
        if not m:
            yield Diagnostic(
                code="lean-lemma-missing",
                severity="error",
                path=corpus.notes[slug].path,
                message=f"lean ref `{ref}`: lemma `{lemma}` not found in {lean_file.name}",
                extra={"slug": slug, "ref": ref},
            )
            continue
        tail = content[m.start(): m.start() + 2000]
        nxt = NEXT_DECL_RE.search(tail[1:])
        body_seg = tail[: 1 + nxt.start()] if nxt else tail
        if "sorry" in body_seg:
            yield Diagnostic(
                code="lean-source-frontier",
                severity="warning",
                path=corpus.notes[slug].path,
                message=f"lean source for `{ref}` contains `sorry`; this is a frontier observation, not a realization verdict",
                extra={"slug": slug, "ref": ref},
            )
