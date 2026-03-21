from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from ._types import OutputFormat


@dataclass
class Context:
    app_name: str = ""
    command_path: tuple[str, ...] = ()
    format: OutputFormat = "toon"
    agent: bool = False
    argv: list[str] = field(default_factory=list)
    env: Mapping[str, str] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    parent_state: Mapping[str, Any] = field(default_factory=dict)

    @property
    def command(self) -> str:
        return " ".join(self.command_path)


def detect_agent_mode(*, stdin: Any = None, stdout: Any = None, env: Mapping[str, str] | None = None) -> bool:
    environment = env or os.environ
    if environment.get("AGENTCLI_MODE"):
        return environment["AGENTCLI_MODE"].lower() == "agent"
    return not _isatty(stdout or sys.stdout) or not _isatty(stdin or sys.stdin)


def _isatty(stream: Any) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False
