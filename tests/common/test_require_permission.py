from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from questr.common.enums import UserRole
from questr.common.exceptions import AuthorizationError
from questr.common.permissions import (
    Permission,
    require_permission,
    user_permissions,
)


class TestRequirePermission:
    """require_permission gates on the user's role-to-permission mapping."""

    def test_user_raises_for_impersonate_users(self) -> None:
        dep = require_permission(Permission.IMPERSONATE_USERS)
        current = {'user': MagicMock(role=UserRole.USER), 'csrf_token': 'x'}
        with pytest.raises(AuthorizationError) as excinfo:
            dep(current)
        assert excinfo.value.error_code == 'authorization'

    def test_user_raises_for_manage_roles(self) -> None:
        dep = require_permission(Permission.MANAGE_ROLES)
        current = {'user': MagicMock(role=UserRole.USER), 'csrf_token': 'x'}
        with pytest.raises(AuthorizationError) as excinfo:
            dep(current)
        assert excinfo.value.error_code == 'authorization'

    def test_superuser_passes_for_impersonate_users(self) -> None:
        dep = require_permission(Permission.IMPERSONATE_USERS)
        current = {
            'user': MagicMock(role=UserRole.SUPERUSER),
            'csrf_token': 'x',
        }
        result = dep(current)
        assert result is None

    def test_superuser_passes_for_manage_roles(self) -> None:
        dep = require_permission(Permission.MANAGE_ROLES)
        current = {
            'user': MagicMock(role=UserRole.SUPERUSER),
            'csrf_token': 'x',
        }
        result = dep(current)
        assert result is None


class TestUserPermissions:
    """user_permissions(user) returns the frozenset for the user's role."""

    def test_user_has_no_permissions(self) -> None:
        user = MagicMock(role=UserRole.USER)
        assert user_permissions(user) == frozenset()

    def test_superuser_has_both_permissions(self) -> None:
        user = MagicMock(role=UserRole.SUPERUSER)
        assert user_permissions(user) == frozenset({
            Permission.IMPERSONATE_USERS,
            Permission.MANAGE_ROLES,
        })

    def test_unknown_role_yields_empty(self) -> None:
        user = MagicMock(role=None)
        assert user_permissions(user) == frozenset()
