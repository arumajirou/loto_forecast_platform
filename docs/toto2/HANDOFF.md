# Handoff

Next gate: generate and review `environments/toto2-4m-py312/uv.lock` on the target host, then add a
real isolated executor that imports the exact Toto packages, loads the pinned local snapshot, and
produces the native `[9,1,S,H]` tensor.

Formal runtime certification must record two distinct provider processes, exact prediction hashes,
model and output device, external GPU PID and UUID, peak VRAM, post-exit release, and
`cpu_fallback=false`. Only after the runtime matrix passes may chronological OOF begin.
