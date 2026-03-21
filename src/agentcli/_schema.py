from __future__ import annotations

import inspect
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import docstring_parser

from ._context import Context
from ._errors import ConfigError
from ._types import CommandSchema, MISSING, Param, ParameterSpec


def snake_to_kebab(value: str) -> str:
    return value.rstrip("_").replace("_", "-")


def command_name_for(value: str) -> str:
    return snake_to_kebab(value)


def extract_command_schema(
    fn: Any,
    *,
    name: str | None = None,
    output: Any = None,
    path: tuple[str, ...] = (),
) -> CommandSchema:
    signature = inspect.signature(fn)
    hints = get_type_hints(fn, include_extras=True)
    descriptions = _docstring_param_descriptions(fn)
    arguments: list[ParameterSpec] = []
    options: list[ParameterSpec] = []
    positional_names: list[str] = []
    keyword_names: list[str] = []
    context_name: str | None = None

    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise ConfigError(f"Unsupported parameter kind for {parameter.name}")
        annotation = hints.get(parameter.name, parameter.annotation)
        annotation, metadata = unwrap_annotation(annotation)
        if annotation is Context:
            context_name = parameter.name
            if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                keyword_names.append(parameter.name)
            else:
                positional_names.append(parameter.name)
            continue
        default = (
            parameter.default if parameter.default is not inspect._empty else MISSING
        )
        help_text = (
            metadata.help
            if metadata and metadata.help
            else descriptions.get(parameter.name)
        )
        spec = ParameterSpec(
            name=parameter.name,
            kind="option"
            if parameter.kind is inspect.Parameter.KEYWORD_ONLY
            else "argument",
            annotation=annotation,
            cli_name=snake_to_kebab(parameter.name),
            default=default,
            required=default is MISSING,
            help=help_text,
            alias=metadata.alias if metadata else None,
            env=metadata.env if metadata else None,
            prompt=metadata.prompt if metadata else None,
            secret=metadata.secret if metadata else False,
            deprecated=metadata.deprecated if metadata else False,
            hidden=metadata.hidden if metadata else False,
            choices=literal_choices(annotation),
            is_list=is_list(annotation),
            is_bool=annotation is bool,
        )
        if spec.kind == "argument":
            arguments.append(spec)
            positional_names.append(parameter.name)
        else:
            options.append(spec)
            keyword_names.append(parameter.name)

    description = inspect.getdoc(fn)
    short_description = description.splitlines()[0] if description else None
    return CommandSchema(
        name=snake_to_kebab(name or fn.__name__),
        full_path=path + (snake_to_kebab(name or fn.__name__),),
        description=short_description,
        handler=fn,
        positionals=tuple(arguments),
        options=tuple(options),
        positional_names=tuple(positional_names),
        keyword_names=tuple(keyword_names),
        context_name=context_name,
        output=output,
    )


def build_command_schema(
    fn: Any,
    *,
    name: str | None = None,
    full_path: tuple[str, ...] = (),
    output_type: Any = None,
) -> CommandSchema:
    path = full_path[:-1] if full_path else ()
    return extract_command_schema(fn, name=name, output=output_type, path=path)


def unwrap_annotation(annotation: Any) -> tuple[Any, Param | None]:
    if get_origin(annotation) is Annotated:
        base, *metadata = get_args(annotation)
        param = next((item for item in metadata if isinstance(item, Param)), None)
        return base, param
    return annotation, None


def literal_choices(annotation: Any) -> tuple[Any, ...]:
    origin = get_origin(annotation)
    if origin is None or "Literal" not in str(origin):
        return ()
    return tuple(get_args(annotation))


def is_list(annotation: Any) -> bool:
    return get_origin(annotation) in (list, tuple)


def _docstring_param_descriptions(fn: Any) -> dict[str, str]:
    docstring = inspect.getdoc(fn)
    if not docstring:
        return {}
    parsed = docstring_parser.parse(docstring)
    return {
        item.arg_name: item.description
        for item in parsed.params
        if item.arg_name and item.description
    }
