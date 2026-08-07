# Handoff

## Current State

```text
DOCUMENTS_CREATED
IMPLEMENTATION_NOT_STARTED
BASE_MAIN=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
FOUNDATION_PRS=120,121,123,124
HOLDOUT=NOT_OPENED
PROSPECTIVE=NOT_OPENED
```

## Recommended Next Action

最初のコードPRは`Research Source Registry`。source/license/revision推測を防ぎ、全candidateを同じ形式で比較し、release変更と重複IDを検出する。

## First Three PRs

1. SRC-01 Research Source Registry
2. BENCH-01 Benchmark Fingerprint and Contamination
3. REVERSO-SMALL-A Source and Contract

Reverso-Smallは小型でCPU/GPU/latency/efficiencyのend-to-end手順を低コストで検証できる。ただし開始直前にsource revision、checkpoint hash、dependencyを再取得する。

## Do Not Start Yet

- Kairos 23/50M before 10M
- unavailable Reverso 2.6M/Nano
- TimeFound/Xihe等のruntime
- TS-RAG before retrieval contract
- online adaptation before chronology contract
- catalog integration before real runtime/OOF
- model専用Runtime Certification SDK

## Review Checklist

- documents only
- no root dependency/workflow/source changes
- no model download/runtime/accuracy claim
- no Holdout/Prospective
- source statusの区別
- #121/#123/#124再利用
- 全metrics/baselines/seeds
- null champion allowed

## Target-host Preparation

disk、cache、isolated env、uv、Python、CUDA/Torch、nvidia-smi、GPU UUID、VRAM、clean checkout、Git commit、reviewed lock、offline snapshot。
