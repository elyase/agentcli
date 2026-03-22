from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Any

from ._errors import AgentCliError


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    retryable: bool = False
    suggested_commands: list[str] | None = None


@dataclass
class Meta:
    command: str
    suggested_commands: list[str] | None = None
    duration_ms: float | None = None
    streamed: bool = False


@dataclass(frozen=True)
class Envelope:
    ok: bool
    data: Any | None = None
    error: ErrorInfo | None = None
    meta: Meta | None = None


def make_success_envelope(
    data: Any,
    *,
    command: str,
    cta: list[str] | None = None,
) -> Envelope:
    return Envelope(
        ok=True, data=data, meta=Meta(command=command, suggested_commands=cta)
    )


def make_error_envelope(error: Exception, *, command: str) -> Envelope:
    if isinstance(error, AgentCliError):
        info = ErrorInfo(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            suggested_commands=error.cta,
        )
    else:
        info = ErrorInfo(code="UNKNOWN", message=str(error), retryable=False)
    return Envelope(
        ok=False,
        error=info,
        meta=Meta(command=command, suggested_commands=info.suggested_commands),
    )


def make_envelope(
    *,
    ok: bool,
    command: str,
    format: str,
    data: Any = None,
    error: ErrorInfo | None = None,
    duration_ms: float | None = None,
    cta: list[str] | None = None,
    streamed: bool = False,
) -> Envelope:
    if ok:
        return Envelope(
            ok=True,
            data=data,
            meta=Meta(
                command=command,
                suggested_commands=cta,
                duration_ms=duration_ms,
                streamed=streamed,
            ),
        )
    return Envelope(
        ok=False,
        error=error,
        meta=Meta(
            command=command,
            suggested_commands=cta,
            duration_ms=duration_ms,
            streamed=streamed,
        ),
    )


def normalize_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return normalize_value(dataclasses.asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return normalize_value(value.to_dict())
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return normalize_value(value.model_dump())
    if isinstance(value, dict):
        return {
            str(key): normalize_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    return value


def envelope_payload(envelope: Envelope, *, verbose: bool) -> Any:
    if envelope.ok and not verbose:
        return normalize_value(envelope.data)
    return normalize_value(dataclasses.asdict(envelope))


def render_output(
    envelope: Envelope,
    *,
    format_name: str | None,
    is_tty: bool,
    verbose: bool = False,
) -> str:
    actual_format = format_name or ("pretty" if is_tty else "toon")
    payload = envelope_payload(envelope, verbose=verbose)
    if actual_format == "json":
        return json.dumps(payload, indent=2, default=str)
    if actual_format == "jsonl":
        return json.dumps(payload, default=str)
    if actual_format == "md":
        return render_markdown(payload)
    if actual_format == "yaml":
        return render_yaml(payload)
    if actual_format == "pretty":
        return render_plain(payload)
    return render_toon(payload)


def render_stream_item(
    item: Any,
    *,
    format_name: str | None = None,
    output_format: str | None = None,
    is_tty: bool | None = None,
) -> str:
    format_name = output_format or format_name
    payload = normalize_value(item)
    if format_name == "jsonl":
        return json.dumps(payload, default=str)
    if format_name == "json":
        return json.dumps(payload, indent=2, default=str)
    if format_name == "md":
        return render_markdown(payload)
    return render_toon(payload)


def render_envelope(envelope: Envelope, *, format: str, verbose: bool = False) -> str:
    return render_output(
        envelope, format_name=format, is_tty=(format == "human"), verbose=verbose
    )


def render_plain(value: Any) -> str:
    value = normalize_value(value)
    if isinstance(value, dict):
        return "\n".join(_plain_lines(value))
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    return str(value)


def _plain_lines(value: dict[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, item in value.items():
        if isinstance(item, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(_plain_lines(item, indent + 2))
            continue
        if isinstance(item, list):
            lines.append(f"{prefix}{key}:")
            lines.extend(f"{prefix}  - {entry}" for entry in item)
            continue
        lines.append(f"{prefix}{key}: {item}")
    return lines


def render_toon(value: Any) -> str:
    value = normalize_value(value)
    if isinstance(value, dict):
        return "\n".join(_toon_dict(value))
    if isinstance(value, list):
        return _toon_list("items", value)
    return _toon_scalar(value)


def _toon_dict(value: dict[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, dict):
            if not item:
                lines.append(f"{prefix}{key}: (empty)")
                continue
            lines.append(f"{prefix}{key}:")
            lines.extend(_toon_dict(item, indent + 2))
            continue
        if isinstance(item, list):
            lines.extend(_toon_list_lines(key, item, indent))
            continue
        lines.append(f"{prefix}{key}: {_toon_scalar(item)}")
    return lines


def _toon_list(key: str, value: list[Any]) -> str:
    return "\n".join(_toon_list_lines(key, value, 0))


def _toon_list_lines(key: str, value: list[Any], indent: int) -> list[str]:
    prefix = " " * indent
    if not value:
        return [f"{prefix}{key}: (empty)"]
    if all(not isinstance(item, (dict, list)) for item in value):
        joined = ",".join(_toon_scalar(item) for item in value)
        return [f"{prefix}{key}[{len(value)}]: {joined}"]
    if all(isinstance(item, dict) and item for item in value):
        headers = list(value[0].keys())
        if all(list(item.keys()) == headers for item in value):
            lines = [f"{prefix}{key}[{len(value)}]{{{','.join(headers)}}}:"]
            for item in value:
                row = ",".join(_toon_scalar(item[column]) for column in headers)
                lines.append(f"{prefix}  {row}")
            return lines
    lines = [f"{prefix}{key}:"]
    for item in value:
        lines.append(f"{prefix}  - {_toon_scalar(item)}")
    return lines


def _toon_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "(empty)"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if any(char in text for char in [":", ",", "\n", '"']):
        return json.dumps(text)
    return text


def render_markdown(value: Any) -> str:
    value = normalize_value(value)
    if (
        isinstance(value, list)
        and value
        and all(isinstance(item, dict) for item in value)
    ):
        headers = list(value[0].keys())
        lines = [
            f"| {' | '.join(headers)} |",
            f"| {' | '.join('---' for _ in headers)} |",
        ]
        for item in value:
            lines.append(
                f"| {' | '.join(str(item.get(header, '')) for header in headers)} |"
            )
        return "\n".join(lines)
    if isinstance(value, dict):
        return "\n".join(f"- **{key}**: {item}" for key, item in value.items())
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    return str(value)


def render_yaml(value: Any) -> str:
    try:
        import yaml
    except ImportError as exc:
        raise AgentCliError(
            code="MISSING_DEP",
            message="YAML output requires agentcli[yaml]",
            retryable=False,
        ) from exc
    return yaml.safe_dump(normalize_value(value), sort_keys=False)
