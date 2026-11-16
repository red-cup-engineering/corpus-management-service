"""Receive the historical archive citation grammar through the original CLI.

The small authored fixture exercises the documented citekey-keyed chapter
manifest, not an assertion that a synthetic citation is an archival source.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research_citations import load


class CitationReceivingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "concepts").mkdir()
        (self.root / "research.toml").write_text(
            '[corpus]\nlib_dirs = ["concepts"]\n', encoding="utf-8"
        )
        self.note = self.root / "concepts" / "source.md"
        self.source = '''---
name: Citation receiving fixture
references:
  fixture-chapter:
    class: chapter
    title: A chapter about relations
    authors: ["Example, Ada"]
    editors: ["Editor, Eli"]
    year: 2026
    in: Collected research
    location: Example City
    publisher: Example Press
    pages: "11--24"
---
This fixture cites a chapter using the original archive manifest grammar.
'''
        self.note.write_text(self.source, encoding="utf-8")

    def generate(self):
        return subprocess.run(
            [sys.executable, "-m", "cite_tool", "generate", "--root", str(self.root)],
            cwd=self.root, text=True, capture_output=True, timeout=30,
        )

    def test_archive_chapter_is_received_as_complete_bibtex(self):
        references, issues = load(self.root, ("concepts",))
        self.assertEqual(issues, [])
        self.assertEqual(set(references), {"fixture-chapter"})
        chapter = references["fixture-chapter"]
        self.assertEqual(chapter.type, "incollection")
        self.assertEqual(chapter.source_path, "concepts/source.md")
        self.assertTrue(chapter.declared_inline)
        self.assertEqual(chapter.fields["booktitle"], "Collected research")
        self.assertEqual(chapter.fields["address"], "Example City")
        self.assertNotIn("class", chapter.fields)
        self.assertNotIn("in", chapter.fields)
        self.assertNotIn("location", chapter.fields)

        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = (self.root / "references.bib").read_text(encoding="utf-8")
        # Field iteration order is not the publication contract; their complete
        # identities and values are. Do not compare against the renderer itself.
        self.assertIn("@incollection{fixture-chapter,\n", output)
        fields = {line.strip().rstrip(",") for line in output.splitlines() if " = " in line}
        self.assertEqual(fields, {
            "author = {Example, Ada}", "editor = {Editor, Eli}",
            "title = {A chapter about relations}", "year = {2026}",
            "booktitle = {Collected research}", "address = {Example City}",
            "publisher = {Example Press}", "pages = {11--24}",
        })
        self.assertEqual(output.count("@incollection{"), 1)
        self.assertEqual(self.note.read_text(encoding="utf-8"), self.source)

    def test_conflicting_archive_fields_cannot_replace_existing_projection(self):
        bad = self.source.replace(
            "    in: Collected research\n",
            "    in: Collected research\n    booktitle: A different work\n",
        )
        self.note.write_text(bad, encoding="utf-8")
        output = self.root / "references.bib"
        original = b"% Existing received bibliography\n@misc{keep, title={Retain me}}\n"
        output.write_bytes(original)
        result = self.generate()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("references-field-conflict", result.stderr)
        self.assertIn("fixture-chapter", result.stderr)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(self.note.read_text(encoding="utf-8"), bad)


if __name__ == "__main__":
    unittest.main()
