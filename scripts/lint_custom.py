"""Custom lint rules for the Questr codebase.

Usage:
    uv run python scripts/lint_custom.py

Exit code:
    0 -- no violations
    1 -- violations found

Scope:
    QTR001 and QTR002 scan the production package (``questr/``) only. The
    ``tests/`` tree is intentionally out of scope: factory-boy factories
    legitimately import ORM models (per docs/backend/coding-guidelines.md),
    and enforcing QTR001 there would contradict that guideline. QTR002 (no
    cross-domain imports) likewise applies to production modules only.

    QTR003 scans ``scripts/`` only: operational tooling must go through the
    repository layer just like production code. The sole exemption is the
    fast_shell namespace package (see QTR003_EXEMPT below).

QTR001 filename exemptions (allowed to import ORM models):
    - ``repository.py`` -- domain persistence boundary (canonical case).
    - ``shell.py``      -- developer query shell; imports the ORM ``models``
                           module to expose model classes in the interactive
                           namespace, not domain code. See questr/shell.py.

QTR003 exemptions (allowed to import ORM models in scripts/):
    - ``scripts/fast_shell/__init__.py`` -- shell script namespace; re-exports
      ORM models for ``make shell`` script execution, mirroring the
      ``shell.py`` exemption. When running interactively we may need to
      access the ORM models directly. Add other exemptions to QTR003_EXEMPT
      with a documented reason.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _walk_py_files(root: Path) -> list[Path]:
    """Walk a directory tree and return all .py files."""
    return [p for p in root.rglob('*.py') if p.is_file()]


# ── QTR001: No ORM model imports outside repository files ────────────


def _check_qtr001(root: Path, filepath: Path) -> list[str]:
    """Check that ORM models are only imported in repository.py files."""
    violations: list[str] = []
    rel = filepath.relative_to(root)
    filename = filepath.name

    if filename.endswith('repository.py') or filename == 'shell.py':
        return violations

    try:
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ''
            # Form B: from questr.infrastructure.orm.models import X
            if 'infrastructure.orm.models' in module:
                violations.append(
                    f'{rel}:{node.lineno}: QTR001 '
                    f'ORM model import in non-repository file'
                )
            # Form C: from questr.infrastructure.orm import models
            elif module.endswith('infrastructure.orm') and any(
                alias.name == 'models' for alias in node.names
            ):
                violations.append(
                    f'{rel}:{node.lineno}: QTR001 '
                    f'ORM model module import in non-repository file'
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if 'infrastructure.orm.models' in alias.name:
                    violations.append(
                        f'{rel}:{node.lineno}: QTR001 '
                        f'ORM model import in non-repository file'
                    )
    return violations


def run_qtr001(root: Path) -> list[str]:
    """Run QTR001 check across all Python files."""
    all_violations: list[str] = []
    for filepath in _walk_py_files(root / 'questr'):
        all_violations.extend(_check_qtr001(root, filepath))
    return all_violations


# ── QTR002: No cross-domain imports between domain modules ───────────


# PLR0912: AST-node branches are inherent to a rule-walking linter
def _check_qtr002(root: Path, filepath: Path) -> list[str]:  # noqa: PLR0912
    """Check that domain modules don't import from other domains."""
    violations: list[str] = []
    rel = filepath.relative_to(root)

    # Only check files inside questr/domains/
    try:
        parts = rel.parts
    except ValueError:
        return violations

    if not any(p == 'domains' for p in parts) or not parts[-1].endswith('.py'):
        return violations

    # Determine which domain this file belongs to
    # e.g. questr/domains/users/service.py -> 'users'
    try:
        domains_idx = parts.index('domains')
        if domains_idx + 1 >= len(parts):
            return violations
        owning_domain = parts[domains_idx + 1]
    except ValueError, IndexError:
        return violations

    try:
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
    except SyntaxError:
        return violations

    # PLR1702: AST-node nesting is inherent to the rule-walking linter
    for node in ast.walk(tree):  # noqa: PLR1702
        if isinstance(node, ast.ImportFrom):
            if node.module and 'questr.domains' in node.module:
                # Extract the domain being imported from
                module_parts = node.module.split('.')
                try:
                    domains_idx = module_parts.index('domains')
                    if domains_idx + 1 < len(module_parts):
                        imported_domain = module_parts[domains_idx + 1]
                        if imported_domain != owning_domain:
                            violations.append(
                                f'{rel}:{node.lineno}: QTR002 '
                                f'Cross-domain import: '
                                f'{owning_domain} → {imported_domain}'
                            )
                except ValueError:
                    continue
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if 'questr.domains' in alias.name:
                    module_parts = alias.name.split('.')
                    try:
                        domains_idx = module_parts.index('domains')
                        if domains_idx + 1 < len(module_parts):
                            imported_domain = module_parts[domains_idx + 1]
                            if imported_domain != owning_domain:
                                violations.append(
                                    f'{rel}:{node.lineno}: QTR002 '
                                    f'Cross-domain import: '
                                    f'{owning_domain} → {imported_domain}'
                                )
                    except ValueError:
                        continue
    return violations


