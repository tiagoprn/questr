from __future__ import annotations

from questr.common.enums import AuditAction


class TestAuditAction:
    """AC (new): AuditAction enum exists with all expected members."""

    def test_has_impersonation_start(self) -> None:
        assert AuditAction.IMPERSONATION_START == 'impersonation_start'

    def test_has_impersonation_end(self) -> None:
        assert AuditAction.IMPERSONATION_END == 'impersonation_end'

    def test_has_role_granted(self) -> None:
        assert AuditAction.ROLE_GRANTED == 'role_granted'

    def test_has_role_revoked(self) -> None:
        assert AuditAction.ROLE_REVOKED == 'role_revoked'
