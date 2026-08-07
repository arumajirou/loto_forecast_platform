# P8C Runtime Evidence Gate

P8C independently verifies the immutable outputs of one supported CPU campaign and one CUDA13
experimental campaign. It does not execute the model and does not accept `campaign_summary.json` as
sufficient evidence by itself.

## Formal inputs

- one `supported-py311` campaign produced with `--device cpu`;
- one `cuda13-experimental` campaign produced with `--device cuda`;
- both campaigns produced by `scripts/run_moirai2_runtime_campaign_p8c.py`;
- both campaigns sealed with the same clean Git source commit and tree.

Each campaign must contain all six formal cases and two provider-process runs per case. The pair
therefore retains 12 formal cases and 24 provider-process evidence records.

## Independent checks

P8C recalculates every `SHA256SUMS` entry and requires the artifact manifest to account for every
file. Extra, missing, duplicate, unsafe, or modified paths fail closed.

For every case it reopens the request, case result, certification, both responses, both run evidence
files, both GPU monitors, logs, and exit codes. It verifies:

- seed 1, local-only snapshot loading, and fixed model revision;
- all nine native quantiles, finite values, equal shapes, and monotonic order;
- point forecast equality with q0.5;
- exact separate-process prediction identity;
- distinct provider PIDs and matching device evidence;
- unchanged model, snapshot, and covariate identity;
- run-evidence hashes against the retained files;
- CUDA PID, one GPU UUID, peak VRAM, and post-exit PID release rederived from monitor samples;
- absence of the CPU provider PID from GPU process samples.

The CPU and CUDA campaigns must use the same source commit, source tree, model revision, model config
SHA-256, and model weight SHA-256. Exact CPU-versus-CUDA prediction equality is retained as evidence
but is not a formal pass requirement because different hardware backends may produce small numerical
differences.

## Implementation structure

The verifier is split into common, manifest, prediction, GPU, case, campaign, and pair modules.
`runtime_evidence_gate.py` remains the stable public facade. This separation keeps each review unit
small without changing the formal verification contract.

## Formal output

`P8C_RUNTIME_EVIDENCE_REPORT.json` sets `p9_oof_gate_open=true` only when both complete campaigns
pass every independent check. The report does not claim accuracy and records OOF, Holdout, and
Prospective as not executed.
