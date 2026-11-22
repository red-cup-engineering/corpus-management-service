"""Exercise native Git provenance and exact document evidence in isolated repositories."""
import builtins
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_corpus.glossary_snapshot import (
    LIMIT, SnapshotReceiver, compare_navigation, parse_nquads, verify_owner_assertions,
)
MANIFEST = "data/records/fixture-glossary.manifest.json"
SNAPSHOT = "data/records/fixture-glossary.nq.gz"
PROFILE = "data/schema/fixture-glossary-build.json"
CONFIG = "data/schema/fixture-glossary-dataset-conformance.json"
OUTPUT = "build/fixture-glossary.nq"
GLOSSARY = "content/text/glossary"
DOCUMENT = GLOSSARY + "/evidence (draft).md"
DOCUMENT_IRI_PATH = GLOSSARY + "/evidence%20(draft).md"
SECOND_DOCUMENT = GLOSSARY + "/other.md"
INDEX_DOCUMENT = GLOSSARY + "/README.md"
BASE = "https://github.com/fixture/corpus/blob/"
V = "urn:fixture:vocab:glossary-vocabulary:"
REVIEWED_GRAPH = "<urn:fixture:vocab:graph:reviewed-vocabulary>"
NAVIGATION_GRAPH = "<urn:fixture:vocab:graph:navigation>"


