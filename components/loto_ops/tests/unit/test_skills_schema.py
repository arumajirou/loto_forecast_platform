"""Schema validation tests for Skill YAML definitions in shared-ai-memory/skills/.

Verifies that all YAML files in /mnt/e/env/ts/shared-ai-memory/skills/ contain
required keys and that their types are valid (e.g., ordered_steps is a list).
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = Path(os.getenv("LOTO_SKILLS_DIR", PROJECT_ROOT / "skills"))

# Required keys for Skill YAML definitions
REQUIRED_KEYS = {
    "name": str,
    "purpose": str,
    "trigger": list,
    "preconditions": list,
    "prohibited_conditions": list,
    "required_tools": list,
    "ordered_steps": list,
    "validation": list,
    "rollback": str,
    "known_failures": list,
    "version": str,
    "evidence": list,
    "success_count": int,
    "failure_count": int,
}


def _load_yaml_file(file_path: Path) -> dict:
    """Load YAML file and return dict."""
    # Use simple YAML parsing since PyYAML may not be installed
    try:
        import yaml

        with open(file_path) as f:
            return yaml.safe_load(f)
    except ImportError:
        # Fallback: simple line-based parsing
        data = {}
        current_key = None
        current_list = None

        with open(file_path) as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                if stripped.startswith("---"):
                    continue
                elif stripped.startswith("- "):
                    if current_key and current_list is not None:
                        current_list.append(stripped[2:].strip())
                elif ":" in stripped and not stripped.startswith(" "):
                    key, _, value = stripped.partition(":")
                    key = key.strip()
                    value = value.strip()

                    if value == "" or value.startswith("["):
                        # Start of a list
                        current_key = key
                        current_list = []
                        if value.startswith("["):
                            # Inline list
                            import re

                            items = re.findall(r'"([^"]*)"', value)
                            current_list.extend(items)
                    else:
                        # String value
                        if current_key is not None and current_list is not None:
                            # End of list
                            data[current_key] = current_list
                            current_key = None
                            current_list = None

                        if ":" in stripped:
                            key, _, value = stripped.partition(":")
                            key = key.strip()
                            value = value.strip()
                            if value:
                                data[key] = value.strip('"')
                            else:
                                current_key = key
                                current_list = []

        # Handle last list
        if current_key and current_list is not None:
            data[current_key] = current_list

        return data


def test_all_yaml_files_exist():
    """Verify that all expected YAML skill files exist."""
    expected_files = [
        "generate_handover.yaml",
        "inspect_recent_logs.yaml",
        "recover_failed_command.yaml",
    ]

    for filename in expected_files:
        file_path = SKILLS_DIR / filename
        assert file_path.exists(), f"Skill YAML file {filename} does not exist at {file_path}"


def test_yaml_schema_validation():
    """Verify that all YAML files in skills/ directory pass schema validation."""
    yaml_files = list(SKILLS_DIR.glob("*.yaml"))

    assert len(yaml_files) > 0, "No YAML files found in skills directory"

    for yaml_file in yaml_files:
        # Load the YAML file
        try:
            import yaml

            with open(yaml_file) as f:
                data = yaml.safe_load(f)
        except ImportError:
            data = _load_yaml_file(yaml_file)

        assert isinstance(data, dict), f"{yaml_file.name}: Root element must be a dict"

        # Check required keys
        for key, expected_type in REQUIRED_KEYS.items():
            assert key in data, f"{yaml_file.name}: Missing required key '{key}'"

            actual_value = data[key]
            assert isinstance(actual_value, expected_type), (
                f"{yaml_file.name}: Key '{key}' expected type {expected_type.__name__}, got {type(actual_value).__name__}"
            )


def test_ordered_steps_is_list():
    """Verify that ordered_steps is always a list of strings."""
    yaml_files = list(SKILLS_DIR.glob("*.yaml"))

    for yaml_file in yaml_files:
        try:
            import yaml

            with open(yaml_file) as f:
                data = yaml.safe_load(f)
        except ImportError:
            data = _load_yaml_file(yaml_file)

        if "ordered_steps" in data:
            steps = data["ordered_steps"]
            assert isinstance(steps, list), f"{yaml_file.name}: ordered_steps must be a list"

            for i, step in enumerate(steps):
                assert isinstance(step, str), (
                    f"{yaml_file.name}: Step {i} must be a string, got {type(step).__name__}"
                )


def test_trigger_is_list():
    """Verify that trigger is always a list of strings."""
    yaml_files = list(SKILLS_DIR.glob("*.yaml"))

    for yaml_file in yaml_files:
        try:
            import yaml

            with open(yaml_file) as f:
                data = yaml.safe_load(f)
        except ImportError:
            data = _load_yaml_file(yaml_file)

        if "trigger" in data:
            triggers = data["trigger"]
            assert isinstance(triggers, list), f"{yaml_file.name}: trigger must be a list"

            for i, trigger in enumerate(triggers):
                assert isinstance(trigger, str), (
                    f"{yaml_file.name}: Trigger {i} must be a string, got {type(trigger).__name__}"
                )


def test_version_format():
    """Verify that version follows semantic versioning format."""
    yaml_files = list(SKILLS_DIR.glob("*.yaml"))

    for yaml_file in yaml_files:
        try:
            import yaml

            with open(yaml_file) as f:
                data = yaml.safe_load(f)
        except ImportError:
            data = _load_yaml_file(yaml_file)

        if "version" in data:
            version = data["version"]
            assert isinstance(version, str), f"{yaml_file.name}: version must be a string"

            # Check semantic versioning format (e.g., "1.0.0")
            import re

            pattern = r"^\d+\.\d+\.\d+$"
            assert re.match(pattern, version), (
                f"{yaml_file.name}: version '{version}' does not match semantic versioning format (X.Y.Z)"
            )


def test_success_failure_counts():
    """Verify that success_count and failure_count are non-negative integers."""
    yaml_files = list(SKILLS_DIR.glob("*.yaml"))

    for yaml_file in yaml_files:
        try:
            import yaml

            with open(yaml_file) as f:
                data = yaml.safe_load(f)
        except ImportError:
            data = _load_yaml_file(yaml_file)

        if "success_count" in data:
            count = data["success_count"]
            assert isinstance(count, int), f"{yaml_file.name}: success_count must be an integer"
            assert count >= 0, f"{yaml_file.name}: success_count must be non-negative"

        if "failure_count" in data:
            count = data["failure_count"]
            assert isinstance(count, int), f"{yaml_file.name}: failure_count must be an integer"
            assert count >= 0, f"{yaml_file.name}: failure_count must be non-negative"


def test_evidence_is_list():
    """Verify that evidence is always a list of strings."""
    yaml_files = list(SKILLS_DIR.glob("*.yaml"))

    for yaml_file in yaml_files:
        try:
            import yaml

            with open(yaml_file) as f:
                data = yaml.safe_load(f)
        except ImportError:
            data = _load_yaml_file(yaml_file)

        if "evidence" in data:
            evidence = data["evidence"]
            assert isinstance(evidence, list), f"{yaml_file.name}: evidence must be a list"

            for i, item in enumerate(evidence):
                assert isinstance(item, str), (
                    f"{yaml_file.name}: Evidence {i} must be a string, got {type(item).__name__}"
                )
