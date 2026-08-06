# GitHub Projects Design

## Fields

Recommended fields remain below the 50-field Project limit:

```text
Status
Experiment ID
Run ID
Game
Execution Lane
Model ID
Protocol Hash
Data Snapshot
Plan Approval
Paid API Approval
Prediction Lock
Actual Status
Evaluation Status
Primary Hit@±1
All-position Hit@±1
MAE
Verdict
API Cost
GPU Hours
Risk
Blocker
Next Gate
Evidence Index URI
```

## Views

- Intake
- Approved and Queued
- Active Local GPU
- Active Local CPU
- Paid API
- Waiting for Actual
- Evaluation Review
- Blocked/Failed
- Campaign Ready
- Cost and Budget

## Automation

Built-in workflows handle only safe projection changes. GitHub App/GraphQL automation updates
fields from verified formal evidence.

## Export

A periodic export retains:

```text
project_id
field IDs and definitions
view inventory
item identities
selected values
exported_at_utc
export_sha256
```

The export is audit evidence, not the experiment source of truth.

## Capability boundary

If Project creation, fields, GraphQL permission, or automation cannot be verified with the connected
account, implementation stops with an owner-action report.
