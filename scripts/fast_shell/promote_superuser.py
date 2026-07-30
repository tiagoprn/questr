"""Out-of-band superuser promotion script.

Usage:
    make shell SCRIPT=scripts/fast_shell/promote_superuser.py \
        EMAIL=promote@test.com

Promotes a verified, ACTIVE user to SUPERUSER role and writes a
ROLE_GRANTED audit row with actor_id=None (out-of-band marker).
Only ACTIVE users may be promoted out-of-band.
"""

import asyncio
from uuid import uuid7

from scripts.fast_shell import (
    AuditAction,
    AuditLogORMModel,
    UserORMModel,
    UserRole,
    UserStatus,
    select,
    session,
)


async def promote(email: str) -> None:
    """Promote a user to SUPERUSER by email."""
    result = await session.execute(
        select(UserORMModel).where(UserORMModel.email == email)
    )
    user = result.scalar_one_or_none()

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

    old_role = user.role.value
    user.role = UserRole.SUPERUSER

    audit_entry = AuditLogORMModel(
        id=uuid7(),
        action=AuditAction.ROLE_GRANTED,
        actor_id=None,
        target_id=user.id,
        old_role=old_role,
        new_role=UserRole.SUPERUSER.value,
    )
    session.add(audit_entry)

    await session.flush()
    print(
        f'Promoted "{email}" from {old_role} to superuser. '
        f'Audit log id: {audit_entry.id}'
    )


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:  # noqa: PLR2004
        print('Usage: python promote_superuser.py <email>')
        sys.exit(1)

    email = sys.argv[1]
    asyncio.run(promote(email))
