from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, get_args, get_origin

from ._errors import AgentCliError, ParseError, ValidationError, suggest_matches
from ._types import BuiltinFlags, CommandSchema, MISSING, ParameterSpec


@dataclass(frozen=True)
class ParsedCommand:
    values: dict[str, Any]


def extract_builtins(argv: list[str]) -> tuple[BuiltinFlags, list[str]]:
    flags = BuiltinFlags()
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--format":
            if index + 1 >= len(argv):
                raise ParseError("Missing value for --format", code="MISSING_OPTION")
            flags = BuiltinFlags(
                format=argv[index + 1],
                verbose=flags.verbose,
                help=flags.help,
                version=flags.version,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 2
            continue
        if token.startswith("--format="):
            flags = BuiltinFlags(
                format=token.split("=", 1)[1],
                verbose=flags.verbose,
                help=flags.help,
                version=flags.version,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token == "--json":
            flags = BuiltinFlags(
                format="json",
                verbose=flags.verbose,
                help=flags.help,
                version=flags.version,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token == "--verbose":
            flags = BuiltinFlags(
                format=flags.format,
                verbose=True,
                help=flags.help,
                version=flags.version,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token in {"--help", "-h"}:
            flags = BuiltinFlags(
                format=flags.format,
                verbose=flags.verbose,
                help=True,
                version=flags.version,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token == "--version":
            flags = BuiltinFlags(
                format=flags.format,
                verbose=flags.verbose,
                help=flags.help,
                version=True,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token == "--llms":
            flags = BuiltinFlags(
                format=flags.format,
                verbose=flags.verbose,
                help=flags.help,
                version=flags.version,
                llms=True,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token == "--llms-full":
            flags = BuiltinFlags(
                format=flags.format,
                verbose=flags.verbose,
                help=flags.help,
                version=flags.version,
                llms=flags.llms,
                llms_full=True,
                mcp=flags.mcp,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token == "--mcp":
            flags = BuiltinFlags(
                format=flags.format,
                verbose=flags.verbose,
                help=flags.help,
                version=flags.version,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=True,
                wizard=flags.wizard,
            )
            index += 1
            continue
        if token == "--wizard":
            flags = BuiltinFlags(
                format=flags.format,
                verbose=flags.verbose,
                help=flags.help,
                version=flags.version,
                llms=flags.llms,
                llms_full=flags.llms_full,
                mcp=flags.mcp,
                wizard=True,
            )
            index += 1
            continue
        remaining.append(token)
        index += 1
    return flags, remaining


def parse_command(
    schema: CommandSchema,
    argv: list[str],
    *,
    env: Mapping[str, str] | None = None,
    is_tty: bool,
    resolve_prompt_value: Callable[..., Any] | None = None,
) -> ParsedCommand:
    env_map = env or {}
    option_by_name = {spec.cli_name: spec for spec in schema.options}
    option_by_alias = {spec.alias: spec for spec in schema.options if spec.alias}
    raw_values: dict[str, Any] = {}
    positionals: list[str] = []
    index = 0
    literal_mode = False

    while index < len(argv):
        token = argv[index]
        if literal_mode:
            positionals.append(token)
            index += 1
            continue
        if token == "--":
            literal_mode = True
            index += 1
            continue
        if token.startswith("--"):
            name, has_inline, inline_value = token[2:].partition("=")
            negate = False
            if name.startswith("no-"):
                name = name[3:]
                negate = True
            spec = option_by_name.get(name)
            if spec is None:
                suggestions = suggest_matches(name, option_by_name)
                hint = (
                    f" Did you mean: {', '.join(f'--{item}' for item in suggestions)}?"
                    if suggestions
                    else ""
                )
                raise ParseError(f'Unknown option "--{name}".{hint}', code="UNKNOWN_OPTION")
            if negate:
                if not spec.is_bool:
                    raise ParseError(
                        f'Option "--{name}" does not support --no- form',
                        code="UNKNOWN_OPTION",
                    )
                raw_values[spec.name] = False
                index += 1
                continue
            if spec.is_bool and not has_inline:
                raw_values[spec.name] = True
                index += 1
                continue
            value = inline_value if has_inline else _next_value(argv, index, f"--{name}")
            _store_value(raw_values, spec, coerce_value(spec, value))
            index += 1 if has_inline else 2
            continue
        if token.startswith("-") and token != "-":
            short = token[1:]
            if "=" in short:
                alias, value = short.split("=", 1)
                spec = option_by_alias.get(alias)
                if spec is None:
                    raise ParseError(f'Unknown option "-{alias}"', code="UNKNOWN_OPTION")
                _store_value(raw_values, spec, coerce_value(spec, value))
                index += 1
                continue
            if len(short) > 1 and all(
                option_by_alias.get(char) and option_by_alias[char].is_bool
                for char in short
            ):
                for char in short:
                    raw_values[option_by_alias[char].name] = True
                index += 1
                continue
            spec = option_by_alias.get(short)
            if spec is None:
                raise ParseError(f'Unknown option "-{short}"', code="UNKNOWN_OPTION")
            if spec.is_bool:
                raw_values[spec.name] = True
                index += 1
                continue
            value = _next_value(argv, index, f"-{short}")
            _store_value(raw_values, spec, coerce_value(spec, value))
            index += 2
            continue
        positionals.append(token)
        index += 1

    if len(positionals) > len(schema.arguments):
        raise ParseError("Too many positional arguments", code="TOO_MANY_ARGS")

    values: dict[str, Any] = {}
    for spec, raw in zip(schema.arguments, positionals):
        values[spec.name] = coerce_value(spec, raw)
    for spec in schema.arguments[len(positionals) :]:
        values[spec.name] = resolve_missing(
            spec,
            env_map,
            is_tty=is_tty,
            resolve_prompt_value=resolve_prompt_value,
        )
    for spec in schema.options:
        if spec.name in raw_values:
            values[spec.name] = raw_values[spec.name]
            continue
        values[spec.name] = resolve_missing(
            spec,
            env_map,
            is_tty=is_tty,
            resolve_prompt_value=resolve_prompt_value,
        )
    return ParsedCommand(values=values)


def resolve_missing(
    spec: ParameterSpec,
    env: Mapping[str, str],
    *,
    is_tty: bool,
    resolve_prompt_value: Callable[..., Any] | None,
) -> Any:
    if spec.env and spec.env in env:
        return coerce_value(spec, env[spec.env])
    value = spec.default
    if resolve_prompt_value is not None:
        value = resolve_prompt_value(
            spec,
            current_value=value,
            is_tty=is_tty,
        )
    if value is not MISSING:
        return value
    code = "MISSING_OPTION" if spec.kind == "option" else "MISSING_ARG"
    subject = "option" if spec.kind == "option" else "argument"
    label = f"--{spec.cli_name}" if spec.kind == "option" else spec.name
    raise ParseError(f'Missing required {subject} "{label}"', code=code)


def coerce_value(spec: ParameterSpec, value: Any) -> Any:
    annotation = spec.annotation
    if spec.is_list:
        inner = get_args(annotation)
        inner_type = inner[0] if inner else str
        raw_values = value if isinstance(value, list) else [value]
        return [_coerce_with_type(item, inner_type, spec.name) for item in raw_values]
    return _coerce_with_type(value, annotation, spec.name, choices=spec.choices)


def _coerce_with_type(
    value: Any,
    annotation: Any,
    field_name: str,
    *,
    choices: tuple[Any, ...] = (),
) -> Any:
    if choices:
        mapping = {str(item).lower(): item for item in choices}
        lowered = str(value).lower()
        if lowered in mapping:
            return mapping[lowered]
        joined = ", ".join(str(item) for item in choices)
        raise ValidationError(
            message=f'Invalid value "{value}" for {field_name}. Expected one of: {joined}'
        )
    if annotation in (Any, str):
        return value
    if annotation is Path:
        return Path(value)
    if annotation is int:
        try:
            return int(str(value), 0)
        except ValueError as exc:
            raise ValidationError(message=f"Invalid integer for {field_name}: {value}") from exc
    if annotation is float:
        try:
            return float(str(value))
        except ValueError as exc:
            raise ValidationError(message=f"Invalid float for {field_name}: {value}") from exc
    if annotation is bool:
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
        raise ValidationError(message=f"Invalid boolean for {field_name}: {value}")
    origin = get_origin(annotation)
    if origin and "Union" in str(origin):
        for branch in get_args(annotation):
            if branch is type(None):
                continue
            try:
                return _coerce_with_type(value, branch, field_name)
            except AgentCliError:
                continue
        raise ValidationError(message=f'Invalid value "{value}" for {field_name}')
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        lowered = str(value).lower()
        for member in annotation:
            if member.name.lower() == lowered:
                return member
        raise ValidationError(message=f'Invalid value "{value}" for {field_name}')
    return value


def _store_value(target: dict[str, Any], spec: ParameterSpec, value: Any) -> None:
    if spec.is_list:
        target.setdefault(spec.name, []).extend(
            value if isinstance(value, list) else [value]
        )
        return
    target[spec.name] = value


def _next_value(argv: list[str], index: int, label: str) -> str:
    if index + 1 >= len(argv):
        raise ParseError(f"Missing value for {label}", code="MISSING_OPTION")
    return argv[index + 1]


def strip_builtin_flags(argv: list[str]) -> tuple[BuiltinFlags, list[str]]:
    return extract_builtins(argv)


def normalize_format(explicit: str | None, *, tty: bool) -> str:
    if explicit:
        return explicit
    return "human" if tty else "toon"


def parse_values(
    argv: list[str],
    schema: CommandSchema,
    *,
    env: Mapping[str, str] | None = None,
    tty: bool,
    prompt_value: Callable[..., Any] | None,
) -> dict[str, Any]:
    return parse_command(
        schema,
        argv,
        env=env,
        is_tty=tty,
        resolve_prompt_value=prompt_value,
    ).values
