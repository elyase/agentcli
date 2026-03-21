from __future__ import annotations

import inspect
from enum import Enum
from typing import Any, Literal, get_origin

from . import prompt as prompt_api
from ._types import CommandSchema, MISSING, ParameterSpec


def wizard_schema(command: CommandSchema) -> dict[str, Any]:
    return {
        "command": command.command,
        "description": command.description,
        "parameters": [
            serialize_parameter(parameter)
            for parameter in command.all_parameters
            if not parameter.hidden
        ],
    }


def prompt_for_parameter(
    parameter: ParameterSpec, *, stdin: Any = None, stdout: Any = None
) -> Any:
    message = parameter.prompt or parameter.description or parameter.name
    if parameter.is_bool:
        default = (
            bool(parameter.default)
            if parameter.has_default and parameter.default is not None
            else False
        )
        return prompt_api.confirm(message, default=default, stdin=stdin, stdout=stdout)
    if parameter.choices:
        return prompt_api.select(
            message,
            parameter.choices,
            default=_default(parameter.default),
            stdin=stdin,
            stdout=stdout,
        )
    if parameter.secret:
        return prompt_api.password(
            message, default=_default(parameter.default), stdin=stdin, stdout=stdout
        )
    if parameter.is_list:
        raw = prompt_api.text(message, default="", stdin=stdin, stdout=stdout)
        return [item.strip() for item in raw.split(",") if item.strip()]
    return prompt_api.text(
        message, default=_default(parameter.default), stdin=stdin, stdout=stdout
    )


def serialize_parameter(parameter: ParameterSpec) -> dict[str, Any]:
    return {
        "name": parameter.name,
        "kind": parameter.kind,
        "flag": None if parameter.kind == "argument" else f"--{parameter.cli_name}",
        "required": parameter.required,
        "description": parameter.description,
        "choices": list(parameter.choices) if parameter.choices else None,
        "default": None
        if parameter.default in (MISSING, inspect.Signature.empty)
        else parameter.default,
        "type": parameter_type(parameter.annotation),
    }


def parameter_type(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is Literal:
        return "literal"
    if origin in (list, tuple):
        return "list"
    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        return "enum"
    return getattr(annotation, "__name__", str(annotation))


def _default(value: Any) -> str | None:
    if value in (None, MISSING, inspect.Signature.empty):
        return None
    return str(value)
