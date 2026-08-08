from __future__ import annotations

from typing import Any

SPACE_MARKER = "__space__"
SUPPORTED_SPACE_TYPES = frozenset({"categorical", "int", "real"})


class SearchSpaceDescriptorError(ValueError):
    pass


def is_search_space_descriptor(value: Any) -> bool:
    return isinstance(value, dict) and SPACE_MARKER in value


def contains_search_space_descriptor(value: Any) -> bool:
    if is_search_space_descriptor(value):
        return True
    if isinstance(value, dict):
        return any(contains_search_space_descriptor(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_search_space_descriptor(item) for item in value)
    return False


def validate_search_space_descriptors(value: Any, *, path: str = "hyperparameters") -> None:
    if is_search_space_descriptor(value):
        _validate_descriptor(value, path=path)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            validate_search_space_descriptors(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            validate_search_space_descriptors(item, path=f"{path}[{index}]")


def _validate_descriptor(descriptor: dict[str, Any], *, path: str) -> None:
    space_type = descriptor.get(SPACE_MARKER)
    if space_type not in SUPPORTED_SPACE_TYPES:
        raise SearchSpaceDescriptorError(
            f"{path}.{SPACE_MARKER} must be one of {sorted(SUPPORTED_SPACE_TYPES)}"
        )

    if space_type == "categorical":
        allowed = {SPACE_MARKER, "choices"}
        unexpected = sorted(set(descriptor) - allowed)
        if unexpected:
            raise SearchSpaceDescriptorError(f"{path} contains unsupported keys: {unexpected}")
        choices = descriptor.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise SearchSpaceDescriptorError(
                f"{path}.choices must be a list containing at least two values"
            )
        return

    allowed = {SPACE_MARKER, "lower", "upper", "default"}
    if space_type == "real":
        allowed.add("log")
    unexpected = sorted(set(descriptor) - allowed)
    if unexpected:
        raise SearchSpaceDescriptorError(f"{path} contains unsupported keys: {unexpected}")

    lower = descriptor.get("lower")
    upper = descriptor.get("upper")
    if space_type == "int":
        if not isinstance(lower, int) or isinstance(lower, bool):
            raise SearchSpaceDescriptorError(f"{path}.lower must be an integer")
        if not isinstance(upper, int) or isinstance(upper, bool):
            raise SearchSpaceDescriptorError(f"{path}.upper must be an integer")
    else:
        if not isinstance(lower, (int, float)) or isinstance(lower, bool):
            raise SearchSpaceDescriptorError(f"{path}.lower must be numeric")
        if not isinstance(upper, (int, float)) or isinstance(upper, bool):
            raise SearchSpaceDescriptorError(f"{path}.upper must be numeric")
        if "log" in descriptor and not isinstance(descriptor["log"], bool):
            raise SearchSpaceDescriptorError(f"{path}.log must be boolean")
    if lower >= upper:
        raise SearchSpaceDescriptorError(f"{path}.lower must be smaller than upper")
    if "default" in descriptor:
        default = descriptor["default"]
        if not isinstance(default, (int, float)) or isinstance(default, bool):
            raise SearchSpaceDescriptorError(f"{path}.default must be numeric")
        if default < lower or default > upper:
            raise SearchSpaceDescriptorError(
                f"{path}.default must be within the inclusive lower/upper bounds"
            )


def materialize_search_spaces(value: Any, *, space_module: Any) -> Any:
    if is_search_space_descriptor(value):
        _validate_descriptor(value, path="hyperparameters")
        space_type = value[SPACE_MARKER]
        if space_type == "categorical":
            return space_module.Categorical(*value["choices"])
        kwargs: dict[str, Any] = {
            "lower": value["lower"],
            "upper": value["upper"],
        }
        if "default" in value:
            kwargs["default"] = value["default"]
        if space_type == "real" and "log" in value:
            kwargs["log"] = value["log"]
        constructor = space_module.Int if space_type == "int" else space_module.Real
        return constructor(**kwargs)
    if isinstance(value, dict):
        return {
            key: materialize_search_spaces(item, space_module=space_module)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [materialize_search_spaces(item, space_module=space_module) for item in value]
    if isinstance(value, tuple):
        return tuple(materialize_search_spaces(item, space_module=space_module) for item in value)
    return value
