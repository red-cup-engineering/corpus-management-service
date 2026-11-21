import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_corpus import CorpusFile, ProgramConfig, load
from research_corpus.frontmatter import parse_file_with_body_line
from research_corpus.vocabulary import VocabularyError, render


class ExplicitCorpusFiles(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def configure(self, paths, extra=""):
        cfg = '[corpus]\nlib_dirs = ["concepts"]\n'
        for path, kind in paths:
            cfg += "[[corpus.files]]\n"
            cfg += f"path = {json.dumps(path)}\ndefault_kind = {json.dumps(kind)}\n"
        self.write("research.toml", cfg + extra)

    def test_only_enrolled_files_once_with_authored_kind_first(self):
        self.write("concepts/direct.md", "---\ntitle: Direct\n---\n\nDirect body\n")
        self.write("concepts/README.md", "# Unselected index\n")
        self.write("concepts/subdir/unseen.md", "---\ntitle: Unknown nested\n---\nBody\n")
        self.write("notes/2026/01/02/a.md", "---\ntitle: First explicit\n---\n\nExact body\n")
        self.write("notes/2026/01/02/z.md", "---\ntype: question\ntitle: Authored question\n---\nA question\n")
        self.write("notes/2026/01/02/ignored.md", "---\ntitle: Unselected sibling\n---\nBody\n")
        self.write("lib/legacy/a.md", "---\ntitle: Archival namesake\n---\nBody\n")
        self.configure([("notes/2026/01/02/z.md", "note"), ("concepts/direct.md", "note"),
                        ("notes/2026/01/02/a.md", "note"), ("concepts/direct.md", "note")])
        with patch("research_corpus.corpus.parse_file_with_body_line",
                   wraps=parse_file_with_body_line) as parse:
            corpus = load(self.root)
        self.assertEqual([call.args[0].relative_to(self.root).as_posix() for call in parse.call_args_list],
                         ["concepts/direct.md", "notes/2026/01/02/a.md", "notes/2026/01/02/z.md"])
        self.assertEqual(list(corpus.notes), ["direct", "a", "z"])
        self.assertEqual([corpus[s].kind for s in corpus.notes], ["note", "note", "question"])
        self.assertEqual(corpus["a"].dir, "notes/2026/01/02")
        self.assertEqual(corpus["a"].body, "\nExact body\n")
        self.assertEqual(corpus["a"].body_start_line, 4)
        self.assertEqual(corpus.parse_errors, [])
        self.configure([])
        old = load(self.root)
        self.assertEqual(list(old.notes), ["direct"])
        self.assertEqual(old["direct"].kind, "concept")

    def test_bad_declarations_are_not_paths_or_unstated_default_kinds(self):
        for path in ("/outside.md", "../outside.md", "inside/../x.md", "C:/escape.md",
                     "dir//x.md", "./x.md", "dir/./x.md", "dir\\x.md", "dir/.hidden/x.md",
                     ".hidden.md", "dir/README.md", "dir/container", "dir/x.md/", "dir/x\n.md"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "exact nonhidden"):
                CorpusFile(path, "note")
        for kind in ("", " padded ", "label\n", 7):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "default_kind"):
                CorpusFile("note.md", kind)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            ProgramConfig(self.root, files=(CorpusFile("a.md", "note"), CorpusFile("a.md", "question")))
        self.write("research.toml", '[corpus]\nfiles = [{path = "a.md"}]\n')
        with self.assertRaisesRegex(ValueError, "requires exactly"):
            load(self.root)

    def test_nonregular_files_missing_paths_and_symlink_components_are_diagnostics(self):
        self.write("inside/real.md", "---\ntitle: Regular file\n---\n\nBody\n")
        (self.root / "folder.md").mkdir()
        (self.root / "file-link.md").symlink_to("inside/real.md")
        (self.root / "dir-link").symlink_to("inside", target_is_directory=True)
        self.configure([("folder.md", "note"), ("file-link.md", "note"),
                        ("dir-link/real.md", "note"), ("missing.md", "note")])
        with patch("research_corpus.corpus.parse_file_with_body_line") as parse:
            selected = load(self.root)
        parse.assert_not_called()
        self.assertEqual(len(selected), 0)
        self.assertEqual([(d.code, d.path.as_posix(), d.severity) for d in selected.parse_errors], [
            ("corpus-file", p, "error") for p in
            ("dir-link/real.md", "file-link.md", "folder.md", "missing.md")])

    def test_partial_scope_diagnostics_do_not_enroll_or_block_unrelated_vocabulary(self):
        authored = "concepts/exact.md"
        self.write(authored, "---\ntitle: Existing\ndescription: The admitted concept\n---\n\nBody\n")
        self.write("notes/other.md", "---\ntitle: Additional note\ndescription: Not a vocabulary member\n---\nBody\n")
        vocabulary = f'''
[vocabulary]
scheme = "urn:example:scheme:reviewed"
namespace = "urn:example:concept:"
document_base_url = "https://example.invalid/blob/main"
output = "build/ontology.ttl"
members = ["{authored}"]
'''
        self.configure([], vocabulary)
        known = render(load(self.root))
        selected = [("notes/other.md", "note"), ("notes/absent.md", "note")]
        self.configure(selected, vocabulary)
        partial = load(self.root)
        self.assertEqual([d.code for d in partial.parse_errors], ["corpus-file"])
        self.assertIn("other", partial.notes)
        self.assertEqual(render(partial), known)
        self.assertNotIn(b"Additional note", known)

        self.write("notes/exact.md", "---\ntype: note\ntitle: A distinct same-name file\n---\nBody\n")
        self.configure(selected + [("notes/exact.md", "note")], vocabulary)
        conflicted = load(self.root)
        self.assertIn("slug-collision", [d.code for d in conflicted.parse_errors])
        with self.assertRaisesRegex(VocabularyError, "slug-collision"):
            render(conflicted)

    def test_explicit_file_keeps_the_original_type_diagnostics(self):
        self.write("notes/conflict.md", "---\ntype: note\nkind: question\n---\nBody\n")
        self.write("notes/unparseable.md", "No frontmatter\n")
        self.configure([("notes/conflict.md", "note"), ("notes/unparseable.md", "note")])
        self.assertEqual([d.code for d in load(self.root).parse_errors],
                         ["frontmatter-kind", "frontmatter-parse"])
