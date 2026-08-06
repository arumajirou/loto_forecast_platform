from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectIdentity(StrictModel):
    owner: str
    owner_type: Literal["user", "organization"]
    repository: str
    title: str
    visibility: Literal["PRIVATE", "PUBLIC"]
    authority: Literal["governance_only"]


class FieldSpec(StrictModel):
    name: str
    data_type: Literal["TEXT", "SINGLE_SELECT", "DATE", "NUMBER"]
    built_in: bool = False
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_options(self) -> "FieldSpec":
        if self.data_type == "SINGLE_SELECT" and not self.options:
            raise ValueError(f"single-select field {self.name!r} requires options")
        if self.data_type != "SINGLE_SELECT" and self.options:
            raise ValueError(f"non-select field {self.name!r} cannot define options")
        if len(self.options) != len(set(self.options)):
            raise ValueError(f"field {self.name!r} has duplicate options")
        return self


class ViewSpec(StrictModel):
    name: str
    layout: Literal["TABLE", "BOARD", "ROADMAP"]
    filter: str
    group_by: str | None = None


class WorkflowSpec(StrictModel):
    name: str
    mode: Literal["BUILT_IN_UI"]
    event: Literal["AUTO_ADD", "ITEM_ADDED", "ISSUE_CLOSED", "PR_MERGED"]
    repository: str | None = None
    filter: str | None = None
    target_status: str | None = None


class ManualPolicy(StrictModel):
    trigger: str
    action: str
    reason: str


class EvidenceSpec(StrictModel):
    directory: str
    required_files: list[str]


class GovernanceSpec(StrictModel):
    schema_version: Literal[1]
    project: ProjectIdentity
    fields: list[FieldSpec]
    views: list[ViewSpec]
    workflows: list[WorkflowSpec]
    manual_policies: list[ManualPolicy]
    required_views: list[str]
    evidence: EvidenceSpec

    @model_validator(mode="after")
    def validate_governance_contract(self) -> "GovernanceSpec":
        field_names = [field.name for field in self.fields]
        if len(field_names) != len(set(field_names)):
            raise ValueError("field names must be unique")
        view_names = [view.name for view in self.views]
        if len(view_names) != len(set(view_names)):
            raise ValueError("view names must be unique")
        if set(self.required_views) != set(view_names):
            raise ValueError("required_views must exactly match declared views")

        required_fields = {
            "Status",
            "Workstream",
            "Type",
            "Priority",
            "Evidence Status",
            "PR Phase",
            "Provider",
            "Risk",
            "Base SHA",
            "Protocol Hash",
            "Target Release",
        }
        if set(field_names) != required_fields:
            raise ValueError("declared fields do not match the governance contract")

        by_name = {field.name: field for field in self.fields}
        status = by_name["Status"]
        evidence = by_name["Evidence Status"]
        expected_status = {
            "Intake",
            "Spec",
            "Design",
            "Ready",
            "In Progress",
            "Verification",
            "Blocked",
            "Failed",
            "Done",
        }
        expected_evidence = {
            "PROPOSED",
            "EXECUTION_PENDING",
            "EXECUTED",
            "VERIFIED",
            "PARTIALLY_VERIFIED",
            "BLOCKED",
            "FAILED",
        }
        if set(status.options) != expected_status or not status.built_in:
            raise ValueError("Status options or built-in marker do not match policy")
        if set(evidence.options) != expected_evidence:
            raise ValueError("Evidence Status options do not match policy")

        auto_add = [workflow for workflow in self.workflows if workflow.event == "AUTO_ADD"]
        if len(auto_add) != 1:
            raise ValueError("exactly one auto-add workflow is required")
        if auto_add[0].repository != self.project.repository:
            raise ValueError("auto-add repository must match project repository")
        return self


def load_spec(path: Path) -> GovernanceSpec:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GovernanceSpec.model_validate(raw)


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def owner_plan(spec: GovernanceSpec) -> dict[str, object]:
    owner = spec.project.owner
    repository_name = spec.project.repository.split("/", maxsplit=1)[1]
    commands = [
        "gh auth status",
        "gh auth refresh -s project",
        (
            f"gh project create --owner {shell_quote(owner)} "
            f"--title {shell_quote(spec.project.title)} --format json"
        ),
        (
            "gh project link <PROJECT_NUMBER> "
            f"--owner {shell_quote(owner)} --repo {shell_quote(repository_name)}"
        ),
    ]

    for field in spec.fields:
        if field.built_in:
            continue
        command = (
            "gh project field-create <PROJECT_NUMBER> "
            f"--owner {shell_quote(owner)} --name {shell_quote(field.name)} "
            f"--data-type {field.data_type}"
        )
        if field.options:
            options = ",".join(field.options)
            command += f" --single-select-options {shell_quote(options)}"
        commands.append(command)

    user_id_command = f"gh api /users/{shell_quote(owner)} --jq .id"
    view_commands = []
    for view in spec.views:
        payload = json.dumps(
            {
                "name": view.name,
                "layout": view.layout.lower(),
                "filter": view.filter,
            },
            separators=(",", ":"),
        )
        view_commands.append(
            "gh api --method POST "
            "-H 'Accept: application/vnd.github+json' "
            "-H 'X-GitHub-Api-Version: 2026-03-10' "
            "'/users/<USER_ID>/projectsV2/<PROJECT_NUMBER>/views' "
            f"--input - <<'JSON'\n{payload}\nJSON"
        )

    return {
        "status": "OWNER_UI_OR_API_ACTION_REQUIRED",
        "owner": owner,
        "repository": spec.project.repository,
        "project_title": spec.project.title,
        "commands": commands,
        "user_id_command": user_id_command,
        "view_commands": view_commands,
        "ui_required": {
            "status_options": next(
                field.options for field in spec.fields if field.name == "Status"
            ),
            "workflows": [workflow.model_dump() for workflow in spec.workflows],
            "manual_policies": [policy.model_dump() for policy in spec.manual_policies],
        },
    }


def render_markdown(plan: dict[str, object]) -> str:
    lines = [
        "# GitHub Projects Owner Execution Plan",
        "",
        f"Status: `{plan['status']}`",
        "",
        "## CLI prerequisites and project fields",
        "",
        "```bash",
    ]
    lines.extend(str(command) for command in plan["commands"])
    lines.extend(["```", "", "## Resolve user ID", "", "```bash"])
    lines.append(str(plan["user_id_command"]))
    lines.extend(["```", "", "## Create views", ""])
    for command in plan["view_commands"]:
        lines.extend(["```bash", str(command), "```", ""])
    lines.extend(
        [
            "## UI-only configuration",
            "",
            "Edit the built-in Status field options and enable the declared built-in workflows.",
            "Do not claim completion until exports and screenshots are retained.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate GitHub Projects governance policy")
    parser.add_argument("--spec", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    render = subparsers.add_parser("render-owner-plan")
    render.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = load_spec(args.spec)
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "status": "VALID",
                    "schema_version": spec.schema_version,
                    "field_count": len(spec.fields),
                    "view_count": len(spec.views),
                    "workflow_count": len(spec.workflows),
                },
                sort_keys=True,
            )
        )
        return 0

    plan = owner_plan(spec)
    if args.format == "markdown":
        print(render_markdown(plan), end="")
    else:
        print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
