"""Real question-recorder to research-workbench receiving tests.

The producer's actual frontmatter and nested Science question path are used.
No test asserts that prose or a graph lookup establishes a theorem or HITS.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from research_corpus import load
from research_corpus.config import load_config
from program_planner.__main__ import main
from program_planner.analysis import open_questions, question_blockers, in_edges_index
from program_planner.focus import focus_recorded_program, focus_recorded_question


class RecordedQuestionFocusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        (self.root / "research.toml").write_text(
            '[corpus]\nlib_dirs = ["questions", "concepts"]\n'
        )
        (self.root / "concepts").mkdir()
        (self.root / "questions").mkdir()
        self.science = (
            self.root / "services" / "semiotics" /
            "content/text/documents/articles/research-articles/questions"
        )
        self.science.mkdir(parents=True)

    def note(self, folder: str, slug: str, frontmatter: str,
             body: str = "A source-held research note.\n") -> Path:
        p = self.root / folder / f"{slug}.md"
        p.write_text(f"---\n{frontmatter}---\n{body}")
        return p

    def question(self, slug: str = "bearing-bonds", *, source: bool = True,
                 explores: str = 'explores: ["semiotic-foam"]\n',
                 status: str = "partially-addressed") -> Path:
        origin = 'source-message: "ni:///sha-256;original-message"\n' if source else ""
        return self.note(
            "services/semiotics/content/text/documents/articles/research-articles/questions",
            slug,
            'date-created: "2026-10-23"\n'
            f'status: "{status}"\n'
            f'title: "Bearing bonds"\n'
            'type: "question"\n'
            + origin + explores,
            "## Question\n\n"
            "What enables an energy-backed commitment by a semiotic cell "
            "toward an attended bearing?\n\n"
            "## Prior observation\n\n"
            "The producer has not attested any proof or installed engine.\n",
        )

    def corpus(self):
        return load(root=self.root, config=load_config(self.root))

    def test_producer_question_preserved_as_original_source_not_theory(self) -> None:
        self.note("concepts", "semiotic-foam",
                  'kind: concept\nstatus: "open"\n')
        original = self.question()
        result = focus_recorded_question(self.corpus(), original)
        self.assertEqual(result["kind"], "program-planner.recorded-question-focus/v1")
        self.assertEqual(result["source"]["sha256"],
                         hashlib.sha256(original.read_bytes()).hexdigest())
        self.assertIn("What enables an energy-backed commitment",
                      result["source"]["question"])
        self.assertIn("## Prior observation", result["source"]["body"])
        self.assertEqual(result["research_program"]["structural_readiness"],
                         "blocked")
        self.assertEqual(
            result["research_program"]["exact_matched_prior_resources"]
            ["semiotic-foam"]["kind"], "concept")
        self.assertEqual(result["receiving"]["whole_structure_received"],
                         "not-assessed")
        self.assertFalse(result["source"]["origin_witness_verified"])

    def test_missing_source_is_unknown_not_attested(self) -> None:
        result = focus_recorded_question(self.corpus(), self.question(source=False))
        self.assertEqual(result["source"]["claimed_origin"], {})
        self.assertFalse(result["source"]["origin_witness_verified"])
        self.assertEqual(result["research_program"]["structural_readiness"],
                         "needs-construction")

    def test_foam_and_uppercase_foam_do_not_merge_by_spelling(self) -> None:
        self.note("concepts", "foam", 'kind: concept\n')
        result = focus_recorded_question(
            self.corpus(), self.question(explores='explores: ["FOAM"]\n'))
        self.assertEqual(result["research_program"]["exact_matched_prior_resources"], {})
        self.assertEqual(result["research_program"]
                         ["unresolved_exact_references"]["explores"], ["FOAM"])

    def test_scalar_explores_is_one_exact_reference(self) -> None:
        self.note("concepts", "semiotic-foam", 'kind: concept\n')
        q = self.note("questions", "question-one",
                      'type: question\nstatus: "partially-addressed"\n'
                      'explores: semiotic-foam\n')
        corpus = self.corpus()
        self.assertIn(q.stem, open_questions(corpus))
        blockers = question_blockers(q.stem, corpus, in_edges_index(corpus))
        self.assertEqual(blockers["loose"], ["semiotic-foam"])
        self.assertEqual(blockers["missing"], [])

    def test_invalid_reference_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "explores"):
            focus_recorded_question(self.corpus(),
                                    self.question(explores='explores: {x: y}\n'))

    def test_slug_collision_cannot_replace_existing_concept(self) -> None:
        self.note("concepts", "bearing-bonds", 'kind: concept\n')
        with self.assertRaisesRegex(ValueError, "slug collision"):
            focus_recorded_question(self.corpus(), self.question())

    def test_not_a_first_class_question_is_refused(self) -> None:
        path = self.note("questions", "bad-record",
                         'type: theorem\ntitle: "Not a question"\n',
                         "## Question\n\nA question-like string.\n")
        with self.assertRaisesRegex(ValueError, "not a first-class"):
            focus_recorded_question(self.corpus(), path)

    def test_resolved_input_preserved_but_not_reopened(self) -> None:
        result = focus_recorded_question(self.corpus(),
                                         self.question(status="resolved"))
        self.assertEqual(result["source"]["status"], "resolved")
        self.assertFalse(result["source"]["active"])

    def test_cli_focus_is_json_stdout_without_report_write(self) -> None:
        question = self.question()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--root", str(self.root),
                         "--question-file", str(question)])
        self.assertEqual(code, 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["source"]["path"], str(question.resolve()))
        self.assertFalse((self.root / "tools/build/research-program.md").exists())

    def test_missing_question_does_not_write_report(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--root", str(self.root),
                         "--question-file", str(self.science / "unrecorded.md")])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertFalse((self.root / "tools/build/research-program.md").exists())

    @unittest.skipUnless(
        os.environ.get("RESEARCH_QUESTION_PRODUCER"),
        "original Red Cup question-recorder source not selected",
    )
    def test_actual_source_recorder_to_planner_handoff(self) -> None:
        """Execute the pinned upstream maker, then this actual consumer."""
        self.note("concepts", "semiotic-foam", 'kind: concept\n')
        record = {
            "root": str(self.root),
            "sectionPath": "services/semiotics",
            "slug": "bearing-bonds",
            "title": "Bearing bonds",
            "question": "Can this cell accept energy under a bearing commitment?",
            "dateCreated": "2026-10-23",
            "status": "partially-addressed",
            "frontmatter": {
                "explores": ["semiotic-foam"],
                "source-message": "ni:///sha-256;source-only-unverified",
            },
        }
        result = subprocess.run(
            ["node", os.environ["RESEARCH_QUESTION_PRODUCER"]],
            input=json.dumps(record), text=True, capture_output=True,
            check=True,
        )
        producer = json.loads(result.stdout)
        self.assertEqual(producer["validation"]["conformant"], True)
        source = self.root / producer["relativePath"]
        focused = focus_recorded_question(self.corpus(), source)
        self.assertEqual(focused["source"]["sha256"],
                         hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(focused["source"]["question"], record["question"])
        self.assertEqual(focused["research_program"]["structural_readiness"],
                         "blocked")
        self.assertFalse(focused["source"]["origin_witness_verified"])
        self.assertEqual(focused["receiving"]["whole_structure_received"],
                         "not-assessed")

    def test_explicit_source_comparison_preserves_new_literal_claim(self) -> None:
        prior = self.question(slug="prior-bearing", status="open")
        before = prior.read_text()
        prior.write_text(before.replace(
            "What enables an energy-backed commitment by a semiotic cell "
            "toward an attended bearing?",
            "Where does a semiotic cell focus attention?",
        ))
        latest = self.question()
        report = focus_recorded_question(self.corpus(), latest, prior)
        diff = report["source_comparison"]
        self.assertEqual(diff["prior_sha256"],
                         hashlib.sha256(prior.read_bytes()).hexdigest())
        self.assertIn("energy-backed", "".join(diff["literal_added_spans"]))
        self.assertTrue(diff["predecessor_selected_by_caller"])
        self.assertFalse(diff["semantic_novelty_assessed"])
        self.assertEqual(report["source"]["question"],
                         "What enables an energy-backed commitment by a semiotic "
                         "cell toward an attended bearing?")

    def test_identical_source_has_no_artificial_change(self) -> None:
        source = self.question()
        output = focus_recorded_question(self.corpus(), source, source)
        diff = output["source_comparison"]
        self.assertEqual(diff["literal_added_spans"], [])
        self.assertEqual(diff["literal_removed_spans"], [])

    def test_missing_explicit_predecessor_refuses_comparison(self) -> None:
        source = self.question()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--root", str(self.root),
                         "--question-file", str(source),
                         "--previous-question-file",
                         str(self.science / "unrecorded.md")])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("source question refused", stderr.getvalue())

    def test_multi_question_original_program_has_shared_blocker(self) -> None:
        self.note("concepts", "semiotic-foam",
                  'kind: concept\nstatus: "open"\n')
        first = self.question(slug="bearing-bonds")
        second = self.question(slug="cell-energy")
        prog = focus_recorded_program(self.corpus(), [first, second])
        self.assertEqual(prog["kind"],
                         "program-planner.recorded-question-program/v1")
        self.assertEqual(prog["source_question_count"], 2)
        self.assertEqual(set(prog["source_questions"]),
                         {"bearing-bonds", "cell-energy"})
        groups = prog["dependency_components"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["question_slugs"],
                         ["bearing-bonds", "cell-energy"])
        self.assertEqual(groups[0]["shared_not_firm_dependencies"],
                         [{"original_reference": "semiotic-foam",
                           "questions": ["bearing-bonds", "cell-energy"]}])
        self.assertEqual(prog["receiving"]["holistic_structure_received"],
                         "not-assessed")

    def test_program_distinguishes_unrelated_and_case_distinct_questions(self) -> None:
        foam = self.question(slug="lowercase-foam", explores='explores: foam\n')
        upper = self.question(slug="uppercase-foam", explores='explores: FOAM\n')
        program = focus_recorded_program(self.corpus(), [upper, foam])
        groups = program["dependency_components"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(len(g["question_slugs"]) == 1 for g in groups))
        self.assertEqual(
            program["source_questions"]["lowercase-foam"]
            ["research_program"]["unresolved_exact_references"]["explores"],
            ["foam"],
        )
        self.assertEqual(
            program["source_questions"]["uppercase-foam"]
            ["research_program"]["unresolved_exact_references"]["explores"],
            ["FOAM"],
        )

    def test_program_refuses_cross_checkout_slug_collision(self) -> None:
        first = self.question()
        second = self.note("questions", "bearing-bonds",
                           'type: question\ntitle: "Same slug"\n',
                           "## Question\n\nDifferent actual origin.\n")
        with self.assertRaisesRegex(ValueError, "slug collision"):
            focus_recorded_program(self.corpus(), [first, second])

    def test_cli_composes_program_from_explicit_sources_without_writes(self) -> None:
        first = self.question(slug="bearing-bonds")
        second = self.question(slug="cell-energy")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--root", str(self.root),
                         "--question-file", str(first),
                         "--question-file", str(second)])
        self.assertEqual(code, 0)
        program = json.loads(out.getvalue())
        self.assertEqual(program["source_question_count"], 2)
        self.assertEqual(program["source_questions"]["bearing-bonds"]
                         ["source"]["sha256"],
                         hashlib.sha256(first.read_bytes()).hexdigest())
        self.assertFalse((self.root / "tools/build/research-program.md").exists())

    @unittest.skipUnless(
        os.environ.get("RESEARCH_QUESTION_PRODUCER"),
        "original Red Cup question recorder source not selected",
    )
    def test_two_original_producer_questions_into_one_program(self) -> None:
        self.note("concepts", "semiotic-foam", 'kind: concept\n')
        paths = []
        for slug in ("bearing-bonds", "cell-energy"):
            record = {
                "root": str(self.root),
                "sectionPath": "services/semiotics",
                "slug": slug,
                "title": slug,
                "question": f"How does the original source qualify {slug}?",
                "dateCreated": "2026-10-23",
                "status": "partially-addressed",
                "frontmatter": {"explores": ["semiotic-foam"]},
            }
            receipt = subprocess.run(
                ["node", os.environ["RESEARCH_QUESTION_PRODUCER"]],
                input=json.dumps(record), text=True, capture_output=True,
                check=True,
            )
            paths.append(self.root / json.loads(receipt.stdout)["relativePath"])
        program = focus_recorded_program(self.corpus(), paths)
        self.assertEqual(program["source_question_count"], 2)
        self.assertEqual(len(program["dependency_components"]), 1)
        self.assertTrue(all(
            value["source"]["origin_witness_verified"] is False
            for value in program["source_questions"].values()
        ))

    def test_original_batch_planner_remains_available(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["--root", str(self.root)])
        self.assertEqual(code, 0)
        report = (self.root / "tools/build/research-program.md").read_text()
        self.assertIn("# Research-program report", report)


if __name__ == "__main__":
    unittest.main()
