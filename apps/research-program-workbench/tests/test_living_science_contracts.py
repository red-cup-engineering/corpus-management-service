"""Acceptance tests derived from specifications/living-science-receiving.md."""
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

LESSONS = "content/text/documents/articles/teaching-articles/explanations"
SOURCES = "content/text/documents/articles/bibliographies/references"
ARCHIVE = "lib/legacy/readings"
READER = "build/reader.md"
BIB = "evidence/selected.bib"


class ReaderIndex(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = []
        self.hrefs = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])


class LivingScienceContracts(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "section"
        self.root.mkdir()
        self.write("research.toml", f"""
[program]
title = 'Evidence: a living reader'
[corpus]
lib_dirs = ["{LESSONS}", "{SOURCES}"]
bib = "{BIB}"
[validate]
min_body_chars = 1
[compose]
output = "{READER}"
require_resolved_citations = true
""")
        self.write(f"{LESSONS}/method.md", """---
type: narrative
title: Method and evidence
position: chapter
---

# Method and evidence

Read the [field observation](../../bibliographies/references/observation.md).
""")
        self.write(f"{SOURCES}/observation.md", """---
type: reference
title: Field observation
---

# Field observation

## Measurement limits

The original observer did not measure direction.
""")
        self.write(f"{ARCHIVE}/observation.md", """---
type: reference
title: Superseded archive
---

An archival namesake is not the live source.
""")

    def write(self, path, value):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def run_cli(self, module, *args):
        return subprocess.run([sys.executable, "-m", module, "--root", str(self.root), *args],
                              capture_output=True, text=True, timeout=30)

    def test_ls1_literal_target_and_diagnostic_scope(self):
        lesson = self.root / LESSONS / "method.md"
        good = lesson.read_text(encoding="utf-8")
        lesson.write_text(good.replace("/references/observation.md", "/references/wrong/observation.md"),
                          encoding="utf-8")
        original = self.run_cli("program_validator", "--no-lean", "--format", "json")
        self.assertEqual(original.returncode, 1, original.stderr)
        findings = json.loads(original.stdout)
        self.assertEqual(findings["total_notes"], 2)
        broken, = [d for d in findings["diagnostics"] if d["code"] == "broken-link"]
        self.assertIn("/wrong/observation.md", broken["message"])
        self.assertEqual(broken["path"], f"{LESSONS}/method.md")
        baseline = self.root.parent / "baseline"
        shutil.copytree(self.root, baseline)
        lesson.write_text(good, encoding="utf-8")
        received = self.run_cli("program_validator", "--no-lean", "--format", "json",
                                "--baseline-root", str(baseline))
        comparison = json.loads(received.stdout)
        self.assertEqual(comparison["baseline"]["scope"],
                         {"different_inputs": [], "added_note_paths": [], "removed_note_paths": []})
        self.assertIn("broken-link", [d["code"] for d in comparison["baseline"]["resolved"]])
        self.assertFalse(any(d["code"] == "broken-link" for d in comparison["diagnostics"]))
        lesson.unlink()
        reduced = self.run_cli("program_validator", "--no-lean", "--format", "json",
                               "--baseline-root", str(baseline))
        self.assertEqual(json.loads(reduced.stdout)["baseline"]["scope"]["removed_note_paths"],
                         [f"{LESSONS}/method.md"])

    def test_explicit_note_enrollment_is_compared_as_scope_and_missing_is_hard(self):
        baseline = self.root.parent / "baseline"
        path = "content/text/documents/articles/notes/2026/02/03/selected.md"
        self.write(path, "---\ntitle: Selected note\n---\n\nAn explicitly enrolled source.\n")
        self.write("content/text/documents/articles/notes/2026/02/03/unselected.md",
                   "---\ntitle: Not in this corpus\n---\n\nSource from another scope.\n")
        config = self.root / "research.toml"
        with config.open("a", encoding="utf-8") as target:
            target.write(f'\n[[corpus.files]]\npath = "{path}"\ndefault_kind = "note"\n')
        shutil.copytree(self.root, baseline)
        config.write_text(config.read_text(encoding="utf-8").replace('default_kind = "note"',
                                                                     'default_kind = "narrative"'),
                          encoding="utf-8")
        result = self.run_cli("program_validator", "--no-lean", "--format", "json",
                              "--baseline-root", str(baseline))
        wire = json.loads(result.stdout)
        self.assertEqual(wire["total_notes"], 3)
        self.assertEqual(wire["baseline"]["scope"], {
            "different_inputs": ["files"], "added_note_paths": [], "removed_note_paths": []})
        (self.root / path).unlink()
        missing = self.run_cli("program_validator", "--no-lean", "--format", "json",
                               "--baseline-root", str(baseline))
        self.assertEqual(missing.returncode, 1, missing.stderr)
        wire = json.loads(missing.stdout)
        self.assertEqual(wire["baseline"]["scope"]["removed_note_paths"], [path])
        self.assertEqual([d["path"] for d in wire["diagnostics"] if d["code"] == "corpus-file"], [path])

    def test_ls2_native_reader_receives_nested_source_note(self):
        result = self.run_cli("monograph_composer")
        self.assertEqual(result.returncode, 0, result.stderr)
        html = subprocess.run(["pandoc", "-f", "commonmark_x-gfm_auto_identifiers", "-t", "html",
                               str(self.root / READER)], capture_output=True, text=True,
                              timeout=15, check=True).stdout
        markup = ReaderIndex(html)
        self.assertEqual(markup.ids.count("observation"), 1)
        self.assertIn("#observation", markup.hrefs)
        self.assertIn("The original observer did not measure direction.", html)
        self.assertNotIn("An archival namesake", html)
        manifest = (self.root / "tools/build/manifest.txt").read_text(encoding="utf-8")
        self.assertEqual([line for line in manifest.splitlines() if line.startswith("R ")],
                         [f"R {SOURCES}/observation\treference"])

    def test_ls3_failed_citeproc_preserves_previously_received_outputs(self):
        lesson = self.root / LESSONS / "method.md"
        with lesson.open("a", encoding="utf-8") as target:
            target.write("\nThe methods are discussed in [@Measure-2020].\n"
                         "\n```text\n[@example-not-evidence]\n```\n")
        evidence = "@book{Measure-2020, author={Lee, Mia}, title={Field Methods}, year={2020}}\n"
        self.write(BIB, evidence)
        self.write("references.bib", evidence)
        received = self.run_cli("monograph_composer")
        self.assertEqual(received.returncode, 0, received.stderr)
        artifacts = [self.root / path for path in
                     (READER, "tools/build/composed.md", "tools/build/manifest.txt")]
        before = [p.read_bytes() for p in artifacts]
        self.assertIn(b"Field Methods", before[0])
        self.write(BIB, evidence.replace("Measure-2020", "Other-2020"))
        refused = self.run_cli("monograph_composer")
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("unresolved citation: Measure-2020", refused.stderr)
        self.assertNotIn("unresolved citation: example-not-evidence", refused.stderr)
        self.assertEqual([p.read_bytes() for p in artifacts], before)

    def test_ls4_reviewed_vocabulary_check_and_failed_output_custody(self):
        config = self.root / "research.toml"
        with config.open("a", encoding="utf-8") as file:
            file.write(f"""
[vocabulary]
scheme = "urn:example:scheme:reviewed"
namespace = "urn:example:concept:"
document_base_url = "https://example.invalid/blob/main"
output = "records/vocabulary.ttl"
members = ["{SOURCES}/observation.md"]
""")
        source = self.root / SOURCES / "observation.md"
        text = source.read_text(encoding="utf-8")
        with_summary = text.replace("title: Field observation",
                                    "title: Field observation\ndescription: This observation describes documented limits.")
        source.write_text(with_summary, encoding="utf-8")
        ready = self.run_cli("research_corpus.vocabulary")
        self.assertEqual(ready.returncode, 0, ready.stderr)
        output = self.root / "records/vocabulary.ttl"
        baseline = output.read_bytes()
        self.assertIn(b"urn:example:concept:observation", baseline)
        self.assertNotIn(b"Superseded archive", baseline)
        self.assertEqual(self.run_cli("research_corpus.vocabulary", "--check").returncode, 0)
        source.write_text(with_summary.replace("documented limits", "observed limits"), encoding="utf-8")
        self.assertEqual(self.run_cli("research_corpus.vocabulary", "--check").returncode, 1)
        self.assertEqual(output.read_bytes(), baseline)
        bad = with_summary.replace("title: Field observation", "title: Field observation\nsources: ['a note, not an IRI']")
        source.write_text(bad, encoding="utf-8")
        self.assertEqual(self.run_cli("research_corpus.vocabulary").returncode, 2)
        self.assertEqual(output.read_bytes(), baseline)


if __name__ == "__main__":
    unittest.main()
