"""Error bodies are ``{"detail": "<message code>"}``; a few add safe fields next to the code."""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ErrorWithFields(HTTPException):
    """An HTTPException whose body carries ``fields`` next to ``detail``.

    Only put values in ``fields`` that are safe to show (codes, schema paths), never user input.
    """

    def __init__(self, status_code: int, detail: str, **fields: Any) -> None:
        super().__init__(status_code, detail)
        self.fields = fields


async def error_with_fields_handler(request: Request, exc: ErrorWithFields) -> JSONResponse:
    return JSONResponse(
        {"detail": exc.detail, **exc.fields}, status_code=exc.status_code, headers=exc.headers
    )
