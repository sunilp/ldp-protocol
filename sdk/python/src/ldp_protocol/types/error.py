"""LDP typed failure codes."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class FailureCategory(str, Enum):
    IDENTITY = "identity"
    CAPABILITY = "capability"
    POLICY = "policy"
    RUNTIME = "runtime"
    QUALITY = "quality"
    SESSION = "session"
    TRANSPORT = "transport"


class ErrorSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class LdpError(BaseModel):
    code: str
    category: FailureCategory
    message: str
    severity: ErrorSeverity
    retryable: bool
    partial_output: Any | None = None

    @classmethod
    def identity(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.IDENTITY,
            message=message,
            severity=ErrorSeverity.ERROR,
            retryable=False,
        )

    @classmethod
    def capability(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.CAPABILITY,
            message=message,
            severity=ErrorSeverity.ERROR,
            retryable=False,
        )

    @classmethod
    def policy(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.POLICY,
            message=message,
            severity=ErrorSeverity.FATAL,
            retryable=False,
        )

    @classmethod
    def runtime(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.RUNTIME,
            message=message,
            severity=ErrorSeverity.ERROR,
            retryable=True,
        )

    @classmethod
    def quality(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.QUALITY,
            message=message,
            severity=ErrorSeverity.WARNING,
            retryable=False,
        )

    @classmethod
    def session(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.SESSION,
            message=message,
            severity=ErrorSeverity.ERROR,
            retryable=True,
        )

    @classmethod
    def transport(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.TRANSPORT,
            message=message,
            severity=ErrorSeverity.WARNING,
            retryable=True,
        )
