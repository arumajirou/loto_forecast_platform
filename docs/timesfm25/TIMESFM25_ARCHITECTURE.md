# TimesFM 2.5 Architecture

```text
DataFrame -> TimesFM25Adapter -> Request v2 -> isolated uv environment
          -> run_timesfm25_provider.py -> TimesFM native API
          -> Response v2 -> validation -> caller
```

Backend manifests separate checkpoint identity while `algorithm_identity=timesfm-2.5-200m` prevents double counting. The first PR executes only the native PyTorch lane. Source-pinned, Transformers, and XReg entries are represented without claiming runtime success.
