"""Receive a living Science section through the original corpus validator.

The directory shapes are the Relationality section's actual glossary and teaching
paths. Fixture prose exercises source structure; it does not assert research facts.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from research_corpus import find_cross_refs, load
from program_validator.__main__ import main
from program_validator.rules import cross_refs


class SectionCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.terms = "content/text/glossary/terms"
        self.concepts = "content/text/glossary/concepts"
        self.teaching = "content/text/documents/articles/teaching-articles/explanations"
        (self.root / "research.toml").write_text(
            '[corpus]\nlib_dirs = [' + ", ".join(
                json.dumps(p) for p in (self.terms, self.concepts, self.teaching)
            ) + ']\n', encoding="utf-8"
        )

    def note(self, path: str, *, kind: str = "concept", body: str = "",
             frontmatter: str = "") -> Path:
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(
            f"---\ntitle: Test entry\ntype: {kind}\n{frontmatter}---\n"
            f"# Test entry\n\n{body}\n", encoding="utf-8"
        )
        return file

    def check(self):
        return list(cross_refs.check(load(self.root)))

    def cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["--root", str(self.root), "--no-lean", "--format", "json"])
        return status, json.loads(output.getvalue())

    def test_nested_science_paths_resolve_from_the_source_file(self):
        self.note(f"{self.terms}/relating.md", kind="term")
        self.note(f"{self.concepts}/attending.md",
                  body="Read [relating](../terms/relating.md#definition).")
        self.note(f"{self.teaching}/introduction.md", kind="narrative",
                  body="Start with [attending](../../../../glossary/concepts/attending.md).")
        status, report = self.cli()
        self.assertEqual(status, 0, report)
        self.assertEqual(report["total_notes"], 3)
        self.assertEqual(load(self.root)["introduction"].kind, "narrative")

    def test_broken_nested_path_is_a_cli_failure(self):
        self.note(f"{self.teaching}/introduction.md", kind="narrative",
                  body="Read [missing](../../../../glossary/terms/missing.md).")
        status, report = self.cli()
        self.assertEqual(status, 1, report)
        broken = [d for d in report["diagnostics"] if d["code"] == "broken-link"]
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]["extra"]["target"], "../../../../glossary/terms/missing.md")

    def test_same_filename_elsewhere_cannot_satisfy_wrong_path(self):
        self.note(f"{self.terms}/relating.md", kind="term")
        self.note(f"{self.concepts}/attending.md",
                  body="[Wrong](relating.md) and [right](../terms/relating.md).")
        findings = self.check()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].extra["target"], "relating.md")

    def test_existing_unindexed_local_navigation_is_valid(self):
        (self.root / "README.md").write_text("# Relationality\n", encoding="utf-8")
        self.note(f"{self.terms}/relating.md", kind="term",
                  body="[Overview](../../../../README.md).")
        self.assertEqual(self.check(), [])

    def test_external_and_fragment_only_links_are_not_local_file_claims(self):
        self.note(f"{self.terms}/relating.md", kind="term", body=(
            "[Primary source](https://example.org/relating.md) "
            "[Protocol relative](//example.org/relating.md) [Section](#definition)."
        ))
        self.assertEqual(self.check(), [])

    def test_code_examples_images_and_comments_are_not_prose_links(self):
        self.note(f"{self.terms}/relating.md", kind="term", body=(
            "`[inline](missing.md)`\n\n```markdown\n[fenced](missing.md)\n```\n"
            "~~~markdown\n[tilde](missing.md)\n~~~\n"
            "<!-- [comment](missing.md) -->\n"
            "![image](missing.md)\n\\[escaped](missing.md)\n"
        ))
        self.assertEqual(self.check(), [])

    def test_composer_preserves_inline_code_in_link_labels(self):
        from monograph_composer.render import rewrite_links
        from research_corpus import find_markdown_links

        body = "[the `P` predicate](predication.md)"
        self.assertEqual(find_markdown_links(body)[0].text, "the `P` predicate")
        self.assertEqual(rewrite_links(body, {"predication"}),
                         "[the `P` predicate](#predication)")

    def test_literal_comment_opener_in_code_does_not_hide_later_links(self):
        from research_corpus import find_markdown_links

        for body in (
            "Use `<!--` to open a comment.\n\n[Broken](missing.md)",
            "```html\n<!--\n```\n[Broken](missing.md)",
            "<!-- ``` and ` stay in comment -->\n[Broken](missing.md)",
        ):
            with self.subTest(body=body):
                self.assertEqual([link.target for link in find_markdown_links(body)],
                                 ["missing.md"])

    def test_fenced_code_ends_only_at_a_matching_fence(self):
        self.note(f"{self.terms}/relating.md", kind="term", body=(
            "````markdown\n```\n[still code](missing.md)\n````\n"
            "[real link](actually-missing.md)\n"
        ))
        self.assertEqual([d.extra["target"] for d in self.check()],
                         ["actually-missing.md"])

    def test_percent_encoded_relative_path_and_link_title(self):
        self.note(f"{self.terms}/relating-example.md", kind="term")
        self.note(f"{self.concepts}/attending.md", body=(
            '[Example](../terms/relating%2Dexample.md "Relating example").'
        ))
        self.assertEqual(self.check(), [])

    def test_out_of_root_link_is_not_admitted(self):
        self.note(f"{self.terms}/relating.md", kind="term",
                  body="[Other checkout](../../../../../neighbor.md).")
        self.assertEqual([d.code for d in self.check()], ["broken-link"])

    def test_source_relative_link_cannot_follow_a_symlink_outside_root(self):
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "foreign.md"
            target.write_text("External source", encoding="utf-8")
            self.note(f"{self.terms}/relating.md", kind="term",
                      body="[Foreign](foreign.md).")
            (self.root / self.terms / "foreign.md").symlink_to(target)
            self.assertEqual([d.code for d in self.check()], ["broken-link"])

    def test_canonical_type_conflict_cannot_be_silently_reclassified(self):
        self.note(f"{self.concepts}/attending.md", kind="concept",
                  frontmatter="kind: theorem\n")
        status, report = self.cli()
        self.assertEqual(status, 1)
        self.assertIn("frontmatter-kind", [d["code"] for d in report["diagnostics"]])

    def test_invalid_type_is_reported(self):
        self.note(f"{self.concepts}/attending.md", kind="[concept, theorem]")
        status, report = self.cli()
        self.assertEqual(status, 1)
        self.assertIn("frontmatter-kind", [d["code"] for d in report["diagnostics"]])

    def test_legacy_kind_and_default_leaf_type_still_load(self):
        path = self.note(f"{self.terms}/relating.md", kind="term")
        path.write_text("---\nkind: definition\n---\nA definition.\n", encoding="utf-8")
        other = self.note(f"{self.concepts}/attending.md")
        other.write_text("---\ntitle: Attending\n---\nA concept.\n", encoding="utf-8")
        corpus = load(self.root)
        self.assertEqual(corpus["relating"].kind, "definition")
        self.assertEqual(corpus["attending"].kind, "concept")

    def test_unconfigured_legacy_and_subdirectories_are_not_live_corpus(self):
        self.note(f"{self.terms}/relating.md", kind="term")
        self.note("lib/legacy/old.md", kind="theorem")
        self.note(f"{self.terms}/archive/old.md", kind="theorem")
        self.assertEqual(load(self.root).slugs(), {"relating"})

    def test_nested_cross_references_are_available_to_other_consumers(self):
        self.assertEqual(find_cross_refs(
            "[Relating](../../../../glossary/terms/relating.md) "
            "`[example](ignored.md)` [Source](https://example.org/source.md)"
        ), ["relating"])

    def test_same_slug_collision_remains_a_hard_failure(self):
        self.note(f"{self.terms}/relationlessness.md", kind="term")
        self.note(f"{self.concepts}/relationlessness.md", kind="concept")
        status, report = self.cli()
        self.assertEqual(status, 1)
        self.assertIn("slug-collision", [d["code"] for d in report["diagnostics"]])

    def test_graph_and_composer_do_not_confuse_unindexed_homonyms(self):
        from program_planner.analysis import in_edges_index
        from program_auditor.analysis import crossref_vs_depends_on
        from monograph_composer.render import rewrite_links

        self.note(f"{self.terms}/relating.md", kind="term")
        self.note("lib/legacy/relating.md", kind="term")
        body = "[Historical reading](../../../../lib/legacy/relating.md)."
        self.note(f"{self.concepts}/attending.md", body=body)
        corpus = load(self.root)
        self.assertNotIn("relating", in_edges_index(corpus))
        self.assertEqual(crossref_vs_depends_on(corpus), {})
        self.assertEqual(rewrite_links(
            body, corpus.slugs(), source_path=corpus["attending"].path,
            path_slugs=corpus.path_slugs,
        ), body)

    def test_nested_links_reach_planner_and_composed_document(self):
        from program_planner.analysis import in_edges_index
        from monograph_composer.__main__ import main as compose

        self.note(f"{self.terms}/relating.md", kind="term")
        self.note(f"{self.teaching}/introduction.md", kind="narrative",
                  body="Read [relating](../../../../glossary/terms/relating.md).")
        corpus = load(self.root)
        self.assertEqual(in_edges_index(corpus)["relating"], {"introduction"})
        with contextlib.redirect_stdout(io.StringIO()):
            status = compose(["--root", str(self.root), "--no-pandoc"])
        self.assertEqual(status, 0)
        result = (self.root / "tools/build/composed.md").read_text(encoding="utf-8")
        self.assertIn("[relating](#relating)", result)

    def test_auditor_ignores_headings_inside_code_blocks(self):
        from program_auditor.analysis import load_bearing_links

        self.assertEqual(load_bearing_links(
            "```markdown\n## Pretend heading\n[Not prose](absent.md)\n```\n",
            "introduction",
        ), set())

    def test_configured_directory_outside_selected_root_is_refused(self):
        (self.root / "research.toml").write_text(
            '[corpus]\nlib_dirs = ["../outside"]\n', encoding="utf-8"
        )
        status, report = self.cli()
        self.assertEqual(status, 1)
        self.assertIn("corpus-directory", [d["code"] for d in report["diagnostics"]])


if __name__ == "__main__":
    unittest.main()
