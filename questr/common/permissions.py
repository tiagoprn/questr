from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

from fastapi import Depends

from questr.common.enums import UserRole
from questr.common.exceptions import AuthorizationError

if TYPE_CHECKING:
    from questr.domains.users.repository import User


class Permission(str, Enum):
    IMPERSONATE_USERS = 'impersonate_users'
    MANAGE_ROLES = 'manage_roles'


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.SUPERUSER: frozenset({
        Permission.IMPERSONATE_USERS,
        Permission.MANAGE_ROLES,
    }),
    UserRole.USER: frozenset(),
}


def require_permission(
    permission: Permission,
) -> Callable[[dict[str, Any]], None]:
    """Return a FastAPI dependency that gates on the required permission.

    Uses a lazy import of ``get_current_user`` to avoid circular imports
    when the users router imports from this module.
    """

    from questr.domains.users.api import (  # noqa: PLC0415
        T_CurrentUser,
        get_current_user,
    )

    def _check_permission(
        current: T_CurrentUser = Depends(get_current_user),
    ) -> None:
        user = current['user']
        if permission not in user_permissions(user):
            msg = f'Missing required permission: {permission.value}'
            raise AuthorizationError(message=msg)

    return _check_permission


def user_permissions(user: User) -> frozenset[Permission]:
    """Return the permission set granted to the user's role."""
    return ROLE_PERMISSIONS.get(user.role, frozenset())
