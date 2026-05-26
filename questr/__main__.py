"""Entry point for `python -m questr`.

This module enables the shell command invocation via `python -m questr`, which
resolves to `questr.shell.main()`.

Why `__main__.py` instead of calling `questr/shell.py` directly?
-----------------------------------------------------------------
Python's `-m` flag runs the `__main__.py` file of a package. Without this
file, `python -m questr` would fail with "Not a package" or would not invoke
the shell at all. The `-m` invocation is used by `make shell` via
`uv run python -m questr.shell`, which internally uses the Python packaging
mechanism to locate and execute the `questr` package.

By placing the entry point in `__main__.py`, we decouple the package's CLI
behavior from its module structure. The actual shell logic lives in
`questr/shell.py` and can be tested independently.
"""

from questr.shell import main

main()
