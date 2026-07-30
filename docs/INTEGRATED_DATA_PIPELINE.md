# Integrated acquisition, normalization, features, and forecasting

Version 1.1.0 connects the original data/feature responsibilities to the audited forecasting platform.

## Supported acquisition

Configured games: `mini`, `loto6`, `loto7`, `bingo5`, `numbers3`, `numbers4`.

- HTTP CSV download with retries, timeout, User-Agent, SHA-256, ETag and Last-Modified metadata
- Local raw CSV input for offline and fixture testing
- Flexible encodings: UTF-8 BOM, UTF-8, CP932, Shift-JIS and EUC-JP
- Flexible delimiters: comma, tab and semicolon
- Japanese label normalization and number-column inference
- Raw and metadata preservation

## Generated datasets

For every game:

- `normalized_draws`
- `draw_features`
- `occurrence_features` when applicable

For Loto7:

- `canonical_loto7`
- `position_loto7`
- `candidate_loto7`
- `candidate_features_v2`

Output formats are CSV, Parquet when PyArrow is installed, and SQLite. PostgreSQL export is optional.

## Commands

Data only from the configured site:

```powershell
uv run loto data acquire --game loto7 --output .\runs\data-loto7
```

Offline/local raw CSV:

```powershell
uv run loto data acquire --game loto7 --source-file .\input\loto7.csv --output .\runs\data-loto7
```

Complete Loto7 path from acquisition through sealed forecast:

```powershell
uv run loto experiment run-all --game loto7 --output .\runs\full-loto7
```

PostgreSQL export:

```powershell
uv run loto data acquire --game loto7 --output .\runs\data-loto7 `
  --postgres-dsn "postgresql+psycopg://user:password@localhost:5432/loto"
```

## Boundaries

The live downloader is implemented but must be verified against the actual site in the user's environment. Website HTML/CSV changes can require parser updates. Automated scraping must respect the source site's terms and reasonable access frequency.
