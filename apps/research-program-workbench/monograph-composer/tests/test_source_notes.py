"""Receive nested Science source annotations as accessible monograph content."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from monograph_composer.__main__ import _yaml_preamble, main
from monograph_composer.render import extract_title_and_body
from research_corpus import load
from research_corpus.frontmatter import parse_note
from research_corpus.links import prose_links_text


class SourceNoteCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.teaching = "content/text/documents/articles/teaching-articles/explanations"
        self.references = "content/text/documents/articles/bibliographies/references"
        (self.root / "research.toml").write_text(
            "[corpus]\nlib_dirs = "
            + json.dumps([self.teaching, self.references, "references"]) + "\n"
        )

    def note(self, folder: str, slug: str, *, kind: str, body: str,
             title: str = "Source title") -> None:
        path = self.root / folder / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\ntype: {kind}\ntitle: {title}\n---\n{body}\n",
            encoding="utf-8",
        )

    def compose(self) -> tuple[str, str]:
        with contextlib.redirect_stdout(io.StringIO()):
            status = main(["--root", str(self.root), "--no-pandoc"])
        self.assertEqual(status, 0)
        build = self.root / "tools/build"
        return ((build / "composed.md").read_text(encoding="utf-8"),
                (build / "manifest.txt").read_text(encoding="utf-8"))

    def test_nested_source_notes_have_full_bodies_and_all_rewritten_targets(self):
        self.note(self.teaching, "lesson", kind="narrative", body=(
            "# Reading source contracts\n\n"
            "Read [the spine](../../bibliographies/references/obsmetrologia-spine.md) "
            "and [Belnap](../../bibliographies/references/belnap-four.md).\n"
        ))
        code_example = "```markdown\n# Literal source example\n[not a book link](absent.md)\n```"
        self.note(self.references, "obsmetrologia-spine", kind="reference", body=(
            "# Inspected `Spine` source\n\nThe source has explicit inputs.\n\n"
            "## Lean verification limits\n\nThis is source inspection, not a new proof replay.\n\n"
            + code_example + "\n\n"
            "Compare [Belnap](belnap-four.md) and "
            "[the lesson](../../teaching-articles/explanations/lesson.md).\n"
        ))
        self.note(self.references, "belnap-four", kind="reference", body=(
            "# Belnap's account\n\nAnnotated mathematical source.\n\n"
            "[Original chapter](https://example.org/chapter).\n"
        ))
        composed, manifest = self.compose()
        self.assertIn("### Source notes {#appendix-source-notes}", composed)
        self.assertIn("#### Inspected `Spine` source {#obsmetrologia-spine}", composed)
        self.assertIn("##### Lean verification limits", composed)
        self.assertIn("This is source inspection, not a new proof replay.", composed)
        self.assertIn(code_example, composed)
        self.assertIn("[Belnap](#belnap-four)", composed)
        self.assertIn("[the lesson](#lesson)", composed)
        self.assertIn("[Original chapter](https://example.org/chapter)", composed)
        prose = prose_links_text(composed)
        anchors = re.findall(r"\{#([^}]+)\}", prose)
        targets = re.findall(r"\]\(#([^\s)]+)\)", prose)
        self.assertEqual(set(targets) - set(anchors), set())
        for slug in ("lesson", "obsmetrologia-spine", "belnap-four"):
            self.assertEqual(anchors.count(slug), 1)
        self.assertEqual(len(manifest.splitlines()), len(load(self.root)))
        self.assertIn(f"R {self.references}/obsmetrologia-spine\treference", manifest)

    def test_root_reference_pathway_remains_separate_and_is_not_duplicated(self):
        self.note("references", "historical", kind="reference", body=(
            "# Historical annotation\n\nLegacy annotation remains available.\n"
        ))
        self.note(self.references, "primary", kind="reference", body=(
            "# Nested source\n\nCurrent source annotation.\n"
        ))
        self.note(self.teaching, "lesson", kind="narrative", body=(
            "# Lesson\n\n[Primary](../../bibliographies/references/primary.md).\n"
        ))
        composed, _ = self.compose()
        self.assertIn("### Further reading {#appendix-further-reading}", composed)
        self.assertIn("### Source notes {#appendix-source-notes}", composed)
        self.assertEqual(composed.count("{#historical}"), 1)
        self.assertEqual(composed.count("{#primary}"), 1)
        self.assertIn("Legacy annotation remains available.", composed)
        self.assertIn("Current source annotation.", composed)

    def test_citation_does_not_erase_nested_annotation_or_invent_bibliography(self):
        self.note(self.references, "primary", kind="reference", body=(
            "# Primary account\n\nIts scope and limitations remain readable.\n"
        ))
        self.note(self.teaching, "lesson", kind="narrative", body=(
            "# Lesson\n\n[@primary] and "
            "[source annotation](../../bibliographies/references/primary.md).\n"
        ))
        composed, _ = self.compose()
        self.assertIn("[@primary]", composed)
        self.assertIn("[source annotation](#primary)", composed)
        self.assertEqual(composed.count("{#primary}"), 1)
        self.assertIn("Its scope and limitations remain readable.", composed)
        self.assertFalse((self.root / "tools/build/references.bib").exists())

    def test_no_nested_references_adds_no_empty_source_appendix(self):
        self.note(self.teaching, "lesson", kind="narrative", body="# A lesson\n\nContent.")
        composed, manifest = self.compose()
        self.assertNotIn("appendix-source-notes", composed)
        self.assertEqual(len(manifest.splitlines()), 1)

    def test_title_retains_trailing_and_entire_inline_code(self):
        for heading, expected in (
            ("# The `FOUR`", "The `FOUR`"),
            ("# `Spine`", "`Spine`"),
            ("# The `FOUR` {#custom}", "The `FOUR`"),
            ("# `Spine` {#custom}", "`Spine`"),
        ):
            with self.subTest(heading=heading):
                title, body = extract_title_and_body(heading + "\n\nSource text.", strip_lean=False)
                self.assertEqual(title, expected)
                self.assertEqual(body, "Source text.")

    def test_preamble_preserves_metadata_through_real_yaml_parser(self):
        title = 'Relationality: sources, "meanings" and models'
        subtitle = 'First line\nSecond: line with "quotes", \\ and Unicode \u0085 ∞'
        bibliography = 'sources: reviewed/"references".bib'
        document = "\n".join(_yaml_preamble(title, subtitle, bibliography)) + "\n# Body\n"
        fields, body = parse_note(document)
        self.assertEqual(fields["title"], title)
        self.assertEqual(fields["subtitle"], subtitle)
        self.assertEqual(fields["bibliography"], bibliography)
        self.assertEqual(body, "\n# Body\n")


if __name__ == "__main__":
    unittest.main()
