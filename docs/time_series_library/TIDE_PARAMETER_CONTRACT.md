# TiDE parameter and geometry contract

## Pinned source

- `models/TiDE.py`: `0fbb98ea159ec5aa5d7afed83eddaf4c2476eaf1`
- SHA-256: `4ab07dec4ae85f8b7c3062ff7d2fec00be342968d41cf09e48d599d8e40f6143`

The source identity is checked before import, construction, fit, and reload.

## Certified lane

The first TiDE lane deliberately supports only:

- long-term forecast mode;
- `e_layers=1`;
- `tide_d_layers=1`;
- `dropout=0.0`;
- `feature_encode_dim=2` from the pinned constructor default;
- internal zero time-feature tensors only;
- CPU execution.

The pinned source constructs repeated encoder and decoder blocks through Python list
multiplication when either depth exceeds one. That aliases the same module instance
instead of creating independent blocks. The certified lane rejects those depths rather
than silently assigning them normal stacked-layer semantics.

## Frequency dimensions

| Frequency | Feature width |
|---|---:|
| `h` | 4 |
| `t` | 5 |
| `s` | 6 |
| `m` | 1 |
| `a` | 1 |
| `w` | 2 |
| `d` | 3 |
| `b` | 3 |

For sequence length `L`, horizon `H`, channels `C`, hidden width `D`, frequency width
`F`, and temporal decoder width `Q`:

```text
feature_encode_dim = 2
flatten_dim = L + 2 * (L + H)
output shape = [batch, H, C]
```

## Exact parameter formula

A TiDE `ResBlock(input, hidden, output)` with bias enabled contains:

```text
input * hidden + hidden
+ hidden * output + output
+ input * output + output
+ 2 * output
```

The final `2 * output` term is LayerNorm weight and bias.

For the certified one-encoder, one-decoder lane:

```text
feature encoder:
  ResBlock(F, D, 2)

main encoder:
  ResBlock(flatten_dim, D, D)

main decoder:
  ResBlock(D, D, C * H)

temporal decoder:
  ResBlock(C + 2, Q, 1)

residual projection:
  L * H + H
```

The provider sums these terms, validates the instantiated parameter count before fit,
and stores the result in checkpoint geometry. Reload recomputes the full geometry and
rejects any modified checkpoint value before strict state loading.
