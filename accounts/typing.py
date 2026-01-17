"""Type definitions for accounts app."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from accounts.models import Account


class UserProtocol(Protocol):
    """Protocol defining expected User model attributes for type checking.

    This protocol describes the interface expected from Django's User model
    with our custom Account extension (via OneToOneField related_name="account").
    """

    id: int
    username: str
    email: str
    is_staff: bool
    is_superuser: bool
    is_active: bool
    account: "Account"

    def get_username(self) -> str: ...