def run_qtr002(root: Path) -> list[str]:
    """Run QTR002 check across all Python files."""
    all_violations: list[str] = []
    for filepath in _walk_py_files(root / 'questr'):
        all_violations.extend(_check_qtr002(root, filepath))
    return all_violations


# ── QTR003: No ORM model imports in scripts/ ─────────────────────────


# Exact relative paths exempt from QTR003. Only the fast_shell namespace
# qualifies: it re-exports ORM models for `make shell` script execution,
# mirroring the questr/shell.py exemption in QTR001. When running
# interactively we may need to access the ORM models directly. To exempt
# another script, add its exact relative path here and document the
# reason in the relevant docs (e.g. docs/backend/shell.md).
QTR003_EXEMPT = frozenset({'scripts/fast_shell/__init__.py'})


def _check_qtr003(root: Path, filepath: Path) -> list[str]:
    """Check that scripts don't import ORM models directly."""
    violations: list[str] = []
    rel = filepath.relative_to(root)

    if rel.as_posix() in QTR003_EXEMPT:
        return violations

    try:
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ''
            # Form B: from questr.infrastructure.orm.models import X
            if 'infrastructure.orm.models' in module:
                violations.append(
                    f'{rel}:{node.lineno}: QTR003 '
                    f'ORM model import in scripts/ file'
                )
            # Form C: from questr.infrastructure.orm import models
            elif module.endswith('infrastructure.orm') and any(
                alias.name == 'models' for alias in node.names
            ):
                violations.append(
                    f'{rel}:{node.lineno}: QTR003 '
                    f'ORM model module import in scripts/ file'
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if 'infrastructure.orm.models' in alias.name:
                    violations.append(
                        f'{rel}:{node.lineno}: QTR003 '
                        f'ORM model import in scripts/ file'
                    )
    return violations


def run_qtr003(root: Path) -> list[str]:
    """Run QTR003 check across all Python files in scripts/."""
    all_violations: list[str] = []
    for filepath in _walk_py_files(root / 'scripts'):
        all_violations.extend(_check_qtr003(root, filepath))
    return all_violations


# ── Main ──────────────────────────────────────────────────────────────


def main() -> int:
    root = PROJECT_ROOT
    exit_code = 0

    print('QTR001: Checking ORM imports outside repository files...')
    violations_qtr001 = run_qtr001(root)
    if violations_qtr001:
        print('\n'.join(violations_qtr001))
        print(f'QTR001: {len(violations_qtr001)} violation(s) found')
        exit_code = 1
    else:
        print('QTR001: OK')

    print()
    print('QTR003: Checking ORM imports in scripts/...')
    violations_qtr003 = run_qtr003(root)
    if violations_qtr003:
        print('\n'.join(violations_qtr003))
        print(f'QTR003: {len(violations_qtr003)} violation(s) found')
        exit_code = 1
    else:
        print('QTR003: OK')

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
