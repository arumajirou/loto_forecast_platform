# Risk Register

| ID | Risk | P | I | Mitigation / Stop |
|---|---|---:|---:|---|
| R-001 | Draft重複 | H | H | PR/branch/path検索。重複時停止 |
| R-002 | 専用certifier重複 | H | H | #123利用 |
| R-003 | Retrieval leakage | H | C | fold-local index、#124 |
| R-004 | Feature availability leakage | M | C | available_at gate |
| R-005 | Online update leakage | M | C | predict-lock-actual-score-update |
| R-006 | Unpinned revision | H | H | commit/tag/file SHA |
| R-007 | Remote code | M | C | allowlist、offline、human review |
| R-008 | License mismatch | M | C | code/weight license分離 |
| R-009 | 16GB VRAM不足 | M | H | small-first、batch matrix、no fallback |
| R-010 | Package conflict | H | H | isolated uv environment |
| R-011 | Unsafe checkpoint | M | C | safetensors優先、pickle review |
| R-012 | Quantile意味誤表示 | M | H | native inventoryとpoint identity |
| R-013 | Benchmark contamination | M | H | disclosure、fingerprint |
| R-014 | baseline未達 | H | M | null champion、正式no-gain |
| R-015 | CI pre-run failure | H | H | #58監査、exact local evidence |
| R-016 | full pytest cost | M | M | focused first、full last |
| R-017 | stale stacked PR | H | H | latest main、retarget |
| R-018 | artifact tamper | L | C | manifest、hash、independent verify |
| R-019 | actual後prediction | L | C | lock chronology |
| R-020 | runtimeだけでpromotion | M | C | runtime/accuracy分離 |
| R-021 | periodicity overfit | M | H | shuffled/period-destroyed control |
| R-022 | ensemble leakage | M | C | earlier-fold weight fit |
| R-023 | source change/disappear | M | M | immutable snapshot |
| R-024 | catalogをrunnable表示 | H | H | capability states |
| R-025 | Holdout reuse | L | C | one-time approval/seal |
