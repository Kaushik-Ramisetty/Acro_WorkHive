"""
utils/response.py — Standardised JSON response helpers.

All onboarding endpoints return:
  { "success": bool, "message": str, "data": any }
"""

from typing import Any
from fastapi.responses import JSONResponse


def ok(data: Any = None, message: str = "Success", status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "message": message, "data": data},
    )


def created(data: Any = None, message: str = "Created successfully") -> JSONResponse:
    return ok(data=data, message=message, status_code=201)


def error(message: str, status_code: int = 400, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message, "data": data},
    )
