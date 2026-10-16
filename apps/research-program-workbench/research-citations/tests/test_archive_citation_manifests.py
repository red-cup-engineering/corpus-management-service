"""Acceptance examples for both original research-citations and archive-org manifests.

Source grammars:
* emsenn/emsenn-archive-code: topical/information/561-group/research-tools/research/citations/README.md
* emsenn/emsenn-archive-org: citations.md (historical keyed map contract)
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_citations import load, render


class ArchiveCitationManifestTest(unittest.TestCase):
    def _read(self, source: str):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "concepts").mkdir()
            (root / "concepts" / "example.md").write_text(source)
            return load(root, ("concepts",))

    def test_keyed_chapter_and_historical_field_names(self):
        refs, issues = self._read("""---
references:
  grice1975:
    class: chapter
    title: Logic and Conversation
    authors: ["Grice, H. Paul"]
    year: 1975
    in: Syntax and Semantics, Vol. 3
    location: New York
---
Citing [@grice1975].
""")
        self.assertFalse([i for i in issues if i.severity == "error"], issues)
        ref = refs["grice1975"]
        self.assertEqual(ref.type, "incollection")
        self.assertEqual(ref.fields["booktitle"], "Syntax and Semantics, Vol. 3")
        self.assertEqual(ref.fields["address"], "New York")
        self.assertNotIn("class", ref.fields)
        bib = render(refs.values())
        self.assertIn("@incollection{grice1975", bib)
        self.assertIn("booktitle = {Syntax and Semantics, Vol. 3}", bib)

    def test_original_list_manifest_is_unchanged(self):
        refs, issues = self._read("""---
references:
  - key: belnap1977
    type: article
    title: A Useful Four-Valued Logic
    year: 1977
    journal: Inquiry
---
Citing [@belnap1977].
""")
        self.assertIn("belnap1977", refs)
        self.assertEqual(refs["belnap1977"].type, "article")
        self.assertFalse([i for i in issues if i.severity == "error"], issues)

    def test_keyed_class_type_disagreement_is_refused(self):
        refs, issues = self._read("""---
references:
  a1977: {class: article, type: book, title: Mismatch, year: 1977}
---
""")
        self.assertFalse(refs)
        self.assertIn("references-class-type-conflict", [i.code for i in issues])

    def test_key_disagreement_is_refused(self):
        refs, issues = self._read("""---
references:
  a1977: {key: b1977, class: book, title: Mismatch, year: 1977}
---
""")
        self.assertFalse(refs)
        self.assertIn("references-key-conflict", [i.code for i in issues])

    def test_lossy_alias_replacement_is_refused(self):
        refs, issues = self._read("""---
references:
  a1977:
    class: chapter
    title: Mismatch
    year: 1977
    in: Old Book
    booktitle: Different Book
---
""")
        self.assertFalse(refs)
        self.assertIn("references-field-conflict", [i.code for i in issues])

    def test_unsupported_historical_class_is_refused(self):
        refs, issues = self._read("""---
references:
  a1977: {class: made-up, title: Mismatch, year: 1977}
---
""")
        self.assertFalse(refs)
        self.assertIn("references-unknown-class", [i.code for i in issues])

    def test_nonmapping_value_is_refused(self):
        refs, issues = self._read("""---
references:
  a1977: 42
---
""")
        self.assertFalse(refs)
        self.assertIn("references-invalid-entry", [i.code for i in issues])

    def test_legacy_annotation_is_additive_and_inline_wins(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "concepts").mkdir()
            (root / "references").mkdir()
            (root / "concepts" / "example.md").write_text("""---
references:
  grice1975: {class: book, title: Inline Title, year: 1975}
---
""")
            (root / "references" / "grice1975.md").write_text("""---
class: book
title: Annotation Title
year: 1975
authors: ["Grice, H. Paul"]
---
Research notes
""")
            refs, issues = load(root, ("concepts",))
            self.assertFalse([i for i in issues if i.severity == "error"], issues)
            self.assertEqual(refs["grice1975"].fields["title"], "Inline Title")
            self.assertEqual(refs["grice1975"].authors, ["Grice, H. Paul"])
            self.assertNotIn("class", refs["grice1975"].fields)

    def test_invalid_scalar_manifest_is_refused(self):
        refs, issues = self._read("""---
references: invalid
---
""")
        self.assertFalse(refs)
        self.assertIn("references-invalid-shape", [i.code for i in issues])


if __name__ == "__main__":
    unittest.main()
