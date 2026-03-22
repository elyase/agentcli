from __future__ import annotations

from ._types import CommandSchema, ParameterSpec


def render_app_help(app, *, path: tuple[str, ...] = ()) -> str:
    title = " ".join(path or (app.name,))
    lines = [title]
    if app.description:
        lines.extend(["", app.description])
    lines.extend(["", f"Usage: {title} <command>"])
    if app.subapps:
        lines.extend(["", "Groups:"])
        for name, subapp in sorted(app.subapps.items()):
            lines.append(f"  {name:<16} {(subapp.description or '')}".rstrip())
    if app.commands:
        lines.extend(["", "Commands:"])
        for name, command in sorted(app.commands.items()):
            lines.append(f"  {name:<16} {(command.description or '')}".rstrip())
    return "\n".join(lines)


def render_command_help(command: CommandSchema) -> str:
    path = " ".join(command.path)
    lines = [path]
    if command.description:
        lines.extend(["", command.description])
    lines.extend(["", f"Usage: {path}{_usage(command)}"])
    if command.positionals:
        lines.extend(["", "Arguments:"])
        lines.extend(_parameters(command.positionals))
    visible_options = [
        parameter for parameter in command.options if not parameter.hidden
    ]
    if visible_options:
        lines.extend(["", "Options:"])
        lines.extend(_parameters(visible_options))
    return "\n".join(lines)


def _usage(command: CommandSchema) -> str:
    parts = []
    for parameter in command.positionals:
        parts.append(
            f"<{parameter.name}>" if parameter.required else f"[{parameter.name}]"
        )
    for parameter in command.options:
        if parameter.hidden:
            continue
        parts.append(
            f"[--{parameter.cli_name}]"
            if parameter.is_bool
            else f"[--{parameter.cli_name} VALUE]"
        )
    return (" " + " ".join(parts)) if parts else ""


def _parameters(parameters: list[ParameterSpec]) -> list[str]:
    lines = []
    for parameter in parameters:
        label = parameter.display_name
        if parameter.alias:
            label = f"{label}, -{parameter.alias}"
        lines.append(f"  {label:<24} {(parameter.description or '')}".rstrip())
    return lines
