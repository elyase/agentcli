from __future__ import annotations

import getpass
import sys
from typing import Any


def text(
    message: str,
    *,
    default: Any = None,
    stdin: Any = None,
    stdout: Any = None,
) -> str:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    suffix = f" [{default}]" if default not in (None, "") else ""
    output_stream.write(f"? {message}{suffix}: ")
    output_stream.flush()
    value = input_stream.readline().rstrip("\n")
    return str(default) if value == "" and default is not None else value


def password(message: str, *, stdin: Any = None, stdout: Any = None) -> str:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    if input_stream is sys.stdin and output_stream is sys.stdout:
        return getpass.getpass(f"? {message}: ")
    output_stream.write(f"? {message}: ")
    output_stream.flush()
    return input_stream.readline().rstrip("\n")


def confirm(
    message: str,
    *,
    default: bool = False,
    stdin: Any = None,
    stdout: Any = None,
) -> bool:
    answer = (
        text(
            f"{message} [{'Y/n' if default else 'y/N'}]",
            default="y" if default else "n",
            stdin=stdin,
            stdout=stdout,
        )
        .strip()
        .lower()
    )
    return answer in {"y", "yes", "true", "1"}


def select(
    message: str,
    options: list[str],
    *,
    stdin: Any = None,
    stdout: Any = None,
) -> str:
    output_stream = stdout or sys.stdout
    output_stream.write(f"? {message}: {', '.join(options)}\n")
    output_stream.flush()
    choice = text("Choice", stdin=stdin, stdout=stdout)
    if choice in options:
        return choice
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(options):
            return options[index]
    raise ValueError(f"Invalid selection: {choice}")
