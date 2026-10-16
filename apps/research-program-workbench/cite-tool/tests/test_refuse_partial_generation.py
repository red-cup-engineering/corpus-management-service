"""Do not overwrite an existing bibliography when archival citations fail admission."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from cite_tool.__main__ import cmd_generate


class BibliographyGenerationTest(unittest.TestCase):
    def test_conflicting_historical_reference_never_clobbers_existing_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "concepts").mkdir()
            (root / "concepts" / "item.md").write_text("""---
references:
  a1977: {class: article, type: book, title: Mismatch, year: 1977}
---
""")
            bib = root / "references.bib"
            bib.write_text("PREVIOUS VALID BIBLIOGRAPHY\n")
            status = cmd_generate(SimpleNamespace(root=root, out=None, verbose=False))
            self.assertEqual(status, 1)
            self.assertEqual(bib.read_text(), "PREVIOUS VALID BIBLIOGRAPHY\n")

    def test_valid_historical_reference_can_generate_bibliography(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "concepts").mkdir()
            (root / "concepts" / "item.md").write_text("""---
references:
  grice1975: {class: book, title: Logic and Conversation, year: 1975}
---
""")
            status = cmd_generate(SimpleNamespace(root=root, out=None, verbose=False))
            self.assertEqual(status, 0)
            self.assertIn("@book{grice1975", (root / "references.bib").read_text())


if __name__ == "__main__":
    unittest.main()
