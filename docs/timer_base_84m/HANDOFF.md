# Handoff

PR-B must first obtain byte-exact upstream files, replace all `UNVERIFIED` digests, complete
human remote-code review, select an exact compatible Torch pin, generate and review `uv.lock`,
and preserve the lock approval evidence. Only then may it add offline checkpoint load and
real runtime certification.

Do not merge PR-A as evidence that Timer loads or predicts. It establishes contracts and
fail-closed boundaries only.