class SnapshotGitEvidence(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.write(DOCUMENT, "Original glossary bytes\n")
        self.write(SECOND_DOCUMENT, "Second glossary entry\n")
        self.write(INDEX_DOCUMENT, "Glossary index\n")
        self.write("content/other.md", "Other content\n")
        self.write("research.toml", 'program = "test"\n')
        self.write("data/schema/reviewed.ttl",
                   '<urn:fixture:concept> <urn:fixture:definition> "Original definition" ; '
                   '<urn:fixture:source> [ <urn:fixture:note> "Reviewed source" ] .\n')
        self.write("data/schema/authored.json", "{}\n")
        self.write("data/schema/shape.ttl", "")
        self.write("data/schema/query.rq", "ASK { ?s ?p ?o }\n")
        self.write(PROFILE, json.dumps({
            "namespace": "urn:fixture:vocab:", "repository": "fixture/corpus",
            "contentRoot": "content", "glossaryRoot": GLOSSARY,
            "reviewedVocabulary": "data/schema/reviewed.ttl",
            "authoredRelations": "data/schema/authored.json", "datasetConformance": CONFIG,
        }))
        self.write(CONFIG, json.dumps({"dataset": {
            "file": "build/fixture-glossary.nq",
            "shapes": ["data/schema/shape.ttl"], "ask": [{"query": "data/schema/query.rq"}],
        }}))
        self.commit("Original source")
        self.source = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        names = ("research.toml", PROFILE, CONFIG, "data/schema/reviewed.ttl",
                 "data/schema/authored.json", "data/schema/shape.ttl", "data/schema/query.rq")
        self.record = {
            "formatVersion": 1,
            "artifact": {"path": SNAPSHOT},
            "coverage": {"audience": "authenticated", "trackedGlossaryMarkdown": 3, "projectedDocuments": 3,
                         "termSchemaAdmitted": 1, "termSchemaNotAdmitted": 1},
            "source": {"commit": self.source, "contentTree": self.git("rev-parse", "HEAD:content"),
                       "inputs": {name: self.git("rev-parse", "HEAD:" + name) for name in names}},
        }
        self.dataset(self.source)
        self.commit("Received graph")

    def write(self, path, content):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content, encoding="utf-8")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, env=self.env, text=True).strip()

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-qm", message)

    def dataset(self, provenance, *, definition="Original definition", definition_graph=REVIEWED_GRAPH,
                omit_second=False, extra_quad=False, statuses=None, extra_status_subject=None):
        graph = "<urn:fixture:vocab:graph:documents>"
        paths = [(DOCUMENT, DOCUMENT_IRI_PATH), (INDEX_DOCUMENT, INDEX_DOCUMENT)]
        selected_statuses = {DOCUMENT: ('"admitted"',), SECOND_DOCUMENT: ('"not-admitted"',),
                             INDEX_DOCUMENT: ('"not-a-term-carrier"',)}
        selected_statuses.update(statuses or {})
        if not omit_second:
            paths.append((SECOND_DOCUMENT, SECOND_DOCUMENT))
        self.record["coverage"]["projectedDocuments"] = len(paths)
        rows = []
        for path, encoded in paths:
            doc = "<" + BASE + "main/" + encoded + ">"
            blob = self.git("rev-parse", self.source + ":" + path)
            rows.extend(f"{doc} {p} {o} {graph} ." for p, o in (
                ("<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>", "<https://schema.org/DigitalDocument>"),
                ("<" + V + "path>", json.dumps(path)), ("<" + V + "gitBlob>", json.dumps(blob)),
                ("<http://www.w3.org/ns/prov#wasDerivedFrom>", "<" + BASE + provenance + "/" + encoded + ">"),
            ))
            rows.extend(f"{doc} <{V}termSchemaStatus> {value} {graph} ."
                        for value in selected_statuses[path])
        if extra_status_subject is not None:
            rows.append(f'{extra_status_subject} <{V}termSchemaStatus> "admitted" {graph} .')
        data = ("\n".join(rows) + "\n").encode()
        # Intentionally use a different blank-node label from the original Turtle source.
        data += (
            f'<urn:fixture:concept> <urn:fixture:definition> {json.dumps(definition)} {definition_graph} .\n'
            f'<urn:fixture:concept> <urn:fixture:source> _:other {REVIEWED_GRAPH} .\n'
            f'_:other <urn:fixture:note> "Reviewed source" {REVIEWED_GRAPH} .\n'
        ).encode()
        if extra_quad:
            data += f'<urn:fixture:concept> <urn:fixture:definition> {json.dumps(definition)} {NAVIGATION_GRAPH} .\n'.encode()
        self.record["artifact"]["quads"] = len(data.splitlines())
        compressed = gzip.compress(data, mtime=0)
        self.record["artifact"]["sha256"] = hashlib.sha256(data).hexdigest()
        self.record["artifact"]["compressedSha256"] = hashlib.sha256(compressed).hexdigest()
        self.write(SNAPSHOT, compressed)
        self.write(MANIFEST, json.dumps(self.record))

    def verify(self, stage, *, failure=None):
        result = subprocess.run([sys.executable, "-m", "research_corpus.glossary_snapshot", stage,
                                 "--root", str(self.root), "--profile", PROFILE, "--manifest", MANIFEST,
                                 "--snapshot", SNAPSHOT, "--output", OUTPUT], cwd=self.root, env=self.env,
                                capture_output=True, text=True, check=False)
        if failure is None:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(failure, result.stderr)

    def test_prepare_reads_only_one_archive_and_writes_exact_plain_bytes(self):
        archive = self.root / SNAPSHOT
        plain = gzip.decompress(archive.read_bytes())
        opens = []
        original_path_open = Path.open
        original_builtin_open = builtins.open

        def record_path_open(path, *args, **kwargs):
            if path == archive:
                opens.append(path)
            return original_path_open(path, *args, **kwargs)

        def record_builtin_open(path, *args, **kwargs):
            if path == archive:
                opens.append(path)
            return original_builtin_open(path, *args, **kwargs)

        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        with patch.object(Path, "open", record_path_open), patch("builtins.open", record_builtin_open):
            receiver.prepare()
        self.assertEqual(opens, [archive])
        self.assertEqual((self.root / OUTPUT).read_bytes(), plain)

    def test_prepare_refuses_each_wrong_digest_before_creating_output(self):
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        expected = self.record["artifact"].copy()
        for key, failure in (
            ("compressedSha256", "Compressed glossary SHA-256 differs"),
            ("sha256", "Uncompressed glossary exceeds the limit or differs"),
        ):
            with self.subTest(digest=key):
                self.record["artifact"] = dict(expected, **{key: hashlib.sha256(b"wrong").hexdigest()})
                self.write(MANIFEST, json.dumps(self.record))
                with self.assertRaisesRegex(ValueError, failure):
                    receiver.prepare()
                self.assertFalse((self.root / OUTPUT).exists())

    def test_prepare_applies_size_limit_to_both_representations(self):
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        archive = (self.root / SNAPSHOT).read_bytes()
        plain = gzip.decompress(archive)
        self.assertLess(len(archive), len(plain))
        for limit, failure in (
            (len(archive) - 1, "Compressed glossary exceeds the snapshot size limit"),
            (len(plain) - 1, "Uncompressed glossary exceeds the limit"),
        ):
            with self.subTest(limit=limit), patch("research_corpus.glossary_snapshot.LIMIT", limit):
                with self.assertRaisesRegex(ValueError, failure):
                    receiver.prepare()
                self.assertFalse((self.root / OUTPUT).exists())
        with patch("research_corpus.glossary_snapshot.LIMIT", len(plain)):
            receiver.prepare()
        self.assertEqual((self.root / OUTPUT).read_bytes(), plain)

    def test_prepare_allows_exact_compressed_size_limit(self):
        plain = b'<urn:fixture:subject> <urn:fixture:property> "value" .\n'
        archive = gzip.compress(plain, mtime=0)
        self.assertGreater(len(archive), len(plain))
        self.write(SNAPSHOT, archive)
        self.record["artifact"].update(sha256=hashlib.sha256(plain).hexdigest(),
                                       compressedSha256=hashlib.sha256(archive).hexdigest())
        self.write(MANIFEST, json.dumps(self.record))
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        with patch("research_corpus.glossary_snapshot.LIMIT", len(archive)):
            receiver.prepare()
        self.assertEqual((self.root / OUTPUT).read_bytes(), plain)

    def test_prepare_does_not_replace_an_existing_output(self):
        self.write(OUTPUT, b"Preserve this existing output\n")
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        with self.assertRaises(FileExistsError):
            receiver.prepare()
        self.assertEqual((self.root / OUTPUT).read_bytes(), b"Preserve this existing output\n")

    def test_non_glossary_body_edit_does_not_stale_the_path_inventory(self):
        self.write("content/other.md", "Revised body at the same path\n")
        self.commit("Revise other content")
        self.verify("prepare")
        self.verify("evidence")

    def test_direct_reader_receives_the_prepared_named_graph(self):
        self.verify("prepare")
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        dataset = receiver.load_prepared_dataset()
        rows = list(dataset.query(
            "SELECT ?definition WHERE { GRAPH <urn:fixture:vocab:graph:reviewed-vocabulary> "
            "{ <urn:fixture:concept> <urn:fixture:definition> ?definition } }",
            use_store_provided=False,
        ))
        self.assertEqual([str(row[0]) for row in rows], ["Original definition"])

    def test_saved_select_uses_one_receiving_cut_and_typed_bindings(self):
        from rdflib import URIRef

        query = "data/schema/reviewed-select.rq"
        text = ("SELECT ?definition WHERE { GRAPH <urn:fixture:vocab:graph:reviewed-vocabulary> "
                "{ ?concept <urn:fixture:definition> ?definition } } ORDER BY ?definition\n")
        self.write(query, text)
        self.commit("Add the saved SELECT")
        self.verify("prepare")
        from unittest.mock import patch

        with patch.dict(os.environ, {"GIT_DIR": str(self.root / "unrelated.git")}):
            reader = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT).open_saved_queries()
        self.write(query, text.replace("urn:fixture:definition", "urn:fixture:other"))
        self.commit("Change the saved SELECT in a later cut")
        result = reader.select(query, bindings={"concept": URIRef("urn:fixture:concept")})
        self.assertEqual([str(row[0]) for row in result], ["Original definition"])
        with self.assertRaisesRegex(ValueError, "RDF IRIs or literals"):
            reader.select(query, bindings={"concept": "urn:fixture:concept"})

    def test_saved_select_must_select_a_regular_query_blob(self):
        query = "data/schema/linked-select.rq"
        (self.root / query).symlink_to("query.rq")
        self.commit("Track a nonregular query")
        self.verify("prepare")
        reader = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT).open_saved_queries()
        with self.assertRaisesRegex(ValueError, "required Git object type"):
            reader.select(query)
        with self.assertRaisesRegex(ValueError, "selected by its .rq path"):
            reader.select("data/schema/reviewed.ttl")

    def test_readers_refuse_different_prepared_bytes_before_replay(self):
        self.verify("prepare")
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        prepared = self.root / OUTPUT
        # A harmless trailing blank line preserves parsed RDF meaning; the
        # receiver still owes exact byte identity to the prepared snapshot.
        prepared.write_bytes(prepared.read_bytes() + b"\n")
        failure = "Prepared glossary SHA-256 differs from its manifest"
        missing_replay = self.root / "not-installed.mjs"
        for verify in (receiver.load_prepared_dataset, receiver.verify_evidence,
                       receiver.verify_authored, lambda: receiver.verify_navigation(missing_replay)):
            with self.assertRaisesRegex(ValueError, failure):
                verify()

    def test_reader_refuses_an_oversized_prepared_dataset(self):
        self.verify("prepare")
        with (self.root / OUTPUT).open("r+b") as prepared:
            prepared.truncate(LIMIT + 1)
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        with self.assertRaisesRegex(ValueError, "exceeds the dataset size limit"):
            receiver.load_prepared_dataset()

    def test_dirty_worktree_profile_is_not_a_source_selector(self):
        self.write(PROFILE, "not even JSON")
        self.verify("prepare")
        self.verify("evidence")

    def test_output_does_not_follow_a_worktree_symlink(self):
        (self.root / "build").symlink_to(self.root / "data", target_is_directory=True)
        self.verify("prepare", failure="may not pass through a symlink")

    def test_added_path_stales_navigation_inventory(self):
        self.write("content/new.md", "A new exact link target\n")
        self.commit("Add target")
        self.verify("prepare", failure="added regular content paths (1): 'content/new.md'")

    def test_glossary_content_edit_is_stale(self):
        self.write(DOCUMENT, "Changed glossary content\n")
        self.commit("Change glossary")
        self.verify("prepare", failure=f"changed glossary blobs (1): {DOCUMENT!r}")

    def test_stale_catalog_reports_each_observed_change_without_guessing_rename(self):
        self.write(DOCUMENT, "Changed glossary content\n")
        (self.root / "content/other.md").rename(self.root / "content/replacement.md")
        self.commit("Change glossary and content path")
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        with self.assertRaises(ValueError) as refusal:
            receiver.prepare()
        self.assertEqual(str(refusal.exception).splitlines(), [
            "Glossary snapshot is stale: glossary bytes or tracked content paths changed",
            f"changed glossary blobs (1): {DOCUMENT!r}",
            "added regular content paths (1): 'content/replacement.md'",
            "removed regular content paths (1): 'content/other.md'",
        ])
        self.assertFalse((self.root / OUTPUT).exists())

    def test_stale_catalog_lists_a_sorted_sample_and_exact_omitted_count(self):
        for index in reversed(range(10)):
            self.write(f"content/target-{index}.md", "A new exact link target\n")
        self.commit("Add content paths")
        receiver = SnapshotReceiver(self.root, PROFILE, MANIFEST, SNAPSHOT, OUTPUT)
        with self.assertRaises(ValueError) as refusal:
            receiver.prepare()
        sample = ", ".join(repr(f"content/target-{index}.md") for index in range(8))
        self.assertEqual(str(refusal.exception).splitlines()[1:], [
            f"added regular content paths (10): {sample} (+2 more)",
        ])

    def test_glossary_symlink_is_not_admitted(self):
        (self.root / (GLOSSARY + "/link.md")).symlink_to("evidence (draft).md")
        self.commit("Add a nonregular glossary file")
        self.verify("prepare", failure="not a regular Git blob")

    def test_unrelated_commit_is_rejected_even_with_same_tree(self):
        self.record["source"]["commit"] = self.git("commit-tree", self.tree, "-m", "Unrelated root")
        self.write(MANIFEST, json.dumps(self.record))
        self.verify("prepare", failure="not an ancestor")

    def test_document_must_name_the_exact_source_even_with_matching_checksums(self):
        self.dataset("0" * 40)
        self.verify("prepare")
        self.verify("evidence", failure="RDF document does not match the claimed Git source")

    def test_a_rehashed_snapshot_cannot_change_a_reviewed_definition(self):
        self.dataset(self.source, definition="Unreviewed replacement")
        self.verify("prepare")
        self.verify("evidence", failure="reviewed-vocabulary graph differs")

    def test_individually_bound_subset_is_not_a_complete_authenticated_graph(self):
        self.dataset(self.source, omit_second=True)
        self.verify("prepare")
        self.verify("evidence", failure=f"omits 1 pinned glossary path(s); first: {SECOND_DOCUMENT}")

    def test_rehashed_same_size_false_status_disagrees_with_receipt(self):
        self.dataset(self.source, statuses={DOCUMENT: ('"not-admitted"',)})
        self.verify("prepare")
        self.verify("evidence", failure="differs from the committed projection manifest: termSchemaAdmitted")

    def test_rehashed_second_status_cannot_amplify_saved_query_rows(self):
        self.dataset(self.source, statuses={DOCUMENT: ('"admitted"', '"not-admitted"')})
        self.verify("prepare")
        self.verify("evidence", failure="lacks one valid Term admission status")

    def test_rehashed_wrong_kind_missing_status_or_non_plain_value(self):
        for path, value in ((INDEX_DOCUMENT, ('"admitted"',)), (DOCUMENT, ()),
                            (DOCUMENT, ('"admitted"@en',)), (DOCUMENT, ('<urn:fixture:admitted>',))):
            with self.subTest(path=path, value=value):
                self.dataset(self.source, statuses={path: value})
                self.verify("prepare")
                self.verify("evidence", failure="lacks one valid Term admission status")
                (self.root / OUTPUT).unlink()

    def test_rogue_status_subject_is_not_a_document(self):
        self.dataset(self.source, extra_status_subject="<urn:fixture:rogue>")
        self.verify("prepare")
        self.verify("evidence", failure="outside the document inventory")

    def test_dataset_counts_quads_not_union_triples(self):
        # A triple asserted in two named graphs counts as two quads.
        self.dataset(self.source, extra_quad=True)
        self.verify("prepare")
        self.verify("evidence")
        self.record["artifact"]["quads"] -= 1
        self.write(MANIFEST, json.dumps(self.record))
        self.verify("evidence", failure="RDF quad count differs")

    def test_public_projection_is_not_the_checked_in_authenticated_dataset(self):
        self.record["coverage"]["audience"] = "public"
        self.write(MANIFEST, json.dumps(self.record))
        self.verify("prepare")
        self.verify("evidence", failure="must be the authenticated projection")

    def test_claimed_tracked_coverage_is_independent_of_projected_count(self):
        self.record["coverage"]["trackedGlossaryMarkdown"] = 1
        self.write(MANIFEST, json.dumps(self.record))
        self.verify("prepare")
        self.verify("evidence", failure="Tracked glossary count differs")

    def test_matching_union_does_not_allow_reviewed_statements_in_navigation(self):
        self.dataset(self.source, definition_graph=NAVIGATION_GRAPH)
        self.verify("prepare")
        self.verify("evidence", failure="reviewed-vocabulary graph differs")


