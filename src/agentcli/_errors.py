from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from ._output import ErrorInfo


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str


class AgentCliError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        cta: list[str] | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.cta = cta
        self.exit_code = exit_code

    def to_error_info(self) -> ErrorInfo:
        from ._output import ErrorInfo

        return ErrorInfo(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
            cta=self.cta,
        )


class ParseError(AgentCliError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "PARSE",
        retryable: bool = True,
        cta: list[str] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            retryable=retryable,
            cta=cta,
            exit_code=1,
        )


class ValidationError(AgentCliError):
    def __init__(
        self,
        *,
        message: str,
        field_errors: list[FieldError] | None = None,
        cta: list[str] | None = None,
    ) -> None:
        super().__init__(
            code="VALIDATION",
            message=message,
            retryable=True,
            cta=cta,
            exit_code=1,
        )
        self.field_errors = field_errors or []


class ConfigError(AgentCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="CONFIG",
            message=message,
            retryable=False,
            exit_code=1,
        )


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def suggest_matches(
    value: str,
    choices: Iterable[str],
    *,
    threshold: int = 2,
    limit: int = 3,
) -> list[str]:
    scored: list[tuple[int, str]] = []
    lowered = value.lower()
    for choice in choices:
        distance = levenshtein(lowered, choice.lower())
        if distance <= threshold:
            scored.append((distance, choice))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [choice for _, choice in scored[:limit]]


def unknown_name_error(*, kind: str, value: str, choices: Iterable[str]) -> ParseError:
    suggestions = suggest_matches(value, choices)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    return ParseError(
        f'Unknown {kind} "{value}".{hint}', code=f"UNKNOWN_{kind.upper()}"
    )


def normalize_exception(error: Exception) -> AgentCliError:
    if isinstance(error, AgentCliError):
        return error
    return AgentCliError(code="UNKNOWN", message=str(error) or error.__class__.__name__)
