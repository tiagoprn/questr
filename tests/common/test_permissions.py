from __future__ import annotations

from questr.common.enums import UserRole
from questr.common.permissions import ROLE_PERMISSIONS, Permission


class TestPermission:
    """Permission enum has the expected members."""

    def test_has_impersonate_users(self) -> None:
        assert Permission.IMPERSONATE_USERS == 'impersonate_users'

    def test_has_manage_roles(self) -> None:
        assert Permission.MANAGE_ROLES == 'manage_roles'


class TestRolePermissions:
    """ROLE_PERMISSIONS maps roles to the correct permissions."""

    def test_superuser_has_both_permissions(self) -> None:
        perms = ROLE_PERMISSIONS[UserRole.SUPERUSER]
        assert Permission.IMPERSONATE_USERS in perms
        assert Permission.MANAGE_ROLES in perms
        assert len(perms) == 2  # noqa: PLR2004

    def test_user_has_no_permissions(self) -> None:
        perms = ROLE_PERMISSIONS[UserRole.USER]
        assert len(perms) == 0

    def test_all_roles_are_covered(self) -> None:
        assert set(ROLE_PERMISSIONS) == set(UserRole)
