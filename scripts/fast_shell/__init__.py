"""Runtime globals for sandbox scripts.

This module provides type-checkable imports for scripts executed via
`make shell SCRIPT=...` with dynamically injected globals.
"""
from sqlalchemy import select as select
from sqlalchemy.ext.asyncio import AsyncSession

from questr.infrastructure.orm.models import (
    EmailVerificationORMModel as EmailVerificationORMModel,
)
from questr.infrastructure.orm.models import (
    UserORMModel as UserORMModel,
)

session: AsyncSession = None  # ty: ignore
"""The open database session. Populated at runtime by the shell."""
