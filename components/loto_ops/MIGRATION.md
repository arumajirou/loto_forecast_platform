# v2から短いディレクトリ名への移行

既存のv2は残したまま、新版を `/mnt/e/env/ts/loto_ops` に配置してください。

```bash
cd /mnt/e/env/ts
unzip -q /mnt/e/env/ts/zips/loto_ops-v3.zip -d /mnt/e/env/ts
cd /mnt/e/env/ts/loto_ops
bash setup_linux.sh
bash install_automation.sh 06:30 8520
```

既存v2の実行データは主に次へ保存されているため、新しい短縮ディレクトリからもそのまま利用できます。

```text
/mnt/e/env/ts/loto_life_feature_pipeline/data
PostgreSQL database: loto
/mnt/e/env/ts/zips
```

v2内の `artifacts`、`runs`、`logs` も移したい場合:

```bash
rsync -a /mnt/e/env/ts/loto_ops_pipeline-fixed-20260729-v2/artifacts/ /mnt/e/env/ts/loto_ops/artifacts/
rsync -a /mnt/e/env/ts/loto_ops_pipeline-fixed-20260729-v2/runs/ /mnt/e/env/ts/loto_ops/runs/
rsync -a /mnt/e/env/ts/loto_ops_pipeline-fixed-20260729-v2/logs/ /mnt/e/env/ts/loto_ops/logs/
```
