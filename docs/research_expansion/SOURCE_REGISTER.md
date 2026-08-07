# Source Register

確認日: 2026-08-06

`VERIFIED_FOR_INTAKE`は論文と公式公開先を確認した状態であり、導入revision、全file SHA、dependency、license review完了を意味しない。各PR開始直前に再取得する。

## FlowState

- paper: https://arxiv.org/abs/2508.05287
- official code: https://github.com/ibm-granite/granite-tsfm
- research model: https://huggingface.co/ibm-research/flowstate
- preferred Granite: https://huggingface.co/ibm-granite/granite-timeseries-flowstate-r1
- observed license: Apache-2.0
- architecture: SSM encoder + Functional Basis Decoder
- observed output: q0.1..q0.9
- status: VERIFIED_FOR_INTAKE
- action: resolve revision/tag to commit and hash all files

## TempoPFN

- paper: https://arxiv.org/abs/2510.25502
- official model/code: https://huggingface.co/AutoML-org/TempoPFN
- observed license: Apache-2.0
- published checkpoint: 38M
- architecture: GatedDeltaProduct linear RNN + state-weaving
- pretraining: synthetic
- status: VERIFIED_FOR_INTAKE
- action: loader security and dependency review

## Kairos

- paper: https://arxiv.org/abs/2509.25826
- official code: https://github.com/foundation-model-research/Kairos
- models: mldi-lab/Kairos_10m, Kairos_23m, Kairos_50m
- observed license: Apache-2.0
- architecture: Mixture-of-Size Encoder, Dynamic RoPE, Multi-Patch Decoder
- official example uses remote code
- status: VERIFIED_REMOTE_CODE_REVIEW_REQUIRED

## Reverso

- paper: https://arxiv.org/abs/2602.17634
- official model/code: https://huggingface.co/shinfxh/reverso
- observed license: MIT
- available: Reverso-Small 550K
- not available at check: Reverso 2.6M, Reverso-Nano
- architecture: long convolution + DeltaNet
- status: SMALL_ONLY_VERIFIED_FOR_INTAKE

## Granite PatchTST-FM

- model: https://huggingface.co/ibm-granite/granite-timeseries-patchtst-fm-r1
- code: https://github.com/ibm-granite/granite-tsfm
- observed license: Apache-2.0
- observed weight: model.safetensors approximately 1.03GB
- output documentation: 99 quantile head
- status: VERIFIED_FOR_INTAKE
- action: separate ID from ordinary PatchTST

## LightGTS

- paper: https://arxiv.org/abs/2506.06005
- official model: https://huggingface.co/DecisionIntelligence/LightGTS
- conference: ICML 2025
- architecture: Periodical Tokenization + Periodical Parallel Decoding
- remote code: official example requires it
- license: VERIFY_BEFORE_IMPLEMENTATION
- status: CONDITIONAL

## Super-Linear

- paper: https://arxiv.org/abs/2509.15105
- official code: https://github.com/azencot-group/SuperLinear
- architecture: frequency-specialized linear experts + spectral gate
- checkpoint/license: VERIFY_BEFORE_IMPLEMENTATION
- status: CONDITIONAL

## RAFT

- paper: https://proceedings.mlr.press/v267/han25d.html
- conference: ICML 2025
- method: retrieve similar Train histories and observed futures
- code revision: RECHECK_REQUIRED
- status: METHOD_VERIFIED

## TS-RAG

- paper: https://arxiv.org/abs/2503.07649
- conference: NeurIPS 2025
- official code: https://github.com/UConn-DSIS/TS-RAG
- observed code license: MIT
- method: retriever + TSFM + Adaptive Retrieval Mixer
- status: VERIFIED_FOR_METHOD_INTAKE

## Watchlist

TimeFound、Xihe、YingLong、VisionTS、TimePro、KRNO、additional Mamba/SSM、diffusion/flow、instruction-conditioned ICL。公式weight/license/revision確認前にruntime PRを作らない。

## Policy

PR開始直前にofficial release、commit、model revision、file inventory、SHA、package、license、security advisory、supersessionを再取得する。論文の性能を本プロジェクトの性能として転用しない。
