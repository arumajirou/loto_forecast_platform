# Moirai 2.0 Requirements

1. Pin `uni2ts==2.0.0`, package hashes, model revision, config hash, and weight hash.
2. Permit only `personal_noncommercial_research`; production promotion must fail closed.
3. Support dynamic position counts for Numbers3, Numbers4, MiniLoto, Loto6, and Loto7.
4. Support formal horizons 1, 2, and 5.
5. Retain exactly q0.1 through q0.9 and define q0.5 as the point forecast.
6. Reject non-finite, shape-invalid, or crossing quantiles.
7. Record draw-sequence/calendar-time mapping SHA-256 and token geometry.
8. Reject requested CUDA execution when CPU fallback occurs.
9. Keep Holdout, Prospective, fine-tuning, shared worker, and shared catalog out of this PR.
