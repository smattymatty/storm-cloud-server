"""Custom exceptions for social integration."""


class GoToSocialError(Exception):
    """Base exception for GoToSocial integration errors."""

    pass


class GoToSocialAuthError(GoToSocialError):
    """Authentication/authorization failed."""

    pass


class GoToSocialAPIError(GoToSocialError):
    """API request failed."""

    pass
