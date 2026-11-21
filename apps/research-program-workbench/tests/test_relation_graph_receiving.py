"""Exercise the same parsed source relations through active Workbench consumers."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from monograph_composer.__main__ import build_composed
from monograph_composer.ordering import assign_chapters
from program_auditor.analysis import crossref_vs_depends_on
from program_auditor.render import render
from program_planner.analysis import out_edges, split_candidates
from program_validator.__main__ import collect
from research_corpus import foundation_distance, load, relation_targets, reverse_depends_on, topo_sort
from research_dagger.ordering import order_corpus


class RelationGraphReceiving(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = self.root / "content" / "notes"
        self.directory.mkdir(parents=True)
        (self.root / "research.toml").write_text(
            '[program]\ntitle = "Graph receiving"\n[corpus]\nlib_dirs = ["content/notes"]\n',
            encoding="utf-8",
        )

    def note(self, slug, fields, body="Evidence."):
        (self.directory / f"{slug}.md").write_text(
            f"---\n{fields}\n---\n{body}\n", encoding="utf-8",
        )

    def test_one_authored_scalar_is_one_edge_for_planner_auditor_and_validator(self):
        self.note("z-foundation", "type: definition\nstatus: draft")
        self.note("a-result", "type: theorem\nstatus: proved\ndepends-on: z-foundation",
                  "Uses the [foundation](z-foundation.md).")
        corpus = load(self.root)
        self.assertFalse(corpus.parse_errors)
        self.assertEqual(out_edges(corpus["a-result"], body_links=False), {"z-foundation"})
        self.assertEqual(reverse_depends_on(corpus.notes), {"z-foundation": ["a-result"]})
        self.assertEqual(foundation_distance(corpus.notes), {"z-foundation": 0, "a-result": 1})
        self.assertEqual(crossref_vs_depends_on(corpus), {})
        finding, = (d for d in collect(corpus, run_lean=False) if d.code == "status-inconsistency")
        self.assertEqual(finding.extra["dep"], "z-foundation")
        self.assertLess(order_corpus(corpus).index("z-foundation"), order_corpus(corpus).index("a-result"))

    def test_dagger_and_composer_use_one_graph_for_scalar_and_repeated_targets(self):
        self.note("z-foundation", "type: definition")
        self.note("a-derived", 'type: definition\ndepends-on: [z-foundation, z-foundation, {ignored: 1}]')
        self.note("part-1", "type: narrative\nchapters: chapter")
        self.note("chapter", "type: narrative\nintroduces: a-derived")
        corpus = load(self.root)
        self.assertFalse(corpus.parse_errors)
        order = order_corpus(corpus)
        self.assertEqual(order.count("z-foundation"), 1)
        self.assertEqual(topo_sort(["z-foundation", "a-derived"], {
            "a-derived": ["z-foundation", "z-foundation"],
        }), ["z-foundation", "a-derived"])
        self.assertLess(order.index("z-foundation"), order.index("a-derived"))
        chapters, names, parts = assign_chapters(order, corpus)
        self.assertEqual(names, ["chapter"])
        self.assertEqual(chapters["chapter"], ["z-foundation", "a-derived"])
        document = build_composed(corpus, order, chapters, names, parts,
                                  title="Graph", subtitle=None, bib_relpath=None)
        self.assertLess(document.index("{#chapter}"), document.index("{#z-foundation}"))
        self.assertLess(document.index("{#z-foundation}"), document.index("{#a-derived}"))
        self.assertEqual(document.count("{#z-foundation}"), 1)
        diagnostics = collect(corpus, run_lean=False)
        self.assertFalse(any(d.code == "orphan" and d.extra["slug"] == "z-foundation" for d in diagnostics))
        self.assertEqual(relation_targets(corpus["a-derived"].fm, "depends-on"), ("z-foundation",))

    def test_planner_counts_targets_not_characters_or_duplicates(self):
        self.note("a-concept", "type: concept\ndepends-on: one-long-target",
                  "\n".join(f"## Section {n}\nEvidence." for n in range(4)))
        corpus = load(self.root)
        self.assertEqual(split_candidates(corpus), [])
        self.assertEqual(relation_targets({"explores": ["a", {}, "", " ", "b", "a"]}, "explores"), ("a", "b"))

    def test_unresolved_source_edge_is_reported_and_cannot_found_a_chain(self):
        self.note("structure", "type: concept\ndepends-on: [foundational-witnesses]")
        self.note("next", "type: theorem\ndepends-on: structure")
        corpus = load(self.root)
        distances = foundation_distance(corpus.notes)
        self.assertEqual(distances, {})
        self.assertIn("`structure` depends on `foundational-witnesses`",
                      render(corpus, {}, {}, {}, distances))

    def test_cycle_and_its_dependents_have_no_finite_foundation_distance(self):
        self.note("root", "type: definition")
        self.note("cyclic", "type: definition\ndepends-on: cyclic")
        self.note("partial", "type: theorem\ndepends-on: [root, cyclic]")
        corpus = load(self.root)
        self.assertEqual(foundation_distance(corpus.notes), {"root": 0})


if __name__ == "__main__":
    unittest.main()
