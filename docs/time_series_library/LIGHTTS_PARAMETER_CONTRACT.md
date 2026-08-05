# LightTS parameter and geometry contract

## Pinned implementation

- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`;
- `models/LightTS.py` Git blob: `a2051e44d864ec4ec5e72e59660b98c30c93a902`;
- constructor: `Model(configs, chunk_size=24)`.

## Provider fields

| Provider field | Upstream mapping | Contract |
|---|---|---|
| `seq_len` | `configs.seq_len` | integer, at least 4 |
| `pred_len` | `configs.pred_len` | integer, at least 1 |
| `channels` | `configs.enc_in` | integer, at least 1 |
| `d_model` | `configs.d_model` | at least 16 and divisible by 4 |
| `dropout` | `configs.dropout` | `0 <= dropout < 1` |
| `lightts_chunk_size` | constructor `chunk_size` | integer, at least 1 |
| `lightts_allow_padding` | provider safety gate | explicit opt-in when padding is needed |

## Effective geometry

The upstream model computes:

```text
chunk_size = min(pred_len, seq_len, lightts_chunk_size)
padding_length = (-seq_len) % chunk_size
padded_seq_len = seq_len + padding_length
num_chunks = padded_seq_len // chunk_size
```

Padding is rejected unless `lightts_allow_padding=true`. This prevents an unnoticed
change in temporal geometry. The requested and effective chunk sizes, padded sequence
length, padding length, chunk count, and internal bottleneck widths are persisted in the
checkpoint and compared again before strict reload.

`d_model >= 16` ensures the first nested `d_model // 4 // 4` bottleneck is non-zero.
Divisibility by 4 ensures the concatenated stage-1 and stage-2 width equals the stage-3
input width.

## Certification boundary

The runtime smoke verifies pinned source identity, CPU input/parameter/output devices,
finite values, output shape, state persistence, separate-process strict reload, and
prediction equality. It does not claim accuracy, GPU execution, or exact Torch 2.9.1
isolated-environment success.
