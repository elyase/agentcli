from __future__ import annotations

import json
from typing import Any

from ._errors import AgentCliError


def iter_commands(app, prefix: tuple[str, ...] | None = None):
    current = prefix or (app.name,)
    if app._default_command is not None:
        command = app._default_command
        command.full_path = current
        yield current, command
    for name, command in sorted(app.commands.items()):
        path = (*current, name)
        command.full_path = path
        yield path, command
    for name, subapp in sorted(app.subapps.items()):
        yield from iter_commands(subapp, (*current, name))


def render_llms_index(app) -> str:
    lines = [f"# {app.name}" + (f" v{app.version}" if app.version else "")]
    if app.description:
        lines.extend(["", app.description])
    lines.extend(["", "| Command | Description |", "|---------|-------------|"])
    for path, command in iter_commands(app):
        lines.append(f"| `{' '.join(path)}` | {command.description or ''} |")
    lines.extend(["", f"Run `{app.name} <command> --help` for details."])
    return "\n".join(lines)


def render_llms_full(app) -> str:
    commands = []
    for path, command in iter_commands(app):
        commands.append(
            {
                "command": " ".join(path),
                "description": command.description,
                "arguments": [parameter.name for parameter in command.positionals],
                "options": [
                    parameter.cli_name
                    for parameter in command.options
                    if not parameter.hidden
                ],
            }
        )
    return json.dumps(
        {
            "name": app.name,
            "version": app.version,
            "description": app.description,
            "commands": commands,
        },
        indent=2,
    )


def start_mcp(app) -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise AgentCliError(
            "MISSING_DEPENDENCY",
            "MCP mode requires agentcli[mcp]",
            cta=["pip install agentcli[mcp]"],
        ) from error

    server = FastMCP(app.name)
    for path, command in iter_commands(app):
        tool_name = "_".join(path[1:] if path and path[0] == app.name else path)

        @server.tool(name=tool_name, description=command.description or tool_name)
        async def _tool(**kwargs: Any) -> str:
            argv = list(path[1:] if path and path[0] == app.name else path)
            for key, value in kwargs.items():
                flag = f"--{key.replace('_', '-')}"
                if value is True:
                    argv.append(flag)
                elif value not in (False, None):
                    argv.extend([flag, str(value)])
            result = app.run(argv, tty=False)
            return json.dumps(
                {
                    "ok": result.envelope.ok,
                    "data": result.envelope.data,
                    "error": result.envelope.error,
                },
                default=str,
            )

    server.run()
