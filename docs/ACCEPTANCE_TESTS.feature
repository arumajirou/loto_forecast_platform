# language: ja
機能: 信頼可能なLoto7予測縦切り

  シナリオ: 合法な履歴から封印予測を生成する
    前提 30回以上の合法なLoto7抽選履歴がある
    もし Trusted Vertical Sliceを実行する
    なら 7数字は1から37の範囲で厳密昇順である
    かつ 予測封印の検証が成功する
    かつ Release Bundleが生成される
    かつ 全Stageが追記台帳に記録される

  シナリオ: 不正な抽選結果を拒否する
    前提 同一数字または降順を含む抽選履歴がある
    もし Canonical検証を実行する
    なら 処理はCriticalとして停止する
    かつ 学習Stageへ進まない

  シナリオ: GPU指定なのにGPU証跡がないtrialを失格にする
    前提 GPU必須trialでmodelとbatchがCPU上にある
    もし GPU適格性ゲートを評価する
    なら trialは正式評価対象外になる
