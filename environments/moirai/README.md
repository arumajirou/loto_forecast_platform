# Moirai Provider Environment

Dedicated uv project for running the Salesforce Moirai foundation provider
outside the main application environment.

- Package: `uni2ts`
- Model repo: `Salesforce/moirai-2.0-R-small`
- Runtime API: `Moirai2Module.from_pretrained`; `Moirai2Forecast.create_predictor`
- Dataset boundary: build GluonTS objects inside the subprocess from JSON
  history. Do not pickle or share GluonTS dataset objects from the main process.
- Runtime status: only report `ZERO_SHOT_PASS` after real local weight loading,
  seven-series prediction, finite shape validation, save/load reference, and
  subprocess reload parity.

Generated artifacts such as Hugging Face cache contents, provider request and
response JSON files, stdout/stderr, GPU evidence, and model manifests are not
source artifacts and should not be committed.
