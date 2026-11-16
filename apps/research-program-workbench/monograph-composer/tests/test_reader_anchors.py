"""Actual Pandoc receiving of note and authored heading anchors."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from monograph_composer.__main__ import main


class ReaderAnchorReceivingTest(unittest.TestCase):
    def compose(self, root: Path, body: str) -> tuple[list[dict], str]:
        notes = root / "concepts"
        notes.mkdir()
        (root / "research.toml").write_text('[corpus]\nlib_dirs = ["concepts"]\n')
        (notes / "carrier.md").write_text("---\nname: Carrier\ntype: concept\n---\n\n" + body)
        (notes / "consumer.md").write_text(
            "---\nname: Consumer\ntype: concept\n---\n\n"
            "See [the carrier](carrier.md#carrier) and [context](carrier.md#details).\n"
        )
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["--root", str(root), "--no-pandoc"]), 0)
        compiled = (root / "tools/build/composed.md").read_text()
        # The same Markdown reader as the exporter, with explicit anchors only.
        parsed = subprocess.run(
            ["pandoc", "--from=markdown-auto_identifiers", "--to=json"],
            input=compiled, text=True, capture_output=True, check=True, timeout=30,
        )
        return json.loads(parsed.stdout)["blocks"], parsed.stderr

    def test_leading_matching_anchor_is_received_once_with_its_authored_title(self):
        with TemporaryDirectory() as tmp:
            blocks, warnings = self.compose(Path(tmp), """
### The `Carrier` construction {#carrier}

Content preserved by composition.

~~~markdown
## Lean example
### Code stays literal {#carrier}
~~~

### Distinct detail {#details}

This section has a distinct address.
""")
        headings = [x["c"] for x in blocks if x["t"] == "Header"]
        by_id = [x for x in headings if x[1][0] == "carrier"]
        self.assertEqual(len(by_id), 1, warnings)
        self.assertEqual(by_id[0][0], 4)
        self.assertTrue(any(x["t"] == "Code" and x["c"][1] == "Carrier" for x in by_id[0][2]))
        self.assertEqual(sum(x[1][0] == "details" for x in headings), 1)
        code = [x["c"][1] for x in blocks if x["t"] == "CodeBlock"]
        self.assertEqual(code, ["## Lean example\n### Code stays literal {#carrier}"])
        links = [x["c"][2][0] for p in blocks if p["t"] == "Para"
                 for x in p["c"] if x["t"] == "Link"]
        self.assertIn("#carrier", links)
        self.assertIn("#details", links)
        self.assertNotIn("Duplicate identifier 'carrier'", warnings)

    def test_differently_anchored_leading_section_is_not_promoted(self):
        with TemporaryDirectory() as tmp:
            blocks, _ = self.compose(Path(tmp), """
### A distinct address {#details}

This title is not the note wrapper.
""")
        headings = {x["c"][1][0]: x["c"][0] for x in blocks if x["t"] == "Header"}
        self.assertEqual(headings["carrier"], 4)
        self.assertEqual(headings["details"], 6)
