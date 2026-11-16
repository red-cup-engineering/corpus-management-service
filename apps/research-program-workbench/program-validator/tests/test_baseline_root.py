"""Native CLI receiving for before/after research corpus validation."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from program_validator.__main__ import main


class CompareBaselineRootTest(unittest.TestCase):
    def run_comparison(self, current: Path, baseline: Path):
        output = StringIO()
        with redirect_stdout(output):
            status = main(["--root", str(current), "--no-lean", "--format", "json",
                           "--baseline-root", str(baseline)])
        return status, json.loads(output.getvalue())

    def write_terms(self, root: Path, text: str) -> None:
        terms = root / "terms"
        terms.mkdir(parents=True, exist_ok=True)
        (root / "research.toml").write_text('[corpus]\nlib_dirs = ["terms"]\n[validate]\nmin_body_chars = 1\n')
        (terms / "care.md").write_text(
            '---\nname: Care\ntype: term\n---\n\n'
            'Care is the subject of this local receiving fixture.\n\n' + text
        )

    def test_fixed_and_regressed_references_keep_separate_counts(self):
        with TemporaryDirectory() as tmp:
            current, baseline = Path(tmp) / "current", Path(tmp) / "baseline"
            self.write_terms(baseline, "[same](missing.md) [repeated](missing.md) [fix](old.md)")
            self.write_terms(current, "\n\n[same](missing.md) [new](new.md)")
            status, report = self.run_comparison(current, baseline)
            self.assertEqual(status, 1)
            compare = report["baseline"]
            self.assertEqual(len(compare["added"]), 1)
            self.assertIn("new.md", compare["added"][0]["message"])
            self.assertEqual(compare["added"][0]["path"], "terms/care.md")
            self.assertEqual(len(compare["resolved"]), 2)
            self.assertTrue(any("missing.md" in x["message"] for x in compare["resolved"]))

    def test_no_regression_never_turns_existing_hard_diagnostics_green(self):
        with TemporaryDirectory() as tmp:
            current, baseline = Path(tmp) / "current", Path(tmp) / "baseline"
            self.write_terms(baseline, "[same](missing.md)")
            self.write_terms(current, "\n\n[same](missing.md)")
            status, report = self.run_comparison(current, baseline)
            self.assertEqual(status, 1)
            self.assertEqual(report["baseline"]["added"], [])
            self.assertEqual(report["baseline"]["resolved"], [])


if __name__ == "__main__":
    unittest.main()
