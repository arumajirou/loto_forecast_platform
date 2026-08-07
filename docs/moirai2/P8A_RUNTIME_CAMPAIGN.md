# P8A Target-Host Runtime Campaign

P8A converts the single-request P8 certifier into a formal target-host matrix. It does not change
Moirai inference, model weights, quantile extraction, or the provider response schema.

## Formal cases

1. `draw-target-only`
2. `draw-past-only`
3. `draw-past-known-future`
4. `calendar-target-only`
5. `calendar-past-only`
6. `calendar-past-known-future`

Every case uses the pinned model identity, revision, snapshot path, seed 1, 128 history rows, context
128, and horizon 1 by default. Calendar fixtures intentionally contain missing days so the existing
calendar expansion and observed-mask path is exercised.

The past-only feature is a normalized historical index. The known-future feature is a normalized
history-plus-horizon step known before prediction. These are runtime probes only; they are not
opened as model-selection features and contain no future actual target values.

## Execution and success

Cases run strictly serially. Each case invokes `certify_moirai2_runtime.py`, so a complete formal
campaign launches twelve independent provider processes. Parallel execution is intentionally absent
to avoid ambiguous GPU PID, UUID, VRAM, and post-exit release evidence.

A campaign is formally certified only when all six cases pass, every case reports two different
provider PIDs, all prediction and artifact identities match, and the requested device remains
consistent. Partial case selection can diagnose a problem but cannot set formal certification true.
