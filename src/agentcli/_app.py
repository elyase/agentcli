from __future__ import annotations

import asyncio
import inspect
import os
import sys
import time
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from typing import Any

from ._agents import iter_commands, render_llms_full, render_llms_index, start_mcp
from ._context import Context, detect_agent_mode
from ._errors import normalize_exception, unknown_name_error
from ._help import render_app_help, render_command_help
from ._output import make_envelope, render_envelope, render_stream_item
from ._parser import normalize_format, parse_values, strip_builtin_flags
from ._schema import build_command_schema, command_name_for
from ._types import CommandSchema, ExecutionResult, MISSING, OutputFormat, Result
from ._wizard import prompt_for_parameter, wizard_schema


Middleware = Callable[[Context, Callable[[], Any]], Any]


class App:
    def __init__(
        self,
        name: str,
        *,
        version: str | None = None,
        description: str | None = None,
        help_header: str | None = None,
        help_footer: str | None = None,
        autocorrect_threshold: int = 2,
    ) -> None:
        self.name = name
        self.version = version
        self.description = description
        self.help_header = help_header
        self.help_footer = help_footer
        self.autocorrect_threshold = autocorrect_threshold
        self.commands: dict[str, CommandSchema] = {}
        self.subapps: dict[str, App] = {}
        self.middleware: list[Middleware] = []
        self._default_command: CommandSchema | None = None

    def command(
        self,
        func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        output: type[Any] | None = None,
    ):
        def decorator(callback: Callable[..., Any]) -> Callable[..., Any]:
            command_name = name or command_name_for(callback.__name__)
            self.commands[command_name] = build_command_schema(
                callback,
                name=command_name,
                full_path=(self.name, command_name),
                output_type=output,
            )
            return callback

        return decorator if func is None else decorator(func)

    def use(self, middleware: Middleware) -> Middleware:
        self.middleware.append(middleware)
        return middleware

    def mount(self, sub_app: App, name: str | None = None) -> None:
        self.subapps[name or sub_app.name] = sub_app

    def default(
        self, func: Callable[..., Any] | None = None, *, output: type[Any] | None = None
    ):
        """Register the default command — runs when no sub-command is given.

        Can be used as a bare decorator (``@app.default``) or with options
        (``@app.default(output=MyType)``).
        """

        def decorator(callback: Callable[..., Any]) -> Callable[..., Any]:
            self._default_command = build_command_schema(
                callback, name=self.name, full_path=(self.name,), output_type=output
            )
            return callback

        return decorator if func is None else decorator(func)

    def _set_default(
        self, callback: Callable[..., Any], *, output: type[Any] | None = None
    ) -> None:
        self.default(callback, output=output)

    def invoke(
        self,
        *,
        argv: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        is_tty: bool | None = None,
        stdin: Any = None,
        stdout: Any = None,
        stderr: Any = None,
    ) -> ExecutionResult:
        return self.run(
            argv, env=env, tty=is_tty, stdin=stdin, stdout=stdout, stderr=stderr
        )

    def run(
        self,
        argv: Iterable[str] | None = None,
        *,
        env: dict[str, str] | None = None,
        tty: bool | None = None,
        stdin: Any = None,
        stdout: Any = None,
        stderr: Any = None,
    ) -> ExecutionResult:
        args = list(sys.argv[1:] if argv is None else argv)
        env_map = {**os.environ, **(env or {})}
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        stderr = stderr or sys.stderr
        is_tty = bool(tty) if tty is not None else _isatty(stdout)
        builtins, remaining = strip_builtin_flags(args)
        output_format = normalize_format(builtins.format, tty=is_tty)
        started = time.perf_counter()
        try:
            app, command, remainder, middlewares = self._resolve(remaining)
            if builtins.version:
                text = self.version or ""
                _write(stdout, text)
                return _finish(
                    make_envelope(
                        ok=True, command=self.name, format=output_format, data=text
                    ),
                    stdout,
                    output_format,
                )
            if builtins.llms:
                text = render_llms_index(self)
                _write(stdout, text)
                return _finish(
                    make_envelope(
                        ok=True, command=self.name, format=output_format, data=text
                    ),
                    stdout,
                    output_format,
                )
            if builtins.llms_full:
                text = render_llms_full(self)
                _write(stdout, text)
                return _finish(
                    make_envelope(
                        ok=True, command=self.name, format=output_format, data=text
                    ),
                    stdout,
                    output_format,
                )
            if builtins.mcp:
                start_mcp(self)
                return _finish(
                    make_envelope(
                        ok=True, command=self.name, format=output_format, data=None
                    ),
                    stdout,
                    output_format,
                )
            if builtins.help or command is None:
                text = (
                    render_command_help(command)
                    if command
                    else render_app_help(app, path=_app_path(self, app))
                )
                _write(stdout, text)
                return _finish(
                    make_envelope(
                        ok=True,
                        command=" ".join(_app_path(self, app)),
                        format=output_format,
                        data=text,
                    ),
                    stdout,
                    output_format,
                )
            if builtins.wizard and not is_tty:
                envelope = make_envelope(
                    ok=True,
                    command=command.command,
                    format=output_format,
                    data=wizard_schema(command),
                )
                _write(
                    stdout,
                    render_envelope(envelope, format=output_format, verbose=True),
                )
                return _finish(envelope, stdout, output_format)
            values = parse_values(
                remainder,
                command,
                env=env_map,
                tty=is_tty,
                prompt_value=lambda spec, current_value=None, is_tty=False, **_kwargs: (
                    prompt_for_parameter(spec, stdin=stdin, stdout=stdout)
                    if spec.prompt and is_tty
                    else current_value
                ),
            )
            if builtins.wizard and is_tty:
                for parameter in command.all_parameters:
                    if values.get(parameter.name, MISSING) is MISSING:
                        values[parameter.name] = prompt_for_parameter(
                            parameter, stdin=stdin, stdout=stdout
                        )
            context = Context(
                self.name,
                command.path,
                output_format,
                detect_agent_mode(stdin=stdin, stdout=stdout, env=env_map),
                args,
                env_map,
                {},
                {},
                {},
            )
            if command.context_parameter:
                values[command.context_parameter] = context
            envelope, streamed = asyncio.run(
                self._execute(
                    command,
                    values,
                    context=context,
                    middlewares=middlewares,
                    stdout=stdout,
                    format=output_format,
                )
            )
            if envelope.meta:
                envelope.meta.duration_ms = (time.perf_counter() - started) * 1000
            rendered = render_envelope(
                envelope,
                format=output_format,
                verbose=builtins.verbose or not envelope.ok,
            )
            if not streamed or builtins.verbose:
                _write(stdout, rendered)
            return _finish(envelope, stdout, output_format, streamed)
        except Exception as error:  # noqa: BLE001
            agent_error = normalize_exception(error)
            envelope = make_envelope(
                ok=False,
                command=self.name,
                format=output_format,
                error=agent_error.to_error_info(),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
            target = stderr if stderr is not None else stdout
            _write(
                target, render_envelope(envelope, format=output_format, verbose=True)
            )
            return ExecutionResult(
                agent_error.exit_code, envelope, _buffer(stdout, stderr), output_format
            )

    def __call__(self, argv: Iterable[str] | None = None) -> None:
        result = self.run(argv)
        if result.exit_code:
            raise SystemExit(result.exit_code)

    def test(self) -> AbstractContextManager[Any]:
        from .testing import _TestClient

        return _TestClient(self)

    def _resolve(
        self, argv: list[str]
    ) -> tuple[App, CommandSchema | None, list[str], list[Middleware]]:
        current = self
        index = 0
        middlewares = list(self.middleware)
        while index < len(argv):
            token = argv[index]
            if token.startswith("-"):
                break
            if token in current.subapps:
                current = current.subapps[token]
                middlewares.extend(current.middleware)
                index += 1
                continue
            if token in current.commands:
                command = current.commands[token]
                command.full_path = (*_app_path(self, current), token)
                return current, command, argv[index + 1 :], middlewares
            if current._default_command is not None:
                break
            raise unknown_name_error(
                kind="command",
                value=token,
                choices=[*current.subapps.keys(), *current.commands.keys()],
            )
        if current._default_command is not None:
            current._default_command.full_path = _app_path(self, current)
            return current, current._default_command, argv[index:], middlewares
        return current, None, argv[index:], middlewares

    async def _execute(
        self,
        command: CommandSchema,
        values: dict[str, Any],
        *,
        context: Context,
        middlewares: list[Middleware],
        stdout: Any,
        format: OutputFormat,
    ) -> tuple[Any, list[Any]]:
        streamed: list[Any] = []
        cta: list[str] | None = None

        async def invoke_callback() -> Any:
            nonlocal cta
            outcome = command.callback(**values)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if inspect.isasyncgen(outcome):
                async for item in outcome:
                    streamed.append(item)
                    _write(
                        stdout,
                        render_stream_item(item, output_format=format, is_tty=False),
                    )
                return None
            if inspect.isgenerator(outcome):
                for item in outcome:
                    streamed.append(item)
                    _write(
                        stdout,
                        render_stream_item(item, output_format=format, is_tty=False),
                    )
                return None
            if isinstance(outcome, Result):
                cta = [
                    item.command if hasattr(item, "command") else str(item)
                    for item in outcome.cta
                ]
                return outcome.data
            return outcome

        last_result: Any = None

        async def dispatch(index: int) -> Any:
            nonlocal last_result
            if index == len(middlewares):
                last_result = await invoke_callback()
                return last_result
            middleware = middlewares[index]

            async def next_call() -> Any:
                return await dispatch(index + 1)

            result = middleware(context, next_call)
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                last_result = result
            return last_result

        data = await dispatch(0)
        if streamed and data is None:
            data = streamed
        envelope = make_envelope(
            ok=True,
            command=command.command,
            format=format,
            data=data,
            cta=cta,
            streamed=bool(streamed),
        )
        return envelope, streamed


def run(
    func: Callable[..., Any],
    *,
    name: str | None = None,
    version: str | None = None,
    argv: list[str] | None = None,
) -> None:
    app = App(
        name or command_name_for(func.__name__),
        version=version,
        description=inspect.getdoc(func),
    )
    app._set_default(func)
    app(argv)


def _app_path(root: App, target: App) -> tuple[str, ...]:
    if root is target:
        return (root.name,)
    for path, _command in iter_commands(root):
        if path[:-1] and path[-2] == target.name:
            return path[:-1]
    return (root.name, target.name)


def _isatty(stream: Any) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def _write(stream: Any, text: str) -> None:
    if not text:
        return
    stream.write(text)
    if not text.endswith("\n"):
        stream.write("\n")


def _buffer(stdout: Any, stderr: Any | None = None) -> str:
    for stream in (stdout, stderr):
        if hasattr(stream, "getvalue"):
            return stream.getvalue()
    return ""


def _finish(
    envelope, stdout: Any, format: OutputFormat, streamed: list[Any] | None = None
) -> ExecutionResult:
    return ExecutionResult(
        0 if envelope.ok else 1, envelope, _buffer(stdout), format, streamed or []
    )
