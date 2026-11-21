"""Receive an authenticated glossary dataset against its pinned Git sources."""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import quote
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rdflib import Dataset
    from rdflib.query import Result
    from rdflib.term import Identifier

LIMIT = 16 * 1024 * 1024
REGULAR = {"100644", "100755"}


def git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0",
               GIT_TERMINAL_PROMPT="0", GIT_GRAFT_FILE="/dev/null")
    return subprocess.check_output(
        ["git", "--no-replace-objects", "--literal-pathspecs", *args],
        cwd=root,
        env=env,
        stderr=subprocess.PIPE,
    )


def exact_path(name):
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or ".." in path.parts
            or path.as_posix() != name or "\\" in name or "\0" in name):
        raise ValueError(f"Unexpected source selection: {name}")
    return name


def entries(root, revision, path, *, recursive=False):
    rows = git(root, "ls-tree", "--full-tree", "-z", *(["-r"] if recursive else []), revision,
               "--", exact_path(path))
    result = {}
    for row in rows.decode("utf-8").split("\0")[:-1]:
        fields, name = row.split("\t", 1)
        mode, _, oid = fields.split(" ")
        result[name] = mode, oid
    return result


def object_id(root, revision, path, modes):
    record = entries(root, revision, path).get(path)
    if record is None or record[0] not in modes:
        raise ValueError(f"{revision}: {path} does not have the required Git object type")
    return record[1]


def content_catalog(root, revision, profile):
    rows = entries(root, revision, profile["contentRoot"], recursive=True)
    prefix = exact_path(profile["glossaryRoot"]) + "/"
    for name, (mode, _) in rows.items():
        if name.startswith(prefix) and name.endswith(".md") and mode not in REGULAR:
            raise ValueError(f"Tracked glossary Markdown is not a regular Git blob: {name}")
    return {name: oid for name, (mode, oid) in rows.items() if mode in REGULAR}

def glossary_catalog(catalog, profile):
    prefix = exact_path(profile["glossaryRoot"]) + "/"
    return {name: oid for name, oid in catalog.items()
            if name.startswith(prefix) and name.endswith(".md")}


