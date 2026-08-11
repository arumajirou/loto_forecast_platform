#!/usr/bin/env bash
set -Eeuo pipefail

OWNER="${OWNER:-arumajirou}"
PROJECT="${PROJECT:-1}"
REPO="${REPO:-arumajirou/loto_forecast_platform}"

command -v gh >/dev/null 2>&1 || { echo "ERROR: gh is required" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required" >&2; exit 2; }

gh auth status >/dev/null

echo "=== PROJECT ==="
gh project view "$PROJECT" --owner "$OWNER"

FIELDS_JSON="$(mktemp)"
ITEMS_JSON="$(mktemp)"
trap 'rm -f "$FIELDS_JSON" "$ITEMS_JSON"' EXIT

refresh_fields() {
  gh project field-list "$PROJECT" --owner "$OWNER" --limit 100 --format json > "$FIELDS_JSON"
}

refresh_items() {
  gh project item-list "$PROJECT" --owner "$OWNER" --limit 200 --format json > "$ITEMS_JSON"
}

field_exists() {
  python3 - "$FIELDS_JSON" "$1" <<'PY'
import json, sys
path, name = sys.argv[1:3]
obj = json.load(open(path, encoding="utf-8"))
raise SystemExit(0 if any(f.get("name") == name for f in obj.get("fields", [])) else 1)
PY
}

ensure_single_select_field() {
  local name="$1"
  local options="$2"
  refresh_fields
  if field_exists "$name"; then
    echo "FIELD_EXISTS=$name"
    return
  fi
  echo "CREATE_FIELD=$name"
  gh project field-create "$PROJECT" \
    --owner "$OWNER" \
    --name "$name" \
    --data-type SINGLE_SELECT \
    --single-select-options "$options"
}

ensure_number_field() {
  local name="$1"
  refresh_fields
  if field_exists "$name"; then
    echo "FIELD_EXISTS=$name"
    return
  fi
  echo "CREATE_FIELD=$name"
  gh project field-create "$PROJECT" \
    --owner "$OWNER" \
    --name "$name" \
    --data-type NUMBER
}

ensure_single_select_field \
  "Phase" \
  "Master,Scheduler Certification,Identity Smoke,Broad Runtime,Unified Runtime,Functional Certification,Accuracy Evaluation"
ensure_single_select_field \
  "Evidence Status" \
  "PLANNED,VALIDATION_PENDING,VERIFIED,BLOCKED,FAILED"
ensure_number_field "Execution Units"

refresh_fields

PROJECT_ID="$(
  gh project view "$PROJECT" --owner "$OWNER" --format json |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)"

echo "PROJECT_ID=$PROJECT_ID"

item_url_exists() {
  python3 - "$ITEMS_JSON" "$1" <<'PY'
import json, sys
path, target = sys.argv[1:3]
obj = json.load(open(path, encoding="utf-8"))
for row in obj.get("items", []):
    content = row.get("content") or {}
    if content.get("url") == target:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

ensure_item() {
  local url="$1"
  refresh_items
  if item_url_exists "$url"; then
    echo "ITEM_EXISTS=$url"
  else
    echo "ADD_ITEM=$url"
    gh project item-add "$PROJECT" --owner "$OWNER" --url "$url" >/dev/null
  fi
}

BASE="https://github.com/$REPO"
URL_269="$BASE/issues/269"
URL_264="$BASE/issues/264"
URL_263="$BASE/pull/263"
URL_265="$BASE/issues/265"
URL_266="$BASE/issues/266"

for url in "$URL_269" "$URL_264" "$URL_263" "$URL_265" "$URL_266"; do
  ensure_item "$url"
done

refresh_items

field_id() {
  python3 - "$FIELDS_JSON" "$1" <<'PY'
import json, sys
path, name = sys.argv[1:3]
obj = json.load(open(path, encoding="utf-8"))
for field in obj.get("fields", []):
    if field.get("name") == name:
        print(field["id"])
        raise SystemExit
raise SystemExit(f"field not found: {name}")
PY
}

option_id() {
  python3 - "$FIELDS_JSON" "$1" "$2" <<'PY'
import json, sys
path, field_name, option_name = sys.argv[1:4]
obj = json.load(open(path, encoding="utf-8"))
for field in obj.get("fields", []):
    if field.get("name") != field_name:
        continue
    for option in field.get("options", []):
        if option.get("name") == option_name:
            print(option["id"])
            raise SystemExit
raise SystemExit(f"option not found: {field_name}/{option_name}")
PY
}

item_id_by_url() {
  python3 - "$ITEMS_JSON" "$1" <<'PY'
import json, sys
path, target = sys.argv[1:3]
obj = json.load(open(path, encoding="utf-8"))
matches = []
for row in obj.get("items", []):
    content = row.get("content") or {}
    if content.get("url") == target:
        matches.append(row["id"])
if len(matches) != 1:
    raise SystemExit(f"expected exactly one project item for {target}, got {len(matches)}")
print(matches[0])
PY
}

set_select() {
  local url="$1"
  local field="$2"
  local option="$3"
  gh project item-edit \
    --id "$(item_id_by_url "$url")" \
    --project-id "$PROJECT_ID" \
    --field-id "$(field_id "$field")" \
    --single-select-option-id "$(option_id "$field" "$option")" \
    >/dev/null
  echo "SET $url :: $field=$option"
}

set_number() {
  local url="$1"
  local field="$2"
  local value="$3"
  gh project item-edit \
    --id "$(item_id_by_url "$url")" \
    --project-id "$PROJECT_ID" \
    --field-id "$(field_id "$field")" \
    --number "$value" \
    >/dev/null
  echo "SET $url :: $field=$value"
}

# Built-in workflow status.
set_select "$URL_269" "Status" "In Progress"
set_select "$URL_264" "Status" "In Progress"
set_select "$URL_263" "Status" "In Progress"
set_select "$URL_265" "Status" "Todo"
set_select "$URL_266" "Status" "Todo"

# Verification phase.
set_select "$URL_269" "Phase" "Master"
set_select "$URL_264" "Phase" "Scheduler Certification"
set_select "$URL_263" "Phase" "Scheduler Certification"
set_select "$URL_265" "Phase" "Broad Runtime"
set_select "$URL_266" "Phase" "Unified Runtime"

# Evidence state.
set_select "$URL_269" "Evidence Status" "PLANNED"
set_select "$URL_264" "Evidence Status" "VALIDATION_PENDING"
set_select "$URL_263" "Evidence Status" "VALIDATION_PENDING"
set_select "$URL_265" "Evidence Status" "BLOCKED"
set_select "$URL_266" "Evidence Status" "BLOCKED"

# Current upper-bound execution-unit counts. Live runs must re-derive registry counts.
set_number "$URL_269" "Execution Units" 1500
set_number "$URL_265" "Execution Units" 1044
set_number "$URL_266" "Execution Units" 1500

echo
echo "=== PROJECT ITEMS AFTER SYNC ==="
gh project item-list "$PROJECT" --owner "$OWNER" --limit 200

echo
echo "PROJECT_URL=https://github.com/users/$OWNER/projects/$PROJECT"
echo "STATUS=PROJECT_SYNC_COMPLETE"
