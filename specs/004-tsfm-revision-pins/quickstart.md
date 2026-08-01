# Quickstart

```bash
uv run loto3 revisions template --output configs/tsfm_revision_pins.json
# Fill revisions only after independently verifying each upstream repository.
uv run loto3 revisions validate --manifest configs/tsfm_revision_pins.json
uv run loto3 revisions report --manifest configs/tsfm_revision_pins.json
uv run loto3 revisions apply --manifest configs/tsfm_revision_pins.json --output runs/pinned_catalog.json
```
