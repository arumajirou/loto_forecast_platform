# TAJ-21 Full OOF Evidence Gap Audit

Base: `main@8964c99f57060e735dcaad62df9f3e9642e73bba`

The six-game baseline reference is complete and merged via PR #382. Before the expensive Unified250 × 6 development-only OOF execution, current main still requires the following evidence-completeness work:

- full real-data loader must use `loto.data.parser.parse_file` for canonical CP932 inputs;
- persist fold-level metrics for every successful seed;
- aggregate per-position Hit@±1 across all approved seeds;
- persist explicit prediction-seal-before-actual-read audit evidence;
- emit paired model-vs-baseline comparisons with Holm multiplicity correction;
- emit `ARTIFACT_MANIFEST.json` and `VERIFICATION_REPORT.json`;
- independently verify the full 1,500-row candidate matrix, baseline rows, seed/fold evidence, prediction locks, comparisons, manifests and checksums;
- keep Holdout, Prospective and Promotion closed.

The full 250 × 6 campaign must not be launched before these gates are implemented, because doing so would create incomplete scientific evidence and require a costly rerun.
