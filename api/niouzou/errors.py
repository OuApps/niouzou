"""API error type and handlers producing the {error, message} envelope.

docs/API_SPEC.md defines every error as ``{"error": <code>, "message": <text>}``.
FastAPI's default is ``{"detail": ...}``, so we raise ``APIError`` and register
handlers in main.py to translate both our errors and framework errors.
"""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    """Raised by services/routers; carries the spec's error code + message."""

    def __init__(self, status_code: int, error: str, message: str) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


# Convenience constructors for the common cases.
def not_found(message: str = "Resource not found") -> APIError:
    return APIError(status.HTTP_404_NOT_FOUND, "not_found", message)


def conflict(message: str) -> APIError:
    return APIError(status.HTTP_409_CONFLICT, "conflict", message)


def unauthorized(message: str = "Missing or invalid token") -> APIError:
    return APIError(status.HTTP_401_UNAUTHORIZED, "unauthorized", message)


def bad_request(message: str) -> APIError:
    return APIError(status.HTTP_400_BAD_REQUEST, "bad_request", message)


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message},
    )


async def http_exception_handler(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "message": str(exc.detail)},
    )


async def validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "validation_error", "message": str(exc.errors())},
    )
