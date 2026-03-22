from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class CliResult:
    exit_code: int
    output: str
    data: Any = None
    error: Any = None


class CliRunner:
    def __init__(self, app: Any) -> None:
        self.app = app

    def invoke(
        self,
        argv: list[str],
        *,
        env: Mapping[str, str] | None = None,
        is_tty: bool = False,
        stdin: str = "",
    ) -> CliResult:
        stdout = io.StringIO()
        input_stream = io.StringIO(stdin)
        result = self.app.invoke(
            argv=argv,
            env=dict(env or {}),
            is_tty=is_tty,
            stdin=input_stream,
            stdout=stdout,
        )
        output = stdout.getvalue()
        data = result.data
        error = result.error
        try:
            parsed = json.loads(output)
        except Exception:
            parsed = None
        if isinstance(parsed, dict) and "ok" in parsed:
            data = parsed.get("data")
            error = parsed.get("error")
        elif parsed is not None:
            data = parsed
        return CliResult(
            exit_code=result.exit_code,
            output=output,
            data=data,
            error=error,
        )
