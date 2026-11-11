"""Source-to-SKOS receiving and refusal cases using the original corpus loader."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from research_corpus import load
from research_corpus.config import load_config
from research_corpus.vocabulary import main, render


class VocabularyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.terms = "content/text/glossary/terms"
        self.concepts = "content/text/glossary/concepts"
        self.member = f"{self.terms}/relating.md"
        self.destination = self.root / "data/records/ontology.ttl"
        self.note(self.member)
        self.config()

    def note(self, path: str, **fields) -> Path:
        note = self.root / path
        note.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = {"name": "Relating", "description": "Activity that articulates distinctions.",
                       "type": "term", **fields}
        note.write_text("---\n" + yaml.safe_dump(frontmatter, allow_unicode=True)
                        + "---\n# Relating\n\nA source-held definition.\n", encoding="utf-8")
        return note

    def config(self, *, members=None, **overrides) -> None:
        vocabulary = {
            "scheme": "urn:561:relationality:vocabulary",
            "namespace": "urn:561:relationality:concept:",
            "document_base_url": "https://github.com/lenticule-science/relationality-science-services-section/blob/main",
            "output": "data/records/ontology.ttl",
            "members": [self.member] if members is None else members,
            **overrides,
        }
        text = "[corpus]\nlib_dirs = " + json.dumps([self.terms, self.concepts]) + "\n"
        text += "\n[vocabulary]\n"
        text += "".join(f"{key} = {json.dumps(value)}\n" for key, value in vocabulary.items())
        (self.root / "research.toml").write_text(text, encoding="utf-8")

    def cli(self, *options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(["--root", str(self.root), *options])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_actual_nested_glossary_path_projects_source_fields(self):
        self.note(self.member, title="Secondary title", id="561-relationality:relating",
                  source="https://example.org/source",
                  **{"original-source": "urn:example:original"})
        self.note(f"{self.terms}/not-selected.md", name="Unselected")
        status, _, error = self.cli()
        self.assertEqual(status, 0, error)
        output = self.destination.read_text(encoding="utf-8")
        self.assertIn("<urn:561:relationality:vocabulary> a skos:ConceptScheme .", output)
        self.assertIn("<urn:561:relationality:concept:relating>\n    a skos:Concept", output)
        self.assertIn('skos:prefLabel "Relating"', output)
        self.assertIn('skos:definition "Activity that articulates distinctions."', output)
        self.assertIn('dct:identifier "561-relationality:relating"', output)
        self.assertIn("prov:wasDerivedFrom <https://example.org/source>", output)
        self.assertIn("prov:wasDerivedFrom <urn:example:original>", output)
        self.assertIn("/blob/main/content/text/glossary/terms/relating.md>", output)
        self.assertNotIn("Unselected", output)
        self.assertNotIn("Secondary title", output)
        self.assertEqual(self.cli("--check")[0], 0)

    def test_title_is_used_when_name_is_absent(self):
        path = self.root / self.member
        path.write_text("---\ntitle: FOUR\ndescription: Four evidence states.\ntype: term\n---\n# FOUR\n")
        self.assertEqual(self.cli()[0], 0)
        self.assertIn('skos:prefLabel "FOUR"', self.destination.read_text())
        self.assertNotIn("dct:identifier", self.destination.read_text())

    def test_member_order_and_duplicate_provenance_do_not_change_bytes(self):
        other = f"{self.concepts}/attending.md"
        self.note(other, name="Attending", sources=["https://example.org/a", "https://example.org/a"])
        self.config(members=[self.member, other])
        first = render(load(self.root))
        self.config(members=[other, self.member])
        self.assertEqual(render(load(self.root)), first)
        self.assertEqual(first.count(b"prov:wasDerivedFrom <https://example.org/a>"), 1)

    def test_check_reports_drift_without_replacing_output(self):
        self.assertEqual(self.cli()[0], 0)
        original = self.destination.read_bytes()
        self.note(self.member, description="A revised definition.")
        self.assertEqual(self.cli("--check")[0], 1)
        self.assertEqual(self.destination.read_bytes(), original)
        self.assertEqual(self.cli()[0], 0)
        self.assertNotEqual(self.destination.read_bytes(), original)
        self.assertEqual(self.cli("--check")[0], 0)

    def test_check_missing_output_creates_nothing(self):
        self.assertEqual(self.cli("--check")[0], 1)
        self.assertFalse(self.destination.parent.exists())

    def test_missing_or_unindexed_source_never_replaces_existing_output(self):
        self.assertEqual(self.cli()[0], 0)
        original = self.destination.read_bytes()
        for member in (f"{self.terms}/absent.md", "lib/legacy/relating.md"):
            with self.subTest(member=member):
                if member.startswith("lib/"):
                    self.note(member)
                self.config(members=[member])
                status, _, error = self.cli()
                self.assertEqual(status, 2)
                self.assertIn("not an indexed source", error)
                self.assertEqual(self.destination.read_bytes(), original)

    def test_duplicate_and_nonexact_member_paths_are_refused(self):
        for members in ([self.member, self.member], ["./" + self.member],
                        ["content/text/glossary/../terms/relating.md"], ["/" + self.member], []):
            with self.subTest(members=members):
                self.config(members=members)
                self.assertEqual(self.cli()[0], 2)
                self.assertFalse(self.destination.exists())

    def test_selected_parse_failure_and_slug_collision_are_refused(self):
        (self.root / self.member).write_text("No frontmatter.\n")
        self.assertEqual(self.cli()[0], 2)
        self.note(self.member)
        self.note(f"{self.concepts}/relating.md")
        status, _, error = self.cli()
        self.assertEqual(status, 2)
        self.assertIn("slug-collision", error)
        self.assertFalse(self.destination.exists())

    def test_unselected_parse_error_does_not_silently_change_whole_corpus(self):
        invalid = self.root / self.terms / "unreviewed.md"
        invalid.write_text("No frontmatter.\n")
        self.assertEqual(len(load(self.root).parse_errors), 1)
        self.assertEqual(self.cli()[0], 0)
        self.assertEqual(len(load(self.root).parse_errors), 1)

    def test_missing_or_malformed_required_frontmatter_is_refused(self):
        for fields in ({"name": ""}, {"name": ["Relating"]}, {"description": " "},
                       {"description": False}, {"id": 123}):
            with self.subTest(fields=fields):
                self.note(self.member, **fields)
                self.assertEqual(self.cli()[0], 2)
                self.assertFalse(self.destination.exists())
        (self.root / self.member).write_text("---\ntype: term\n---\n# A title alone is insufficient.\n")
        self.assertEqual(self.cli()[0], 2)

    def test_descriptive_provenance_is_kept_in_source_not_coerced_to_iri(self):
        descriptive = {
            "source": "Leader's 2026-10-20 correction in the Adventure/Quest/Mystery conversation",
            "original-owner": "lenticule-science/obsmetrologia",
        }
        self.note(self.member, provenance=descriptive,
                  source="Conversation: a correction made in person",
                  sources=["https://example.org/witness", "urn:example:receipt"])
        original = (self.root / self.member).read_bytes()
        self.assertEqual(self.cli()[0], 0)
        output = self.destination.read_text()
        self.assertNotIn("Leader's", output)
        self.assertNotIn("Conversation:", output)
        self.assertIn("prov:wasDerivedFrom <https://example.org/witness>", output)
        self.assertIn("prov:wasDerivedFrom <urn:example:receipt>", output)
        self.assertEqual((self.root / self.member).read_bytes(), original)

    def test_url_bearing_provenance_entries_are_preserved(self):
        self.note(self.member, provenance=[
            {"url": "https://example.org/a", "description": "A contextual note."},
            {"source_url": "urn:example:b"}, {"source": "https://example.org/c"},
            "https://example.org/d", "Unlinked historical description.",
        ])
        self.assertEqual(self.cli()[0], 0)
        output = self.destination.read_text()
        for iri in ("https://example.org/a", "urn:example:b", "https://example.org/c", "https://example.org/d"):
            self.assertIn(f"prov:wasDerivedFrom <{iri}>", output)

    def test_invalid_attempted_source_iris_are_refused(self):
        for fields in (
            {"sources": ["file:///private/source"]}, {"sources": ["not an IRI"]},
            {"sources": "https://example.org/a"}, {"sources": ["https://"]},
            {"source": "https:/missing-host"}, {"source": "https://example.org/%ZZ"},
            {"provenance": {"source_url": "javascript:alert(1)"}},
            {"sources": ["https://example.org/> . <urn:evil:x>"]},
        ):
            with self.subTest(fields=fields):
                self.note(self.member, **fields)
                self.assertEqual(self.cli()[0], 2)
                self.assertFalse(self.destination.exists())

    def test_turtle_literals_preserve_quotes_backslashes_newlines_and_unicode(self):
        label = 'A "quoted" label \\ ∞'
        definition = 'First line.\nSecond\tline with "quotes", \\ and \x00 control.'
        self.note(self.member, name=label, description=definition)
        self.assertEqual(self.cli()[0], 0)
        lines = self.destination.read_text(encoding="utf-8").splitlines()
        label_line = next(line for line in lines if "skos:prefLabel" in line)
        definition_line = next(line for line in lines if "skos:definition" in line)
        # Turtle's emitted short string escapes share this JSON subset; the
        # roundtrip asserts that no text escaped its literal into extra triples.
        self.assertEqual(json.loads(label_line.strip().removeprefix("skos:prefLabel ").removesuffix(" ;")), label)
        self.assertEqual(json.loads(definition_line.strip().removeprefix("skos:definition ").removesuffix(" ;")), definition)

    def test_document_paths_and_subject_suffixes_are_percent_encoded(self):
        member = f"{self.terms}/relation with space.md"
        self.note(member)
        self.config(members=[member])
        self.assertEqual(self.cli()[0], 0)
        output = self.destination.read_text()
        self.assertIn("<urn:561:relationality:concept:relation%20with%20space>", output)
        self.assertIn("/terms/relation%20with%20space.md>", output)

    def test_invalid_configuration_iris_are_refused(self):
        for fields in (
            {"scheme": "relative-scheme"}, {"scheme": "urn:missing-value"},
            {"namespace": "https://example.org/no-delimiter"},
            {"document_base_url": "urn:example:documents"},
            {"document_base_url": "https://example.org/?query=1"},
            {"document_base_url": "https://example.org/#fragment"},
            {"scheme": "urn:561:relationality:concept:relating"},
        ):
            with self.subTest(fields=fields):
                self.config(**fields)
                self.assertEqual(self.cli()[0], 2)
                self.assertFalse(self.destination.exists())

    def test_output_cannot_escape_root_or_replace_a_source_note(self):
        for output in ("../outside.ttl", "/tmp/outside.ttl", self.member, "research.toml"):
            with self.subTest(output=output):
                self.config(output=output)
                self.assertEqual(self.cli()[0], 2)
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "linked").symlink_to(outside, target_is_directory=True)
            self.config(output="linked/outside.ttl")
            self.assertEqual(self.cli()[0], 2)
            self.assertFalse((Path(outside) / "outside.ttl").exists())

    def test_output_symlink_is_refused(self):
        self.destination.parent.mkdir(parents=True)
        other = self.root / "original.ttl"
        other.write_text("Existing source.")
        self.destination.symlink_to(other)
        self.assertEqual(self.cli()[0], 2)
        self.assertEqual(other.read_text(), "Existing source.")

    def test_absent_vocabulary_keeps_original_config_compatible(self):
        (self.root / "research.toml").write_text("[corpus]\nlib_dirs = " + json.dumps([self.terms]) + "\n")
        self.assertIsNone(load_config(self.root).vocabulary)
        self.assertEqual(len(load(self.root)), 1)
        status, _, error = self.cli()
        self.assertEqual(status, 2)
        self.assertIn("no [vocabulary]", error)

    def test_module_cli_uses_the_same_exporter_and_check_mode(self):
        result = subprocess.run(
            [sys.executable, "-m", "research_corpus.vocabulary", "--root", str(self.root)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        check = subprocess.run(
            [sys.executable, "-m", "research_corpus.vocabulary", "--root", str(self.root), "--check"],
            capture_output=True, text=True,
        )
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
