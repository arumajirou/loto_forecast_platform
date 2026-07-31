# Runtime Promotion Gates

Runtime validation proves that a model can execute its lifecycle. It does not make
the model a production candidate. Promotion is tracked as explicit gates:

1. `RUNTIME_PASS`
   - Inputs: catalog hash, data hash, resolved config hash, code fingerprint.
   - Artifacts: lifecycle result, predictions, reload parity, model/provider hash.
2. `SMOKE_BACKTEST_PASS`
   - Inputs: `RUNTIME_PASS` artifact hash, smoke backtest period hash.
   - Artifacts: smoke leaderboard row, metric JSON, holdout period.
3. `FORMAL_BACKTEST_PASS`
   - Inputs: frozen model/provider hash, formal backtest config hash.
   - Artifacts: full metric matrix, calibration report, failure analysis.
4. `PROSPECTIVE_REGISTERED`
   - Inputs: approved model hash, registration timestamp, prediction schedule.
   - Artifacts: prospective registry row, no-lookahead data cutoff.
5. `PROSPECTIVE_EVALUATED`
   - Inputs: prospective predictions, realized draws, evaluation period.
   - Artifacts: prospective metrics, drift report, operational incidents.
6. `DEPLOYMENT_CANDIDATE`
   - Inputs: formal and prospective pass artifacts, approval record.
   - Artifacts: deployment manifest, rollback plan, monitoring contract.
