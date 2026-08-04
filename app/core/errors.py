from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.settings import get_settings


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    details: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


def error_response(status_code: int, err: ApiError, request: Request | None = None) -> JSONResponse:
    payload: dict[str, Any] = {"error": err.to_dict()}
    if request is not None and hasattr(request.state, "request_id") and request.state.request_id:
        payload["request_id"] = request.state.request_id
    return JSONResponse(status_code=status_code, content=payload)


def _flatten_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x is not None)
        items.append({"loc": loc, "msg": e.get("msg"), "type": e.get("type")})
    return items


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    details: list[dict[str, Any]] | None = None
    msg: str

    if isinstance(exc.detail, dict):
        if isinstance(exc.detail.get("code"), str) and exc.detail.get("code"):
            code = exc.detail["code"]
        msg = str(exc.detail.get("message") or "Erreur HTTP")
        extra = {k: v for k, v in exc.detail.items() if k not in {"code", "message"}}
        if extra:
            details = [extra]
        if isinstance(exc.detail.get("details"), list):
            details = list(exc.detail["details"])
    else:
        msg = exc.detail if isinstance(exc.detail, str) else "Erreur HTTP"

    return error_response(exc.status_code, ApiError(code=code, message=msg, details=details), request=_)


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        400,
        ApiError(code="VALIDATION_ERROR", message="Erreur de validation", details=_flatten_validation_errors(exc)),
        request=_,
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    settings = get_settings()
    details: list[dict[str, Any]] | None = None
    if settings.env != "production":
        details = [{"type": type(exc).__name__, "msg": str(exc)}]
    return error_response(500, ApiError(code="INTERNAL_ERROR", message="Erreur interne du serveur", details=details), request=_)


def install_exception_handlers(app: Any) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
