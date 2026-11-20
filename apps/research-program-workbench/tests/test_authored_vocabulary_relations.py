from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_corpus.config import load_config
from research_corpus.corpus import load
from research_corpus.vocabulary import main, project_authored_relations, render


class AuthoredRelations(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "concepts").mkdir()
        self.config = self.root / "research.toml"
        self.config.write_text("""
[program]
title = "One vocabulary"
[corpus]
lib_dirs = ["concepts"]
[vocabulary]
scheme = "urn:test:scheme:vocabulary"
namespace = "urn:test:concept:"
document_base_url = "https://example.invalid/blob/main/"
output = "data/ontology.ttl"
members = ["concepts/act.md", "concepts/diagram.md"]
""")
        self.policy = '\n[vocabulary.authored_relations]\ncodomain-concept = "urn:test:predicate:codomain"\n'
        self.act = self.root / "concepts" / "act.md"
        self.diagram = self.root / "concepts" / "diagram.md"
        self.act.write_text("---\nname: Act\ndescription: Describes a witnessed act.\nvisibility: public\n"
                            "codomain-concept: diagram\n---\n\nSee [Diagram](diagram.md).\n")
        self.diagram.write_text("---\nname: Diagram\ndescription: Describes the diagram.\n---\n\nNot an act.\n")

    def configure(self):
        self.config.write_text(self.config.read_text() + self.policy)

    def source_json(self, audience="authenticated"):
        return project_authored_relations(load(config=load_config(self.root)), audience=audience)

    def cli(self, *args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_owner_declared_assertion_and_unchanged_reviewed_turtle(self):
        before = render(load(config=load_config(self.root)))
        self.configure()
        self.assertEqual(render(load(config=load_config(self.root))), before)
        code, output, _ = self.cli("--authored-relations", "--audience", "authenticated")
        self.assertEqual(code, 0)
        row, = json.loads(output)["assertions"]
        self.assertEqual(row, {
            "subject": "urn:test:concept:act", "predicate": "urn:test:predicate:codomain",
            "object": "urn:test:concept:diagram", "source": "https://example.invalid/blob/main/concepts/act.md",
            "targetSource": "https://example.invalid/blob/main/concepts/diagram.md",
            "field": "codomain-concept", "rawValue": "diagram",
        })
        self.assertFalse((self.root / "data").exists())

    def test_markdown_link_without_frontmatter_does_not_assert(self):
        self.configure()
        self.act.write_text(self.act.read_text().replace("codomain-concept: diagram\n", ""))
        self.assertEqual(self.source_json()["assertions"], [])
        self.assertEqual(self.source_json()["unresolved"], [])

    def test_neither_alias_nor_audience_boundary_is_promoted(self):
        self.configure()
        _, _, err = self.cli("--authored-relations")
        self.assertIn("explicit public or authenticated", err)
        report = self.source_json(audience="public")
        self.assertEqual(report["assertions"], [])
        self.assertEqual(len(report["unresolved"]), 1)
        self.assertNotIn("diagram", str(report))
        self.diagram.write_text(self.diagram.read_text().replace("---\n\n", "consent-status: hold\n---\n\n"))
        self.assertEqual(self.source_json()["assertions"], [])
        self.act.write_text(self.act.read_text().replace("codomain-concept: diagram", "codomain-concept: The Diagram"))
        code, output, _ = self.cli("--authored-relations", "--audience", "authenticated")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)["assertions"], [])

    def test_no_projection_without_owner_policy(self):
        code, output, err = self.cli("--authored-relations", "--audience", "authenticated")
        self.assertEqual((code, output), (2, ""))
        self.assertIn("must explicitly select fields", err)


if __name__ == "__main__":
    unittest.main()
