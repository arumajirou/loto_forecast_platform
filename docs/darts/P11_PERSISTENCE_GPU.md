# P11 save/load, checkpoint, and GPU certification

P11 covers one representative contract for each Darts family: Local, Regression,
Torch, Foundation, Ensemble, and Conformal.

Formal success requires the complete lifecycle:

1. fit;
2. predict before save;
3. save;
4. record artifact size and SHA-256;
5. terminate the saving process;
6. load from disk in a different process;
7. predict after load;
8. compare model identity, shape, finite values, and numerical replay.

A same-process pickle roundtrip is insufficient. The evidence must show distinct save
and load PIDs, a terminated save process, disk loading, and no reused object identity.

## Manual and clean save

All six families require manual save/load. Global-capable families also receive a clean
save path. Clean certification requires the loaded artifact not to retain training-series
or covariate state. Local models treat clean-state removal as not applicable because the
base Darts clean operation has no effect for local forecasting models.

## Torch and Foundation paths

Torch-backed models receive independent checks for:

- manual save/load with the companion `.ckpt` weights artifact;
- best checkpoint restore;
- last checkpoint restore;
- `load_weights()` into an initialized model with encoders;
- `map_location=cpu`;
- `map_location=cuda:0`.

Checkpoint certification requires trainer, optimizer, and scheduler state evidence.
Weights certification is not treated as checkpoint-resume certification.

## Device certification

P11 reuses the P7 device gate. GPU success requires CUDA parameter and prediction
devices, GPU PID, VRAM before/peak/after, and CUDA allocated/reserved evidence. A CUDA
request that produces CPU parameters or predictions is retained as
`GPU_REQUESTED_BUT_CPU_FALLBACK` and fails certification.

CPU cross-device loading requires CPU parameters and CPU prediction output. CUDA
cross-device loading requires the complete GPU evidence set.

## Artifact and prediction identity

Every artifact stores size and SHA-256 at save and load time. Any change fails the
artifact-integrity check. Before/after predictions must have identical position and
horizon shape, finite values, and configured `allclose` parity. Model ID, public class,
class path, and parameter-config SHA-256 must also match.

The implementation is a runtime-neutral evidence contract. Real Darts runtime success is
not claimed until the pinned environment executes these paths.
