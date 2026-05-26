# Shell Support

Questr provides an IPython-based interactive shell (similar to `flask shell`)
for running queries against the database. It automatically imports all ORM
models, an open async session, and the application settings.

> **Note on explicit commits:** Unlike `flask shell` which auto-commits
> transparently, this shell requires you to call
> `await session.commit()` explicitly to persist changes.

## What is auto-imported

When the shell starts, the following variables are available in the namespace:

| Variable | Description |
| :-- | :-- |
| `session` | Open `AsyncSession` for executing queries |
| `select` | SQLAlchemy `select()` function |
| `settings` | Application settings (database URL, etc.) |
| `UserORMModel`, `EmailVerificationORMModel`, ... | All ORM model classes (auto-discovered) |

## Usage

### Interactive shell

Open the interactive shell:

```bash
make shell
```

Inside the shell, you can run queries using `await` directly:

```python
result = await session.execute(select(UserORMModel))
users = result.scalars().all()
for user in users:
    print(f'{user.username} - {user.email}')
```

### Script execution

Execute a script non-interactively:

```bash
make shell SCRIPT=scripts/fast_shell/user_orm_sandbox.py
```

Scripts executed via `make shell SCRIPT=<path>` must use `async def main() + asyncio.run()` because IPython's non-interactive script execution does not support top-level `await`.

## Static type-checking for sandbox scripts

The `scripts/fast_shell/` directory contains a `__init__.py` module that
re-exports all ORM models and type declarations statically. This allows
static analysis tools (`ruff`, `ty`) to trace imports and resolve
type information, avoiding false-positive errors for dynamically
injected globals.

### Writing a new sandbox script

New scripts placed under `scripts/fast_shell/` should import from the
package instead of relying on dynamically injected globals:

```python
import asyncio

from scripts.fast_shell import UserORMModel, select, session


async def main():
    result = await session.execute(select(UserORMModel))
    users = result.scalars().all()
    for user in users:
        print(user)


asyncio.run(main())
```

This ensures both `ruff` and `ty` can resolve all names correctly.

## Example script

A sandbox script is available at:

```
scripts/fast_shell/user_orm_sandbox.py
```

This script queries all users and prints their ID, username, email, role,
and status. Run it with:

```bash
make shell SCRIPT=scripts/fast_shell/user_orm_sandbox.py
```