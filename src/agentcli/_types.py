from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


class _Missing:
    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()

OutputFormat = Literal["human", "toon", "json", "yaml", "md", "jsonl"]


@dataclass(frozen=True)
class Param:
    help: str | None = None
    alias: str | None = None
    env: str | None = None
    prompt: str | None = None
    secret: bool = False
    deprecated: bool = False
    hidden: bool = False


@dataclass(frozen=True)
class Result:
    data: Any
    cta: list[str] | None = None


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    kind: str
    annotation: Any
    cli_name: str
    default: Any = MISSING
    required: bool = True
    help: str | None = None
    alias: str | None = None
    env: str | None = None
    prompt: str | None = None
    secret: bool = False
    deprecated: bool = False
    hidden: bool = False
    choices: tuple[Any, ...] = ()
    is_list: bool = False
    is_bool: bool = False

    @property
    def description(self) -> str | None:
        return self.help

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING

    @property
    def display_name(self) -> str:
        return self.name if self.kind == "argument" else f"--{self.cli_name}"


@dataclass
class CommandSchema:
    name: str
    full_path: tuple[str, ...]
    description: str | None
    handler: Callable[..., Any]
    positionals: tuple[ParameterSpec, ...]
    options: tuple[ParameterSpec, ...]
    positional_names: tuple[str, ...]
    keyword_names: tuple[str, ...]
    context_name: str | None = None
    output: Any = None

    @property
    def path(self) -> tuple[str, ...]:
        return self.full_path

    @property
    def arguments(self) -> tuple[ParameterSpec, ...]:
        return self.positionals

    @property
    def context_parameter(self) -> str | None:
        return self.context_name

    @property
    def callback(self) -> Callable[..., Any]:
        return self.handler

    @property
    def command(self) -> str:
        return " ".join(self.full_path)

    @property
    def all_parameters(self) -> list[ParameterSpec]:
        return [*self.positionals, *self.options]


@dataclass(frozen=True)
class BuiltinFlags:
    format: str | None = None
    verbose: bool = False
    help: bool = False
    version: bool = False
    llms: bool = False
    llms_full: bool = False
    mcp: bool = False
    wizard: bool = False


@dataclass
class InvocationResult:
    exit_code: int
    output: str = ""
    envelope: Any | None = None
    data: Any = None
    error: Any = None


@dataclass
class ExecutionResult:
    exit_code: int
    envelope: Any
    output: str
    format: OutputFormat
    streamed: list[Any] = field(default_factory=list)

    @property
    def data(self) -> Any:
        return None if self.envelope is None else self.envelope.data

    @property
    def error(self) -> Any:
        return None if self.envelope is None else self.envelope.error
