# SegRNN parameter and geometry contract

## Pinned source

- `models/SegRNN.py`: `afff1bc07dd14d227bbecdd36941d57f8aa8f63e`;
- `layers/Autoformer_EncDec.py`: `6fce4bcd6b3d3eb00e9bcf5931ed2ee301554f4a`.

Both identities are verified before import, construction, fit, or reload. Although
`series_decomp` is not used by the forecast path, the import is required by the pinned
module and its dependency identity is therefore part of certification.

## Request fields

- `seq_len >= 4`;
- `pred_len >= 1`;
- `channels >= 1`;
- `d_model >= 4` through the shared provider schema;
- `d_model` must be even;
- `0 <= dropout < 1`;
- `segrnn_seg_len >= 1`;
- `seq_len % segrnn_seg_len == 0`;
- `pred_len % segrnn_seg_len == 0`.

Invalid geometry is rejected before model import. SegRNN does not pad or truncate
sequences in this lane.

## Persisted geometry

The checkpoint stores and reload validates:

- sequence and prediction lengths;
- channel count;
- `d_model` and half width;
- segment length;
- input and output segment counts;
- decoder token count;
- positional and channel embedding shapes.

Checkpoint geometry is recomputed before strict state-dictionary loading. A modified
geometry record fails closed.

## Runtime certification shape

The formal smoke uses `seq_len=12`, `pred_len=6`, `channels=3`, `d_model=20`, and
`segrnn_seg_len=3`. It produces `[2, 6, 3]` predictions and uses separate fit and load
processes.
