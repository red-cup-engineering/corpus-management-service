"""Installed Workbench receiving for a source-owned living Science section."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import yaml

from monograph_composer.__main__ import main as compose
from program_validator.__main__ import main as validate
from research_corpus.vocabulary import main as vocabulary


TERM = "content/text/glossary/terms"
SOURCES = "content/text/documents/articles/bibliographies/references"
ARCHIVE = "lib/legacy"
SOURCE_LINK = "../../documents/articles/bibliographies/references/witness.md"


class LivingScienceReceivingTest(unittest.TestCase):
    def create_corpus(self, root: Path) -> None:
        (root / TERM).mkdir(parents=True)
        (root / SOURCES).mkdir(parents=True)
        (root / ARCHIVE).mkdir(parents=True)
        (root / "research.toml").write_text(f"""
[program]
title = "Living section: proof and evidence"
[corpus]
lib_dirs = ["{TERM}", "{SOURCES}"]
[validate]
min_body_chars = 1
[vocabulary]
scheme = "urn:example:scheme:science"
namespace = "urn:example:concept:"
document_base_url = "https://example.invalid/source/"
output = "data/records/vocabulary.ttl"
members = ["{TERM}/witnessing.md"]
""", encoding="utf-8")
        (root / TERM / "witnessing.md").write_text(f"""---
name: Witnessing
id: urn:example:source:witnessing
description: Evidence presented for an explicitly named claim.
type: term
source: https://example.invalid/archive/witness
---

Keep the [exact source]({SOURCE_LINK}) with the claim it supports.
""", encoding="utf-8")
        (root / SOURCES / "witness.md").write_text("""---
name: Source witness
type: reference
---

This source records one observation, not a theorem.
""", encoding="utf-8")
        (root / ARCHIVE / "witness.md").write_text(
            "---\nname: Retired witness\ntype: reference\n---\n\nUnenrolled archive.\n",
            encoding="utf-8",
        )

    def run_validator(self, root: Path) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            code = validate(["--root", str(root), "--no-lean", "--format", "json"])
        return code, json.loads(output.getvalue())

    def test_selected_source_reaches_validation_vocabulary_and_reader(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_corpus(root)
            status, report = self.run_validator(root)
            self.assertEqual(status, 0, report)
            self.assertEqual(report["total_notes"], 2)
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(vocabulary(["--root", str(root)]), 0)
                self.assertEqual(vocabulary(["--root", str(root), "--check"]), 0)
                self.assertEqual(compose(["--root", str(root), "--no-pandoc"]), 0)
            projected = (root / "data/records/vocabulary.ttl").read_text()
            self.assertIn("<urn:example:concept:witnessing>", projected)
            self.assertIn('dct:identifier "urn:example:source:witnessing"', projected)
            self.assertIn("prov:wasDerivedFrom <https://example.invalid/archive/witness>", projected)
            reader = (root / "tools/build/composed.md").read_text()
            self.assertEqual(yaml.safe_load(reader.split("---", 2)[1])["title"],
                             "Living section: proof and evidence")
            self.assertIn("[exact source](#witness)", reader)
            self.assertEqual(reader.count("{#witness}"), 1)
            self.assertIn("This source records one observation, not a theorem.", reader)
            self.assertNotIn("Unenrolled archive", reader)
            manifest = (root / "tools/build/manifest.txt").read_text()
            self.assertIn(f"R {SOURCES}/witness\treference", manifest)

    def test_unenrolled_homonym_cannot_satisfy_a_missing_source(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_corpus(root)
            path = root / TERM / "witnessing.md"
            path.write_text(path.read_text().replace(SOURCE_LINK, "missing/witness.md"))
            status, report = self.run_validator(root)
            self.assertEqual(status, 1)
            errors = [row for row in report["diagnostics"] if row["code"] == "broken-link"]
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["path"], f"{TERM}/witnessing.md")
            self.assertIn("missing/witness.md", errors[0]["message"])

    def test_link_diagnostics_identify_source_lines_and_typed_target_reasons(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_corpus(root)
            note = root / TERM / "witnessing.md"
            with note.open("a", encoding="utf-8") as file:
                file.write("\n[Missing](ghost.md#observe)\n[Folder](subdir/folder.md)\n"
                           "[External path](../../../../../outside.md)\n")
            (note.parent / "subdir/folder.md").mkdir(parents=True)
            status, report = self.run_validator(root)
            self.assertEqual(status, 1)
            failures = {row["extra"]["target"]: row for row in report["diagnostics"]
                        if row["code"] == "broken-link"}
            self.assertEqual(set(failures), {"ghost.md#observe", "subdir/folder.md", "../../../../../outside.md"})
            source_lines = note.read_text().splitlines()
            for target, reason, expected in (
                ("ghost.md#observe", "missing", f"{TERM}/ghost.md"),
                ("subdir/folder.md", "not-a-file", f"{TERM}/subdir/folder.md"),
                ("../../../../../outside.md", "outside-root", None),
            ):
                row = failures[target]
                self.assertIn(target, source_lines[row["line"] - 1])
                self.assertEqual(row["extra"]["reason"], reason)
                self.assertEqual(row["extra"]["expected_path"], expected)
            self.assertEqual(failures["ghost.md#observe"]["extra"]["fragment"], "observe")

    def test_opt_in_math_check_reports_native_tex_fallback_not_code_examples(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_corpus(root)
            note = root / TERM / "witnessing.md"
            with note.open("a", encoding="utf-8") as file:
                file.write("\nA formula: $a \\notacommand{b}$.\n\n~~~tex\n"
                           "$\\exampleonly{a}$\n~~~\n")
            self.assertEqual(self.run_validator(root)[0], 0)
            output = StringIO()
            with redirect_stdout(output):
                status = validate(["--root", str(root), "--no-lean", "--format", "json",
                                   "--check-math"])
            self.assertEqual(status, 1)
            reports = json.loads(output.getvalue())["diagnostics"]
            tex = [row for row in reports if row["code"] == "tex-rendering"]
            self.assertEqual(len(tex), 1, reports)
            self.assertEqual(tex[0]["path"], f"{TERM}/witnessing.md")
            self.assertEqual(tex[0]["extra"]["tex"], r"a \notacommand{b}")
