"""Native recorder and planner receiving contract, from the living-science spec."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class QuestionProducerReceiving(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.corpus = self.root / "workbench"
        (self.corpus / "concepts").mkdir(parents=True)
        (self.corpus / "research.toml").write_text(
            '[program]\ntitle = "Fixture"\n[corpus]\nlib_dirs = ["concepts"]\n',
            encoding="utf-8",
        )
        (self.corpus / "concepts/foam.md").write_text(
            "---\ntitle: foam\ntype: concept\nstatus: established\n---\n\nAn enrolled resource.\n",
            encoding="utf-8",
        )
        self.producer = Path(os.environ["RESEARCH_QUESTION_PRODUCER"]).resolve(strict=True)

    def command(self, args, **kwargs):
        return subprocess.run(args, cwd=self.root, capture_output=True, text=True,
                              timeout=20, check=False, **kwargs)

    def write(self, slug, question, *, status="open", frontmatter=None):
        request = {
            "root": str(self.root), "sectionPath": "science", "slug": slug,
            "title": slug, "question": question, "dateCreated": "2026-11-20",
            "status": status, "research": "Keep this original supporting paragraph.",
            "frontmatter": frontmatter or {},
        }
        return self.command(["node", str(self.producer)], input=json.dumps(request))

    def record(self, slug, question, **options):
        result = self.write(slug, question, **options)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        relative = f"science/content/text/documents/articles/research-articles/questions/{slug}.md"
        self.assertEqual(receipt["relativePath"], relative)
        self.assertTrue(receipt["receipt"]["created"])
        self.assertTrue(receipt["validation"]["conformant"])
        return self.root / relative

    def plan(self, *questions, previous=None):
        args = [sys.executable, "-m", "program_planner", "--root", str(self.corpus)]
        for q in questions:
            args.extend(["--question-file", str(q)])
        if previous is not None:
            args.extend(["--previous-question-file", str(previous)])
        return self.command(args)

    def tree_bytes(self):
        return {p.relative_to(self.root): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def test_single_source_receives_original_bytes_and_exact_references(self):
        question = "Does observed foam preserve the witness?"
        path = self.record("preserve-witness", question, frontmatter={
            "explores": ["foam", "FOAM"], "source-message": "urn:fixture:message:1",
        })
        before = self.tree_bytes()
        result = self.plan(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["kind"], "program-planner.recorded-question-focus/v1")
        source = report["source"]
        self.assertEqual(source["path"], str(path))
        self.assertEqual(source["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(source["question"], question + "\n\nKeep this original supporting paragraph.")
        self.assertIn("Keep this original supporting paragraph.", source["body"])
        self.assertEqual(source["claimed_origin"], {"source-message": "urn:fixture:message:1"})
        self.assertFalse(source["origin_witness_verified"])
        joined = report["research_program"]
        self.assertEqual(set(joined["exact_matched_prior_resources"]), {"foam"})
        self.assertEqual(joined["unresolved_exact_references"], {"explores": ["FOAM"]})
        self.assertEqual(joined["structural_readiness"], "needs-construction")
        self.assertEqual(set(report["receiving"].values()), {"not-assessed"})
        self.assertEqual(self.tree_bytes(), before)

    def test_selected_program_groups_only_original_active_questions_by_exact_blocker(self):
        a = self.record("first", "Can the first witness settle?", frontmatter={"explores": ["missing"]})
        b = self.record("second", "Can the second witness settle?", frontmatter={"explores": ["missing"]})
        c = self.record("resolved", "Was the older question settled?", status="resolved",
                        frontmatter={"explores": ["missing"]})
        self.record("unselected", "Another question is not part of this program.",
                    frontmatter={"explores": ["missing"]})
        before = self.tree_bytes()
        result = self.plan(a, b, c)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["kind"], "program-planner.recorded-question-program/v1")
        self.assertEqual(set(report["source_questions"]), {"first", "second", "resolved"})
        self.assertFalse(report["source_questions"]["resolved"]["source"]["active"])
        self.assertEqual(report["dependency_components"], [{
            "question_slugs": ["first", "second"],
            "shared_not_firm_dependencies": [{"original_reference": "missing", "questions": ["first", "second"]}],
        }])
        self.assertEqual(set(report["receiving"].values()), {"not-assessed"})
        self.assertEqual(self.tree_bytes(), before)

    def test_explicit_predecessor_reports_literal_change_not_novelty(self):
        prior = self.record("prior", "Can foam settle?")
        current = self.record("current", "Can signed foam settle?")
        result = self.plan(current, previous=prior)
        self.assertEqual(result.returncode, 0, result.stderr)
        comparison = json.loads(result.stdout)["source_comparison"]
        self.assertEqual(comparison["prior_sha256"], hashlib.sha256(prior.read_bytes()).hexdigest())
        self.assertEqual(comparison["literal_added_spans"], ["signed"])
        self.assertTrue(comparison["predecessor_selected_by_caller"])
        self.assertFalse(comparison["semantic_novelty_assessed"])

    def test_create_only_and_refusal_preserve_existing_source(self):
        original = self.record("original", "May this question be recorded once?")
        invalid = self.record("malformed", "Does an invalid relation get invented?",
                              frontmatter={"explores": [17]})
        before = self.tree_bytes()
        self.assertNotEqual(self.write("original", "Overwriting is not allowed.").returncode, 0)
        for result, reason in (
            (self.plan(original, original), "duplicate source question"),
            (self.plan(original, previous=self.root / "absent.md"), "source question refused"),
            (self.plan(invalid), "non-string reference"),
        ):
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(reason, result.stderr)
            self.assertEqual(result.stdout, "")
        self.assertEqual(self.tree_bytes(), before)


if __name__ == "__main__":
    unittest.main()