class AlternateProfileReceiving(unittest.TestCase):
    def test_installed_receiver_replays_profile_with_no_relativity_coordinates(self):
        from rdflib import Graph, URIRef

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            def put(path, data):
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data if isinstance(data, bytes) else data.encode())

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

            def python(module, *args):
                return subprocess.check_output([sys.executable, "-m", module, *args],
                                               cwd=root, text=True, stderr=subprocess.PIPE)

            git("init", "-q")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "Fixture")
            prefix = "urn:example:ontology:"
            base = "https://github.com/example/biology/blob/"
            profile, manifest, snapshot = ("settings/profile.json", "output/received.index.json",
                                           "output/vocab.nq.gz")
            output = "cache/dataset.nq"
            paths = ["notebooks/terms/cell.md", "notebooks/terms/tissue.md"]
            put(paths[0], "---\nname: Cell\ndescription: A test entry.\n"
                          "part-of: tissue\nsee-also: unknown-fiber\nexample: authored example\n"
                          "relations:\n  local-field: [another-sense]\n---\n# Cell\n")
            put(paths[1], "---\nname: Tissue\ndescription: Another test entry.\n---\n# Tissue\n")
            put("research.toml", '[corpus]\nlib_dirs=["notebooks/terms"]\n[vocabulary]\n'
                f'scheme="{prefix}scheme"\nnamespace="{prefix}term:"\n'
                f'document_base_url="{base}main"\noutput="settings/review.ttl"\n'
                f'members={json.dumps(paths)}\n')
            authored, config = "settings/relations.json", "settings/rdf.json"
            put(profile, json.dumps({"namespace": prefix, "repository": "example/biology",
                                    "contentRoot": "notebooks", "glossaryRoot": "notebooks/terms",
                                    "reviewedVocabulary": "settings/review.ttl", "authoredRelations": authored,
                                    "datasetConformance": config}))
            put(authored, json.dumps({"formatVersion": 1, "relations": {"part-of": "urn:example:part-of"}}))
            put(config, json.dumps({"dataset": {"file": output, "shapes": [], "ask": []}}))
            python("research_corpus.vocabulary", "--root", str(root))
            git("add", ".")
            git("commit", "-qm", "Select source")
            src = git("rev-parse", "HEAD")
            # Separate authored witness from the source producer; the receiver
            # must derive the expected evidence from the original frontmatter.
            graph = f"<{prefix}graph:authored-assertions>"
            v = prefix + "glossary-vocabulary:"
            cell, tissue = prefix + "term:cell", prefix + "term:tissue"
            witness = "<urn:example:owned-witness>"
            lines = [f"<{cell}> <urn:example:part-of> <{tissue}> {graph} ."]
            lines.extend(f"{witness} <{pred}> {value} {graph} ." for pred, value in (
                ("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", f"<{v}AuthoredRelationObservation>"),
                ("http://purl.org/dc/terms/source", f"<{base}main/{paths[0]}>"),
                (v + "predicateKey", '"part-of"'), (v + "rawTarget", '"tissue"'),
                (v + "projectionStatus", '"admitted-carrier"'), (v + "target", f"<{tissue}>"),
            ))
            for field, raw_value, status in (
                ("see-also", "unknown-fiber", "observed-unprojected"),
                ("local-field", "another-sense", "observed-unprojected"),
                ("example", "authored example", "admitted-literal"),
            ):
                observation = f"<urn:example:witness:{field}>"
                lines.extend(f"{observation} <{pred}> {value} {graph} ." for pred, value in (
                    ("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", f"<{v}AuthoredRelationObservation>"),
                    ("http://purl.org/dc/terms/source", f"<{base}main/{paths[0]}>"),
                    (v + "predicateKey", json.dumps(field)), (v + "rawTarget", json.dumps(raw_value)),
                    (v + "projectionStatus", json.dumps(status)),
                ))
            reviewed = Graph().parse(root / "settings/review.ttl", format="turtle")
            lines.extend(f"{s.n3()} {p.n3()} {o.n3()} <{prefix}graph:reviewed-vocabulary> ."
                         for s, p, o in reviewed)
            for path in paths:
                graph = f"<{prefix}graph:documents>"
                uri = URIRef(base + "main/" + path).n3()
                lines.extend(f"{uri} <{pred}> {value} {graph} ." for pred, value in (
                    ("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "<https://schema.org/DigitalDocument>"),
                    (v + "path", json.dumps(path)), (v + "gitBlob", json.dumps(git("rev-parse", src + ":" + path))),
                    (v + "termSchemaStatus", '"admitted"' if path == paths[0] else '"not-admitted"'),
                    ("http://www.w3.org/ns/prov#wasDerivedFrom", f"<{base}{src}/{path}>"),
                ))
            raw = ("\n".join(lines) + "\n").encode()
            packed = gzip.compress(raw, mtime=0)
            put(snapshot, packed)
            put(manifest, json.dumps({
                "formatVersion": 1,
                "artifact": {"path": snapshot, "sha256": hashlib.sha256(raw).hexdigest(),
                             "compressedSha256": hashlib.sha256(packed).hexdigest(), "quads": len(lines)},
                "coverage": {"audience": "authenticated", "trackedGlossaryMarkdown": 2, "projectedDocuments": 2,
                             "termSchemaAdmitted": 1, "termSchemaNotAdmitted": 1,
                             "authoredObservations": 4, "projectedAuthoredObservations": 2,
                             "unprojectedAuthoredObservations": 2},
                "source": {"commit": src, "contentTree": git("rev-parse", src + ":notebooks"),
                           "inputs": {name: git("rev-parse", src + ":" + name)
                                      for name in (profile, authored, config, "research.toml", "settings/review.ttl")}},
            }))
            git("add", ".")
            git("commit", "-qm", "Receive snapshot")
            args = ("--root", str(root), "--profile", profile, "--manifest", manifest,
                    "--snapshot", snapshot, "--output", output)
            for stage in ("prepare", "evidence", "authored"):
                result = python("research_corpus.glossary_snapshot", stage, *args)
            self.assertIn("Verified 1 reviewed concept assertions", result)
            self.assertIn("Verified original field values for all 4 authored observations (2 unprojected).", result)

            # Even when the tracked archive, prepared bytes and digests agree,
            # neither unresolved strings nor projected values may lose custody.
            original_record = json.loads((root / manifest).read_text("utf-8"))
            for original, substituted in (
                (b'"unknown-fiber"', b'"another-fiber"'),
                (b'"authored example"', b'"other example"'),
            ):
                with self.subTest(value=original):
                    changed = raw.replace(original, substituted)
                    changed_archive = gzip.compress(changed, mtime=0)
                    record = {**original_record, "artifact": {
                        **original_record["artifact"], "sha256": hashlib.sha256(changed).hexdigest(),
                        "compressedSha256": hashlib.sha256(changed_archive).hexdigest(),
                    }}
                    put(output, changed)
                    put(snapshot, changed_archive)
                    put(manifest, json.dumps(record))
                    with self.assertRaises(subprocess.CalledProcessError) as error:
                        python("research_corpus.glossary_snapshot", "authored", *args)
                    self.assertIn("RDF authorship differs from the pinned field value", error.exception.stderr)


class OwnerAssertionReplay(unittest.TestCase):
    def setUp(self):
        from rdflib import Dataset, Literal, RDF, URIRef
        from rdflib.namespace import DCTERMS, RDFS, SKOS

        self.ns = "urn:fixture:"
        self.dataset = Dataset()
        self.authored = self.dataset.graph(URIRef(self.ns + "graph:authored-assertions"))
        reviewed = self.dataset.graph(URIRef(self.ns + "graph:reviewed-vocabulary"))
        self.inquiry, self.evidence = map(URIRef, ("urn:fixture:inquiry", "urn:fixture:evidence"))
        self.source, self.target = map(URIRef, ("urn:fixture:inquiry-doc", "urn:fixture:evidence-doc"))
        self.predicate = URIRef("https://561.group/ns/predicate/produces")
        self.predicates = {"produces": str(self.predicate)}
        self.documents = {self.source, self.target}
        self.report = {"schema": "research-vocabulary.authored-relations.v1",
                       "audience": "authenticated", "unresolved": [], "assertions": [{
                           "subject": str(self.inquiry), "predicate": str(self.predicate),
                           "object": str(self.evidence), "source": str(self.source),
                           "targetSource": str(self.target), "field": "produces", "rawValue": "evidence",
                       }]}
        for concept, document in ((self.inquiry, self.source), (self.evidence, self.target)):
            reviewed.add((concept, RDF.type, SKOS.Concept))
            reviewed.add((concept, RDFS.isDefinedBy, document))
        self.owner = URIRef("urn:fixture:owner-witness")
        self.owner_edge = (self.inquiry, self.predicate, self.evidence)
        self.authored.add(self.owner_edge)
        vocab = self.ns + "glossary-vocabulary:"
        self.raw = URIRef(vocab + "rawTarget")
        self.target_predicate = URIRef(vocab + "target")
        self.owner_properties = (
            (RDF.type, URIRef(vocab + "AuthoredRelationObservation")),
            (DCTERMS.source, self.source), (URIRef(vocab + "predicateKey"), Literal("produces")),
            (self.raw, Literal("evidence")),
            (URIRef(vocab + "projectionStatus"), Literal("admitted-carrier")),
            (self.target_predicate, self.evidence),
        )
        for predicate, value in self.owner_properties:
            self.authored.add((self.owner, predicate, value))
        # The same predicate also has a legitimate Term document-level
        # projection. It does not belong to the reviewed owner comparison.
        other = URIRef("urn:fixture:term-witness")
        self.authored.add((self.target, self.predicate, self.source))
        for predicate, value in self.owner_properties:
            self.authored.add((other, predicate, self.target if predicate == DCTERMS.source
                               else self.source if predicate == self.target_predicate else value))

    def verify(self):
        return verify_owner_assertions(self.dataset, self.ns, self.documents, self.predicates, self.report)

    def test_owner_replay_does_not_consume_term_document_projection(self):
        self.assertEqual(self.verify(), 1)

    def test_extra_reverse_assertion_refuses_even_with_complete_positive_evidence(self):
        self.authored.add((self.evidence, self.predicate, self.inquiry))
        with self.assertRaisesRegex(ValueError, "owner assertions differ"):
            self.verify()

    def test_source_value_disagreement_refuses_even_when_exact_typed_edge_survives(self):
        from rdflib import Literal

        self.authored.set((self.owner, self.raw, Literal("unrelated-value")))
        with self.assertRaisesRegex(ValueError, "witnesses differ"):
            self.verify()

    def test_valid_duplicate_witness_is_not_lost_in_rdf_set_comparison(self):
        from rdflib import URIRef

        duplicate = URIRef("urn:fixture:duplicate")
        for predicate, value in self.owner_properties:
            self.authored.add((duplicate, predicate, value))
        with self.assertRaisesRegex(ValueError, "witnesses differ"):
            self.verify()


class NavigationGraphReplay(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.snapshot = self.root / "snapshot.nq"
        self.replay = self.root / "replay.nq"
        self.raw_target = f'<urn:fixture:link:1> <{V}rawTarget> "claim.md" {NAVIGATION_GRAPH} .\n'
        self.target = f'<urn:fixture:link:1> <{V}target> <urn:fixture:document:claim> {NAVIGATION_GRAPH} .\n'
        self.replay.write_text(self.raw_target + self.target, encoding="utf-8")

    def verify(self):
        return compare_navigation(parse_nquads(self.snapshot.read_bytes()),
                                  parse_nquads(self.replay.read_bytes()), "urn:fixture:vocab:")

    def test_compares_only_the_graphed_navigation_evidence(self):
        unrelated = f'<urn:fixture:concept> <urn:fixture:definition> "Reviewed" {REVIEWED_GRAPH} .\n'
        self.snapshot.write_text(self.target + unrelated + self.raw_target, encoding="utf-8")
        self.assertEqual(self.verify(), 2)

    def test_same_target_and_count_do_not_authenticate_an_invented_spelling(self):
        self.snapshot.write_text(self.raw_target.replace("claim.md", "invented.md") + self.target,
                                 encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "navigation differs"):
            self.verify()

    def test_empty_native_navigation_requires_an_empty_actual_navigation_graph(self):
        self.replay.write_text("", encoding="utf-8")
        other = f'<urn:fixture:concept> <urn:fixture:definition> "Reviewed" {REVIEWED_GRAPH} .\n'
        self.snapshot.write_text(other, encoding="utf-8")
        self.assertEqual(self.verify(), 0)
        self.snapshot.write_text(other + self.raw_target, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "navigation differs"):
            self.verify()

    def test_replay_must_not_emit_another_named_graph(self):
        self.replay.write_text(self.target + self.raw_target.replace(NAVIGATION_GRAPH, REVIEWED_GRAPH),
                               encoding="utf-8")
        self.snapshot.write_text(self.target, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "only its named graph"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
