# Research program dependency auditor

The original Python research-corpus parser and program-auditor CLI are recovered intact under the living Red Cup Content Engineering corpus-management owner. This preserves the already implemented typed `research.toml` corpus reader, dependency graph, citations/reference parsing, foundation-distance and cross-reference versus dependency analysis. It does not implement the superseded Lean proof validator or replicate Science knowledge.

From this directory, run `uv run program-auditor --root /path/to/a/research/program` against an existing program declaring `research.toml`. The original CLI also accepts `--out /path/to/report.md`. The command emits its original dependency-audit report at the configured output path.

Source: `emsenn/emsenn-archive-code@3c69d5cf9d3bec484f1dc22067ed9623b1bab7c6`, under `topical/information/561-group/research-tools/research/math/{research-corpus,program-auditor}`. Original package code and pyproject files are byte-preserved; only this two-package workspace root is new. Library/package imports still use the original `research_corpus` and `program_auditor` names. The original archive is not a production owner.
