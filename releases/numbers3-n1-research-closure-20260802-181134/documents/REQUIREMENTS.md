# REQUIREMENTS

- 最優先指標はHit@±1。
- Train/Calibration/Holdout/Prospectiveを時間順に分離する。
- 特徴量選択、Scaler、調整はTrain系区間内だけで行う。
- 複数seedの平均・分散・最悪値を保存する。
- 固定値、平均、中央値、直近値、頻度、統計モデルと比較する。
- 実測判明前に予測JSONをSHA-256で固定する。
- Rawデータを上書きしない。
