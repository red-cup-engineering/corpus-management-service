"""Project explicitly selected corpus notes into a deterministic SKOS vocabulary.

The Markdown frontmatter remains authoritative. This module neither infers a
taxonomy from prose nor replaces validation of the whole research corpus.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from urllib.parse import quote, urlsplit

from .config import VocabularyConfig, find_root, load_config
from .corpus import Corpus, Note, load


class VocabularyError(ValueError):
    """A selected source or vocabulary configuration cannot be projected."""


_IRI_LIKE = re.compile(r"^(?:(?:https?|urn)[:/]|[A-Za-z][A-Za-z0-9+.-]*://)", re.I)
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_URN = re.compile(r"urn:[A-Za-z0-9][A-Za-z0-9-]{0,30}[A-Za-z0-9]:[^?#]+", re.I)
_PREFIXES = """@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
"""


def _text(value: object, field: str) -> str:
    if (not isinstance(value, str) or not value.strip()
            or any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise VocabularyError(f"{field} must be a nonempty Unicode string")
    return value


def _iri(value: object, field: str, *, web_only: bool = False) -> str:
    iri = _text(value, field)
    if (any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F
            or c in '<>"{}|^`\\' for c in iri) or _BAD_PERCENT.search(iri)):
        raise VocabularyError(f"{field} contains characters forbidden in an IRI")
    try:
        parsed = urlsplit(iri)
        if parsed.scheme in ("http", "https"):
            if not parsed.hostname:
                raise ValueError("HTTP(S) IRI requires a host")
            _ = parsed.port  # Reject an invalid port instead of preserving it.
        elif not web_only and parsed.scheme == "urn":
            if not _URN.fullmatch(iri.split("?", 1)[0].split("#", 1)[0]):
                raise ValueError("URN requires a namespace identifier and value")
        else:
            raise ValueError("expected HTTP(S)" if web_only else "expected HTTP(S) or URN")
    except ValueError as error:
        raise VocabularyError(f"{field}: {error}") from error
    return iri


def _relative_path(value: str, field: str, suffix: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts
            or "\\" in value or path.as_posix() != value
            or path.suffix != suffix):
        raise VocabularyError(f"{field} must be an exact root-relative {suffix} path")
    return path


def _source_iris(note: Note) -> list[str]:
    """Read URLs without converting descriptive provenance into identifiers."""
    sources: set[str] = set()

    def explicit(value: object, field: str) -> None:
        sources.add(_iri(value, f"{note.path}: {field}"))

    def array(value: object, field: str) -> None:
        if not isinstance(value, list):
            raise VocabularyError(f"{note.path}: {field} must be an array of IRIs")
        for index, item in enumerate(value):
            explicit(item, f"{field}[{index}]")

    def provenance(value: object, field: str) -> None:
        if isinstance(value, str):
            if _IRI_LIKE.match(value.strip()):
                explicit(value, field)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                provenance(item, f"{field}[{index}]")
        elif isinstance(value, dict):
            for key in ("url", "source_url", "source-url"):
                if key in value:
                    explicit(value[key], f"{field}.{key}")
            for key in ("source", "original-source"):
                if key in value:
                    provenance(value[key], f"{field}.{key}")
            if "sources" in value:
                array(value["sources"], f"{field}.sources")

    for key in ("source", "original-source", "provenance"):
        if key in note.fm:
            provenance(note.fm[key], key)
    if "sources" in note.fm:
        array(note.fm["sources"], "sources")
    return sorted(sources)


def _selected_notes(corpus: Corpus, config: VocabularyConfig) -> list[Note]:
    members = list(config.members)
    if not members:
        raise VocabularyError("vocabulary.members must not be empty")
    if len(members) != len(set(members)):
        raise VocabularyError("vocabulary.members contains duplicate paths")
    indexed = {note.path.as_posix(): note for note in corpus}
    selected: list[Note] = []
    for member in sorted(members):
        _relative_path(member, "vocabulary.members", ".md")
        note = indexed.get(member)
        if note is None:
            raise VocabularyError(f"vocabulary member is not an indexed source note: {member}")
        # The existing loader decides what belongs to the corpus. A collision
        # affecting this selection cannot silently pick the first file loaded.
        for error in corpus.parse_errors:
            if (error.path is not None and
                    (error.path.as_posix() == member
                     or (error.code == "slug-collision" and error.path.stem == note.slug))):
                raise VocabularyError(f"{member}: {error.code}: {error.message}")
        selected.append(note)
    return selected


def render(corpus: Corpus) -> bytes:
    """Render selected frontmatter to UTF-8 Turtle, without writing any files."""
    config = corpus.config.vocabulary
    if config is None:
        raise VocabularyError("research.toml has no [vocabulary] configuration")
    scheme = _iri(config.scheme, "vocabulary.scheme")
    namespace = _iri(config.namespace, "vocabulary.namespace")
    if not namespace.endswith(("/", "#", ":")):
        raise VocabularyError("vocabulary.namespace must end with '/', '#' or ':'")
    document_base = _iri(config.document_base_url, "vocabulary.document_base_url", web_only=True)
    if urlsplit(document_base).query or urlsplit(document_base).fragment:
        raise VocabularyError("vocabulary.document_base_url must not contain a query or fragment")

    chunks = ["# Generated by research-vocabulary from selected Markdown frontmatter.\n",
              _PREFIXES, f"\n<{scheme}> a skos:ConceptScheme .\n"]
    for note in _selected_notes(corpus, config):
        label_field = "name" if "name" in note.fm else "title"
        label = _text(note.fm.get(label_field), f"{note.path}: {label_field}")
        definition = _text(note.fm.get("description"), f"{note.path}: description")
        concept = _iri(namespace + quote(note.slug, safe=""), f"{note.path}: concept IRI")
        if concept == scheme:
            raise VocabularyError(f"{note.path}: concept IRI equals the concept scheme IRI")
        document = document_base.rstrip("/") + "/" + quote(note.path.as_posix(), safe="/")
        predicates = [
            "a skos:Concept",
            "skos:prefLabel " + json.dumps(label, ensure_ascii=False),
            "skos:definition " + json.dumps(definition, ensure_ascii=False),
            f"skos:inScheme <{scheme}>",
            f"rdfs:isDefinedBy <{document}>",
        ]
        if "id" in note.fm:
            identifier = _text(note.fm["id"], f"{note.path}: id")
            predicates.append("dct:identifier " + json.dumps(identifier, ensure_ascii=False))
        predicates.extend(f"prov:wasDerivedFrom <{source}>" for source in _source_iris(note))
        chunks.append(f"\n<{concept}>\n    " + " ;\n    ".join(predicates) + " .\n")
    return "".join(chunks).encode("utf-8")


def output_path(corpus: Corpus) -> Path:
    config = corpus.config.vocabulary
    if config is None:
        raise VocabularyError("research.toml has no [vocabulary] configuration")
    relative = _relative_path(config.output, "vocabulary.output", ".ttl")
    root = corpus.root.resolve()
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise VocabularyError("vocabulary.output must stay within the root and not be a symlink")
    return path


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research-vocabulary")
    parser.add_argument("--root", type=Path, help="root containing research.toml")
    parser.add_argument("--check", action="store_true", help="compare expected bytes without writing")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve() if args.root else find_root()
        config = load_config(root)
        corpus = load(config=config)
        expected = render(corpus)
        target = output_path(corpus)
        if args.check:
            if not target.is_file() or target.read_bytes() != expected:
                print(f"research-vocabulary: missing or stale output: {target}", file=sys.stderr)
                return 1
            print(f"research-vocabulary: current: {target}")
        else:
            _write_atomic(target, expected)
            print(f"research-vocabulary: wrote {target} ({len(config.vocabulary.members)} concepts)")
    except (ValueError, OSError) as error:
        print(f"research-vocabulary: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