@dataclass(frozen=True)
class SnapshotReceiver:
    """Repository-relative receiver choices, supplied by the consuming Science owner."""

    root: Path
    profile: str
    manifest: str
    snapshot: str
    output: str

    def selected(self, name: str) -> Path:
        selected = self.root / exact_path(name)
        # The checkout and the scratch output have distinct custody. Refuse
        # links at any selected path component, even when they stay in root.
        for component in (selected, *selected.parents):
            if component == self.root:
                break
            if component.is_symlink():
                raise ValueError(f"Snapshot path may not pass through a symlink: {name}")
        return selected

    def receiving_commit(self):
        receiving = git(self.root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", receiving):
            raise ValueError("A full receiving Git commit is required")
        return receiving

    def source_context(self, receiving):
        manifest = json.loads(self.selected(self.manifest).read_bytes())
        profile = json.loads(git(self.root, "cat-file", "blob", receiving + ":" + self.profile))
        source = manifest["source"]["commit"]
        if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
            raise ValueError("Glossary source must be an exact lowercase Git commit ID")
        if git(self.root, "cat-file", "-t", source).strip() != b"commit":
            raise ValueError("Glossary source is not a Git commit")
        try:
            git(self.root, "merge-base", "--is-ancestor", source, receiving)
        except subprocess.CalledProcessError as error:
            raise ValueError("Glossary source is not an ancestor of the receiving checkout") from error
        return manifest, profile, source


    def validated_context(self, receiving=None):
        """Admit the same source/profile and tracked inventory for every reader."""
        receiving = self.receiving_commit() if receiving is None else receiving
        manifest, profile, source = self.source_context(receiving)
        artifact = manifest["artifact"]
        expected = manifest["source"]
        conformance = exact_path(profile["datasetConformance"])
        config = json.loads(git(self.root, "cat-file", "blob", receiving + ":" + conformance))
        if manifest.get("formatVersion") != 1 or artifact["path"] != self.snapshot:
            raise ValueError("Unexpected glossary manifest contract")
        if config["dataset"]["file"] != self.output:
            raise ValueError("Dataset conformance does not select the prepared glossary")
        expected_inputs = {
            self.profile, "research.toml", profile["reviewedVocabulary"],
            profile["authoredRelations"], conformance, *config["dataset"]["shapes"],
            *(item["query"] for item in config["dataset"]["ask"]),
        }
        if set(expected["inputs"]) != expected_inputs:
            raise ValueError("The snapshot does not describe all current build inputs")
        content = profile["contentRoot"]
        if object_id(self.root, source, content, {"040000"}) != expected["contentTree"]:
            raise ValueError("Manifest content tree does not match the claimed source commit")
        for path, oid in expected["inputs"].items():
            if object_id(self.root, source, path, REGULAR) != oid:
                raise ValueError(f"Manifest input does not match the claimed source: {path}")
            if object_id(self.root, receiving, path, REGULAR) != oid:
                raise ValueError(f"Glossary snapshot is stale: build input changed: {path}")
        if object_id(self.root, receiving, content, {"040000"}) != expected["contentTree"]:
            prior = content_catalog(self.root, source, profile)
            current = content_catalog(self.root, receiving, profile)
            # Link presence depends on the names of regular content files, not
            # changes to the bytes of files outside the selected Markdown glossary.
            if prior.keys() != current.keys() or glossary_catalog(prior, profile) != glossary_catalog(current, profile):
                raise ValueError("Glossary snapshot is stale: glossary bytes or tracked content paths changed")
        return manifest, profile, source

    def prepare(self):
        manifest, _, _ = self.validated_context()
        artifact = manifest["artifact"]
        with self.selected(self.snapshot).open("rb") as compressed:
            if hashlib.file_digest(compressed, "sha256").hexdigest() != artifact["compressedSha256"]:
                raise ValueError("Compressed glossary SHA-256 differs from its manifest")
        with gzip.open(self.selected(self.snapshot), "rb") as stream:
            data = stream.read(LIMIT + 1)
        if len(data) > LIMIT or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise ValueError("Uncompressed glossary exceeds the limit or differs from its manifest")
        build = self.selected(self.output)
        build.parent.mkdir(parents=True, exist_ok=True)
        with build.open("xb") as output:
            output.write(data)


    def _read_prepared_dataset(self, manifest):
        # Hash and parse one bounded byte buffer. A pathname read after the
        # check would not necessarily read the bytes that passed it.
        with self.selected(self.output).open("rb") as prepared:
            data = prepared.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("Prepared glossary exceeds the dataset size limit")
        if hashlib.sha256(data).hexdigest() != manifest["artifact"]["sha256"]:
            raise ValueError("Prepared glossary SHA-256 differs from its manifest")
        return parse_nquads(data)

    def load_prepared_dataset(self):
        """Load a digest-bound local Dataset after validating the selected Git sources.

        This is byte and Git-input verification against the selected manifest,
        not an attestation of that manifest or of any scientific claim.
        """
        manifest, _, _ = self.validated_context()
        return self._read_prepared_dataset(manifest)

    def open_saved_queries(self):
        """Open the verified local dataset and its saved queries at one receiving cut."""
        receiving = self.receiving_commit()
        manifest, _, _ = self.validated_context(receiving)
        return SavedGlossaryQueries(self.root, receiving, self._read_prepared_dataset(manifest))

    def verify_evidence(self):
        from rdflib import Graph, Literal, RDF, URIRef
        from rdflib.namespace import PROV
        from rdf_vocabulary_conformance import matches_named_graph

        manifest, profile, source = self.validated_context()
        namespace = profile["namespace"]
        dataset = self._read_prepared_dataset(manifest)
        reviewed_path = exact_path(profile["reviewedVocabulary"])
        reviewed = Graph().parse(
            data=git(self.root, "cat-file", "blob", source + ":" + reviewed_path),
            format="turtle",
            publicID="urn:x-glossary:reviewed-source",
        )
        if not matches_named_graph(dataset, URIRef(namespace + "graph:reviewed-vocabulary"), reviewed):
            raise ValueError("RDF reviewed-vocabulary graph differs from the pinned reviewed Turtle")
        graph = dataset.graph(URIRef(namespace + "graph:documents"))
        predicates = {key: URIRef(namespace + "glossary-vocabulary:" + key)
                      for key in ("path", "gitBlob")}
        catalog = glossary_catalog(content_catalog(self.root, source, profile), profile)
        coverage = manifest["coverage"]
        if coverage.get("audience") != "authenticated":
            raise ValueError("The checked-in glossary must be the authenticated projection")
        if type(coverage.get("trackedGlossaryMarkdown")) is not int or coverage["trackedGlossaryMarkdown"] != len(catalog):
            raise ValueError("Tracked glossary count differs from the pinned Git catalog")
        documents = set(graph.subjects(RDF.type, URIRef("https://schema.org/DigitalDocument")))
        if type(coverage.get("projectedDocuments")) is not int or coverage["projectedDocuments"] != len(documents):
            raise ValueError("RDF document count differs from the committed projection manifest")
        quads = sum(1 for _ in dataset.quads((None, None, None, None)))
        if type(manifest["artifact"].get("quads")) is not int or manifest["artifact"]["quads"] != quads:
            raise ValueError("RDF quad count differs from the committed projection manifest")
        base = "https://github.com/" + profile["repository"] + "/blob/"
        seen = set()
        document_paths = {}
        for document in documents:
            paths = set(graph.objects(document, predicates["path"]))
            if len(paths) != 1 or not isinstance(path := next(iter(paths)), Literal):
                raise ValueError("RDF document does not have one literal Git path")
            name = str(path)
            if name not in catalog or name in seen:
                raise ValueError(f"RDF document does not identify one original glossary path: {name}")
            seen.add(name)
            document_paths[document] = name
            # Match the Workbench's per-segment encodeURIComponent spelling.
            encoded = quote(name, safe="/!~*'()")
            if (document != URIRef(base + "main/" + encoded)
                    or set(graph.objects(document, predicates["gitBlob"])) != {Literal(catalog[name])}
                    or set(graph.objects(document, PROV.wasDerivedFrom)) != {URIRef(base + source + "/" + encoded)}):
                raise ValueError(f"RDF document does not match the claimed Git source: {name}")
        missing = catalog.keys() - seen
        if missing:
            example = sorted(missing)[0]
            raise ValueError(f"RDF document graph omits {len(missing)} pinned glossary path(s); first: {example}")
        if not documents:
            raise ValueError("The authenticated glossary must contain documents")
        verify_term_statuses(graph, namespace, document_paths, coverage)
        print(f"Verified {quads} quads, {len(reviewed)} reviewed triples, and all {len(catalog)} pinned glossary documents.")


    def verify_authored(self):
        from rdflib import URIRef

        manifest, profile, source = self.validated_context()
        dataset = self._read_prepared_dataset(manifest)
        namespace = profile["namespace"]
        selected = glossary_catalog(content_catalog(self.root, source, profile), profile)
        authored_profile = exact_path(profile["authoredRelations"])
        base = "https://github.com/" + profile["repository"] + "/blob/main/"
        documents = {URIRef(base + quote(path, safe="/!~*'()")) for path in selected}
        with TemporaryDirectory(prefix="glossary-authored-replay-") as temporary:
            root = Path(temporary)
            # Replicate the producer's data-only input selection, not its parser.
            # In particular unrelated, newer document bodies are not independent
            # inputs to the snapshot from this revision.
            for path in (*selected, "research.toml", authored_profile):
                destination = root / exact_path(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(git(self.root, "cat-file", "blob", source + ":" + path))
            predicates = json.loads((root / authored_profile).read_bytes())["relations"]
            replay = subprocess.check_output(
                [sys.executable, "-B", "-m", "research_corpus.vocabulary", "--root", str(root),
                 "--authored-relations", authored_profile, "--audience", "authenticated"],
                stderr=subprocess.PIPE, timeout=60, cwd=self.root,
            )
            report = json.loads(replay)
        count = verify_owner_assertions(dataset, namespace, documents, predicates, report)
        print(f"Verified {count} reviewed concept assertions and exact authored witnesses from pinned Git.")


    def verify_navigation(self, replay_entry):
        """Require exact equality with the native observation of pinned Markdown."""
        manifest, profile, source = self.validated_context()
        dataset = self._read_prepared_dataset(manifest)
        if manifest["coverage"].get("audience") != "authenticated":
            raise ValueError("Navigation replay requires the authenticated projection")
        # The caller supplies the installed Workbench entrypoint. Untrusted
        # glossary data only supplies the source commit already admitted above.
        command = [
            "node", str(replay_entry.resolve(strict=True)), "--repository", str(self.root),
            "--revision", source, "--profile", self.profile, "--audience", "authenticated",
        ]
        with TemporaryDirectory(prefix="glossary-navigation-replay-") as temporary:
            output = Path(temporary) / "navigation.nq"
            with output.open("xb") as replay:
                subprocess.run(command, stdout=replay, stderr=subprocess.PIPE,
                               check=True, timeout=60, cwd=self.root)
            with output.open("rb") as replay:
                expected = replay.read(LIMIT + 1)
            if len(expected) > LIMIT:
                raise ValueError("Native glossary navigation projection exceeds the dataset size limit")
            count = compare_navigation(dataset, parse_nquads(expected), profile["namespace"])
        print(f"Verified {count} navigation triples from pinned Git.")


@dataclass(frozen=True)
class SavedGlossaryQueries:
    """Read committed local SELECTs over one digest-verified named dataset."""

    root: Path
    revision: str
    dataset: Dataset

    def select(self, path: str, *, bindings: Mapping[str, Identifier] | None = None) -> Result:
        from rdflib import Literal, URIRef
        from rdf_vocabulary_conformance import prepare_local_select
        from rdf_vocabulary_conformance.dataset_checks import MAX_QUERY_BYTES

        query = exact_path(path)
        if not query.endswith(".rq"):
            raise ValueError("A saved SELECT must be selected by its .rq path")
        values = {} if bindings is None else bindings
        if (not isinstance(values, Mapping) or len(values) > 32
                or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                       or not isinstance(value, (URIRef, Literal)) for name, value in values.items())):
            raise ValueError("Saved SELECT bindings need variable names and RDF IRIs or literals")
        blob = object_id(self.root, self.revision, query, REGULAR)
        size = int(git(self.root, "cat-file", "-s", blob))
        if size > MAX_QUERY_BYTES:
            raise ValueError("Saved SELECT exceeds the input byte limit")
        query_bytes = git(self.root, "cat-file", "blob", blob)
        if len(query_bytes) != size:
            raise ValueError("Saved SELECT bytes differ from the pinned Git object length")
        prepared = prepare_local_select(query_bytes)
        return self.dataset.query(prepared, initBindings=dict(values), use_store_provided=False)


def verify_term_statuses(document_graph, namespace, document_paths, coverage):
    """Bind document status rows to the inventory and receipt without replaying Term."""
    from rdflib import Literal, URIRef

    predicate = URIRef(namespace + "glossary-vocabulary:termSchemaStatus")
    if set(document_graph.subjects(predicate)) - document_paths.keys():
        raise ValueError("RDF term status identifies a subject outside the document inventory")
    counts = {"admitted": 0, "not-admitted": 0, "not-a-term-carrier": 0}
    for document, name in document_paths.items():
        statuses = set(document_graph.objects(document, predicate))
        # The native projector classifies the exact basename README.md as an index.
        allowed = ({"not-a-term-carrier"} if name.rsplit("/", 1)[-1] == "README.md"
                   else {"admitted", "not-admitted"})
        if len(statuses) != 1 or not any(Literal(status) in statuses for status in allowed):
            raise ValueError(f"RDF document lacks one valid Term admission status: {name}")
        counts[str(next(iter(statuses)))] += 1
    for field, status in (("termSchemaAdmitted", "admitted"), ("termSchemaNotAdmitted", "not-admitted")):
        if type(coverage.get(field)) is not int or coverage[field] != counts[status]:
            raise ValueError(f"RDF term status count differs from the committed projection manifest: {field}")
    return counts


def parse_nquads(data):
    """Parse the supplied UTF-8 bytes locally as separate named graphs."""
    from rdflib import Dataset

    return Dataset(default_union=False).parse(data=data.decode("utf-8"), format="nquads")


def compare_navigation(actual, expected, namespace):
    """Compare the exact navigation named graph, not aggregate counts or the union."""
    from rdflib import URIRef
    from rdf_vocabulary_conformance import matches_named_graph

    identifier = URIRef(namespace + "graph:navigation")
    if any(g != identifier for _, _, _, g in expected.quads((None, None, None, None))):
        raise ValueError("Native glossary navigation replay must emit only its named graph")
    reference = expected.graph(identifier)
    matches = (matches_named_graph(actual, identifier, reference) if len(reference)
               else len(actual.graph(identifier)) == 0)
    if not matches:
        raise ValueError("RDF navigation differs from the pinned Workbench replay")
    return len(reference)


def verify_owner_assertions(dataset, namespace, documents, predicates, report):
    """Compare only the reviewed concept assertions and their raw witnesses."""
    from rdflib import Literal, RDF, URIRef
    from rdflib.namespace import DCTERMS, RDFS, SKOS

    if (report.get("schema") != "research-vocabulary.authored-relations.v1"
            or report.get("audience") != "authenticated" or report.get("unresolved") != []
            or not isinstance(report.get("assertions"), list)):
        raise ValueError("Workbench did not return a complete authenticated authored projection")
    authored = dataset.graph(URIRef(namespace + "graph:authored-assertions"))
    reviewed = dataset.graph(URIRef(namespace + "graph:reviewed-vocabulary"))
    concepts = set(reviewed.subjects(RDF.type, SKOS.Concept))
    owned_predicates = {URIRef(value) for value in predicates.values()}
    expected_edges = set()
    expected_witnesses = Counter()
    for row in report["assertions"]:
        start, relation, end = (URIRef(row[field]) for field in ("subject", "predicate", "object"))
        source, target_source = URIRef(row["source"]), URIRef(row["targetSource"])
        if (start not in concepts or end not in concepts or source not in documents
                or target_source not in documents
                or (start, RDFS.isDefinedBy, source) not in reviewed
                or (end, RDFS.isDefinedBy, target_source) not in reviewed
                or row["predicate"] != predicates.get(row["field"])):
            raise ValueError("Workbench authored projection is outside the reviewed owner profile")
        expected_edges.add((start, relation, end))
        expected_witnesses[source, Literal(row["field"]), Literal(row["rawValue"]), end] += 1
    if len(expected_edges) != len(report["assertions"]) or any(n != 1 for n in expected_witnesses.values()):
        raise ValueError("Workbench returned duplicate owner assertion evidence")
    actual_edges = {(s, p, o) for s, p, o in authored
                    if s in concepts or (p in owned_predicates and s not in documents)}
    if actual_edges != expected_edges:
        raise ValueError("RDF owner assertions differ from the pinned Workbench replay")

    vocab = namespace + "glossary-vocabulary:"
    witness_type, key, raw, status, target = map(
        URIRef, (vocab + value for value in
                 ("AuthoredRelationObservation", "predicateKey", "rawTarget", "projectionStatus", "target")))
    expected_prefixes = {record[:3] for record in expected_witnesses}
    actual_witnesses = Counter()
    # Term's independent carrier observations target document IRIs. Include
    # unknown non-document targets and exact expected prefixes so a malformed
    # or missing owner target is not silently filtered out.
    subjects = set(authored.subjects(RDF.type, witness_type)) | set(authored.subjects(target))
    for witness in subjects:
        sources, keys, raws, targets = [set(authored.objects(witness, prop))
                                        for prop in (DCTERMS.source, key, raw, target)]
        if (not (targets - documents)
                and not any(s in sources and k in keys and r in raws for s, k, r in expected_prefixes)):
            continue
        if ((witness, RDF.type, witness_type) not in authored
                or any(len(values) != 1 for values in (sources, keys, raws, targets))
                or set(authored.objects(witness, status)) != {Literal("admitted-carrier")}):
            raise ValueError("RDF owner assertion does not have one complete admitted source witness")
        actual_witnesses[tuple(next(iter(values)) for values in (sources, keys, raws, targets))] += 1
    if actual_witnesses != expected_witnesses:
        raise ValueError("RDF owner assertion witnesses differ from the pinned Workbench replay")
    return len(expected_edges)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "evidence", "authored", "navigation"))
    parser.add_argument("--root", default=Path.cwd(), type=Path, help="receiving Git worktree")
    for name in ("profile", "manifest", "snapshot", "output"):
        parser.add_argument("--" + name, required=True, type=exact_path, help="exact repository-relative path")
    parser.add_argument("--navigation-replay", type=Path,
                        help="installed Workbench replay-glossary-navigation.mjs entrypoint")
    args = parser.parse_args(argv)
    if (args.stage == "navigation") != (args.navigation_replay is not None):
        parser.error("--navigation-replay is required for, and only valid with, the navigation stage")
    try:
        receiver = SnapshotReceiver(args.root.resolve(strict=True), args.profile, args.manifest,
                                    args.snapshot, args.output)
        if args.stage == "navigation":
            receiver.verify_navigation(args.navigation_replay)
        else:
            {"prepare": receiver.prepare, "evidence": receiver.verify_evidence,
             "authored": receiver.verify_authored}[args.stage]()
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"Cannot verify pinned glossary source: {error.stderr.decode(errors='replace').strip()}\n")
    except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
