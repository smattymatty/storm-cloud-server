"""Middleware to track social posting warnings in request context."""
import threading
from typing import Dict, List

_thread_locals = threading.local()


def get_social_warnings() -> List[Dict[str, str]]:
    """Get social warnings from current request context."""
    return getattr(_thread_locals, "social_warnings", [])


def add_social_warning(code: str, message: str) -> None:
    """Add a warning to current request context."""
    if not hasattr(_thread_locals, "social_warnings"):
        _thread_locals.social_warnings = []
    _thread_locals.social_warnings.append(
        {
            "code": code,
            "message": message,
        }
    )


def clear_social_warnings() -> None:
    """Clear warnings (called at request start)."""
    _thread_locals.social_warnings = []


class SocialWarningMiddleware:
    """Middleware to manage social posting warning context."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_social_warnings()
        response = self.get_response(request)
        return response
