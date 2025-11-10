from typing import Any, Dict, Optional
import math
from fastapi import status
from fastapi.responses import JSONResponse

def format_response(
    success: bool = True,
    data: Any = None,
    message: str = "",
    error: Optional[str] = None,
    status_code: int = status.HTTP_200_OK,
    total: Optional[int] = None,
    page: int = 1,
    limit: int = 10,
    headers: Optional[Dict[str, str]] = None
) -> JSONResponse:
    """
    Standard response formatter for all API responses.
    
    Args:
        success: Boolean indicating if the request was successful
        data: The main data payload
        message: Human-readable message
        error: Error message if the request failed
        status_code: HTTP status code
        total: Total number of items (for pagination)
        page: Current page number (for pagination)
        limit: Number of items per page (for pagination)
        headers: Additional headers to include in the response
    
    Returns:
        JSONResponse: Formatted response with standard structure
    """
    if total is not None:
        total_pages = math.ceil(total / limit) if limit > 0 else 0
        has_next = (page * limit) < total if total is not None else False
        has_previous = page > 1
    else:
        total_pages = None
        has_next = None
        has_previous = None

    response_data = {
        "success": success,
        "data": data,
        "message": message,
        "error": error,
        "meta": {
            "total": total,
            "limit": limit,
            "page": page,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_previous": has_previous
        }
    }
    
    # Remove None values from the response
    response_data = {k: v for k, v in response_data.items() if v is not None}
    response_data["meta"] = {k: v for k, v in response_data["meta"].items() if v is not None}
    
    return JSONResponse(
        content=response_data,
        status_code=status_code,
        headers=headers
    )

def success_response(
    data: Any = None,
    message: str = "Operation completed successfully",
    **kwargs
) -> JSONResponse:
    """Helper for successful responses"""
    return format_response(
        success=True,
        data=data,
        message=message,
        **kwargs
    )

def error_response(
    message: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    error: Optional[str] = None,
    **kwargs
) -> JSONResponse:
    """Helper for error responses"""
    return format_response(
        success=False,
        message=message,
        error=error or message,
        status_code=status_code,
        **kwargs
    )
