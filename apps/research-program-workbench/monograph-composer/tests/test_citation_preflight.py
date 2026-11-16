"""Native Pandoc receiving for the original monograph composer."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from monograph_composer.__main__ import main


class CitationPreflightTest(unittest.TestCase):
    def create_corpus(self, root: Path) -> Path:
        (root / "terms").mkdir()
        (root / "research.toml").write_text('[corpus]\nlib_dirs = ["terms"]\n')
        (root / "references.bib").write_text(
            '@book{Case_With_Underscore, title={Exact key}, author={Author, Alice}, year={2021}}\n'
            '@book{source.key, title={Braced key}, author={Writer, Will}, year={2022}}\n'
        )
        return root / "terms" / "claim.md"

    def run_composer(self, root: Path) -> tuple[int, str]:
        error = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(error):
            status = main(["--root", str(root), "--out", str(root / "reader.md"),
                           "--require-resolved-citations"])
        return status, error.getvalue()

    def test_native_markdown_syntax_agrees_with_the_final_bibliography(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = self.create_corpus(root)
            note.write_text("""---
name: Actual citation syntax
type: term
---

A grouped citation [see -@Case_With_Underscore, p. 8; @{source.key}].
This example is displayed as code: `[@not_a_citation]`.
""")
            status, error = self.run_composer(root)
            self.assertEqual(status, 0, error)
            reader = (root / "reader.md").read_text()
            self.assertIn("{#ref-Case_With_Underscore .csl-entry}", reader)
            self.assertIn("{#ref-source.key .csl-entry}", reader)
            self.assertIn("[@not_a_citation]", reader)

    def test_selected_generated_bibliography_cannot_be_supplemented_by_stale_fallback(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = self.create_corpus(root)
            note.write_text("""---
name: Generated bibliography selection
type: term
references:
  generated:
    type: book
    title: Authored in the corpus
    authors: ["Writer, Will"]
    year: 2026
    publisher: Example Press
---

Two visible keys [@generated; @Case_With_Underscore; @case_with_underscore].
""")
            reader = root / "reader.md"
            reader.write_bytes(b"Previously received reader\n")
            status, error = self.run_composer(root)
            self.assertEqual(status, 1, error)
            self.assertIn("Case_With_Underscore", error)
            self.assertIn("case_with_underscore", error)
            self.assertNotIn("unresolved citation: generated", error)
            self.assertEqual(reader.read_bytes(), b"Previously received reader\n")
            self.assertFalse((root / "tools/build/references.bib").exists())
