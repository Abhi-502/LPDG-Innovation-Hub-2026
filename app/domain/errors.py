"""Domain exceptions and API error mappings."""

from __future__ import annotations


class DomainError(Exception):
    """Base domain exception."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InvalidRequestError(DomainError):
    """Raised when client input parameters are malformed or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, status_code=400)


class InvalidGatewayIdError(DomainError):
    """Raised when gateway identifier fails normalisation format checks."""

    def __init__(self, gateway_id: str) -> None:
        super().__init__(
            message=f"Gateway ID '{gateway_id}' is invalid. Must be 12-character hex or colon-separated hex.",
            status_code=400,
        )


class GatewayNotFoundError(DomainError):
    """Raised when a gateway is absent from master records."""

    def __init__(self, gateway_id: str) -> None:
        super().__init__(
            message=f"Gateway '{gateway_id}' was not found in gateway master records.",
            status_code=404,
        )


class WeekNotSupportedError(DomainError):
    """Raised when an requested date is outside supported scoring dates."""

    def __init__(self, week_start: str) -> None:
        super().__init__(
            message=f"Week '{week_start}' is not supported. Scored weeks are Mondays between 2026-02-02 and 2026-03-23.",
            status_code=404,
        )


class RunNotFoundError(DomainError):
    """Raised when a requested run_id does not exist."""

    def __init__(self, run_id: str) -> None:
        super().__init__(
            message=f"Run '{run_id}' not found.",
            status_code=404,
        )


class ConcurrentRunError(DomainError):
    """Raised when a new run is triggered while another execution is actively running."""

    def __init__(self, message: str = "Another prioritisation run is currently executing.") -> None:
        super().__init__(message=message, status_code=409)


class DataUnavailableError(DomainError):
    """Raised when required underlying data files are missing or inaccessible."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, status_code=503)
