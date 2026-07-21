"""Questr interactive query shell.

Provides an IPython-based interactive shell (similar to flask shell) with
all ORM models, an open async session, and settings pre-imported.

Usage
-----
    make shell                  # interactive mode
    make shell SCRIPT=<path>    # non-interactive script execution

The session is NOT auto-committed. Users must call ``await session.commit()``
explicitly to persist changes.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import runpy
import sys

from sqlalchemy import select as _sa_select
from sqlalchemy.exc import SQLAlchemyError

from questr.infrastructure.orm import models as _orm_models
from questr.infrastructure.orm.base import AsyncSessionLocal, Base
from questr.settings import settings


def _discover_orm_models() -> dict[str, type]:
    """Dynamically discover all ORM model classes in the models module.

    Introspects ``questr.infrastructure.orm.models`` at runtime and returns
    all classes that are subclasses of ``DeclarativeBase`` (excluding Base
    itself). This ensures new models become available automatically.
    """
    return {
        name: obj
        for name, obj in inspect.getmembers(
            _orm_models,
            lambda x: (
                inspect.isclass(x) and issubclass(x, Base) and x is not Base
            ),
        )
    }


def _prepare_namespace(session: object) -> dict[str, object]:
    """Build the user namespace injected into the IPython shell."""
    namespace: dict[str, object] = {
        'session': session,
        'select': _sa_select,
        'settings': settings,
    }
    # Discovered ORM model classes injected by name
    namespace.update(_discover_orm_models())
    return namespace


def _run_interactive(namespace: dict[str, object]) -> None:
    """Launch interactive IPython shell with the provided namespace."""
    import IPython  # noqa: PLC0415  # noqa: PLC0415

    IPython.start_ipython(argv=[], user_ns=namespace)


def _run_script(script_path: str, namespace: dict[str, object]) -> None:
    """Execute a script file non-interactively with the provided namespace.

    Uses ``runpy.run_path`` to provide ``namespace`` as ``init_globals``.
    Scripts must use ``async def`` + ``asyncio.run()`` for async queries,
    since IPython's non-interactive script execution does not support
    top-level ``await``.
    """
    runpy.run_path(script_path, init_globals=namespace)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the shell."""
    parser = argparse.ArgumentParser(description='Questr interactive shell')
    parser.add_argument(
        '--script',
        '-s',
        type=str,
        default=None,
        help='Path to a Python script to execute non-interactively',
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point: parse args, set up session, launch IPython.

    The session is created once and kept open for the entire shell session.
    It is closed after the user exits the shell or the script finishes.
    """
    args = _parse_args()

    session = AsyncSessionLocal()
    # Inject session into the static sandbox module for type checkers
    import scripts.fast_shell as _sf  # noqa: PLC0415

    _sf.session = session
    try:
        namespace = _prepare_namespace(session)
        if args.script:
            _run_script(args.script, namespace)
        else:
            _run_interactive(namespace)
    except KeyboardInterrupt:
        # Ctrl+C pressed — graceful exit
        pass
    except ModuleNotFoundError as exc:
        if exc.name == 'IPython':
            print(
                'IPython is not installed. Run: uv sync',
                file=sys.stderr,
            )
        raise
    except SQLAlchemyError as exc:
        # Database connection errors (OperationalError, InterfaceError, etc.)
        print(
            'Database unreachable. Check your .env settings and ensure '
            f'the database is running. Error: {exc}',
            file=sys.stderr,
        )
        raise
    finally:
        asyncio.run(session.close())


if __name__ == '__main__':
    main()
