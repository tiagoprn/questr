"""Out-of-band superuser promotion script.

Usage:
    make shell SCRIPT=scripts/fast_shell/promote_superuser.py \
        EMAIL=promote@test.com

Promotes a verified, ACTIVE user to SUPERUSER role and writes a
ROLE_GRANTED audit row with actor_id=None (out-of-band marker).
Only ACTIVE users may be promoted out-of-band.
"""

import asyncio
import os

from questr.common.enums import AuditAction, UserRole, UserStatus
from questr.domains.users.repository import (
    AuditLog,
    AuditLogRepository,
    UserRepository,
)
from scripts.fast_shell import session


async def promote(email: str) -> None:
    """Promote a user to SUPERUSER by email."""
    user_repo = UserRepository(session=session)
    audit_repo = AuditLogRepository(session=session)

    user = await user_repo.get_by_email(email)
    if user is None:
        print(f'User with email "{email}" not found.')
        return

    if user.role == UserRole.SUPERUSER:
        print(f'User "{email}" is already a superuser.')
        return

    if user.status != UserStatus.ACTIVE:
        print(
            f'User "{email}" is not ACTIVE (status={user.status.value}); '
            f'aborting promotion.'
        )
        return

    old_role = user.role
    updated = await user_repo.update_role(user.id, UserRole.SUPERUSER)
    if updated is None:
        print(f'User "{email}" could not be promoted.')
        return

    audit = await audit_repo.insert(
        AuditLog(
            action=AuditAction.ROLE_GRANTED,
            actor_id=None,
            target_id=user.id,
            old_role=old_role,
            new_role=UserRole.SUPERUSER,
            # Out-of-band marker: differentiates script-originated audit
            # rows. ip_address is intentionally NOT set (Captain, 2026-08-04).
            user_agent='fast_shell',
        )
    )

    # shell.py does NOT auto-commit; without this the changes roll back
    # when the session closes.
    await session.commit()
    print(
        f'Promoted "{email}" from {old_role.value} to superuser. '
        f'Audit log id: {audit.id}'
    )


# NOTE: runpy.run_path (make shell) executes the module with
# __name__ == '<run_path>', so a plain __main__ guard would never fire.
# This dual guard keeps the module importable for tests while still
# running under both direct execution and make shell.
if __name__ in {'__main__', '<run_path>'}:
    email = os.environ.get('EMAIL')
    if not email:
        print(
            'Usage: make shell SCRIPT=scripts/fast_shell/promote_superuser.py '
            'EMAIL=<email>'
        )
        raise SystemExit(1)
    asyncio.run(promote(email))
