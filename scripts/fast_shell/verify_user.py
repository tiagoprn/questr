"""Out-of-band user verification (activation) script.

Usage:
    make shell SCRIPT=scripts/fast_shell/verify_user.py \
        EMAIL=verify@test.com

Activates a PENDING user directly in the database (no email click
needed): deletes any existing verification rows, writes a fresh
verification row marked as used (token consumed immediately, no email
is sent), and sets the user status to ACTIVE.
"""

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid7

from questr.common.enums import UserStatus
from questr.domains.users.repository import (
    EmailVerification,
    EmailVerificationRepository,
    UserRepository,
)
from questr.domains.users.service import (
    generate_verification_token,
    get_token_expiry,
)
from scripts.fast_shell import session


async def verify(email: str) -> None:
    """Verify (activate) a PENDING user by email."""
    user_repo = UserRepository(session=session)
    verification_repo = EmailVerificationRepository(session=session)

    user = await user_repo.get_by_email(email)
    if user is None:
        print(f'User with email "{email}" not found.')
        return

    if user.status == UserStatus.ACTIVE:
        print(f'User "{email}" is already ACTIVE.')
        return

    # user_id has a UNIQUE constraint: clear any stale verification row
    # before inserting a fresh one.
    await verification_repo.delete_by_user_id(user.id)

    _, token_hash = generate_verification_token()
    verification = EmailVerification(
        id=uuid7(),
        user_id=user.id,
        token_hash=token_hash,
        expires_at=get_token_expiry(),
        used_at=datetime.now(timezone.utc),
    )
    await verification_repo.create(verification)

    user = await user_repo.update_status(user.id, UserStatus.ACTIVE)
    if user is None:
        print(f'User "{email}" could not be activated.')
        return

    # shell.py does NOT auto-commit; without this the changes roll back
    # when the session closes.
    await session.commit()
    print(f'Activated "{email}". Verification id: {verification.id}')


# NOTE: runpy.run_path (make shell) executes the module with
# __name__ == '<run_path>', so a plain __main__ guard would never fire.
# This dual guard keeps the module importable for tests while still
# running under both direct execution and make shell.
if __name__ in {'__main__', '<run_path>'}:
    email = os.environ.get('EMAIL')
    if not email:
        print(
            'Usage: make shell SCRIPT=scripts/fast_shell/verify_user.py '
            'EMAIL=<email>'
        )
        raise SystemExit(1)
    asyncio.run(verify(email))
