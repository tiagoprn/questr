"""Custom lint rules for the Questr codebase.

Usage:
    uv run python scripts/lint_custom.py

Exit code:
    0 — no violations
    1 — violations found
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _walk_py_files(root: Path) -> list[Path]:
    """Walk a directory tree and return all .py files."""
    return [p for p in root.rglob('*.py') if p.is_file()]


# ── QTR001: No ORM model imports outside repository files ────────────


def _check_qtr001(filepath: Path) -> list[str]:
    """Check that ORM models are only imported in repository.py files."""
    violations: list[str] = []
    rel = filepath.relative_to(PROJECT_ROOT)
    filename = filepath.name

    if filename.endswith('repository.py') or filename.endswith(
        'test_repository.py'
    ):
        return violations

    try:
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and 'infrastructure.orm.models' in node.module:
                violations.append(
                    f'{rel}:{node.lineno}: QTR001 '
                    f'ORM model import in non-repository file'
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
        all_violations.extend(_check_qtr001(filepath))
    return all_violations


# ── QTR002: No cross-domain imports between domain modules ───────────


def _check_qtr002(filepath: Path) -> list[str]:
    """Check that domain modules don't import from other domains."""
    violations: list[str] = []
    rel = filepath.relative_to(PROJECT_ROOT)

    # Only check files inside questr/domains/
    try:
        parts = rel.parts
    except ValueError:
        return violations

    if not any(p == 'domains' for p in parts) or not parts[-1].endswith(
        '.py'
    ):
        return violations

    # Determine which domain this file belongs to
    # e.g. questr/domains/users/service.py -> 'users'
    try:
        domains_idx = parts.index('domains')
        if domains_idx + 1 >= len(parts):
            return violations
        owning_domain = parts[domains_idx + 1]
    except (ValueError, IndexError):
        return violations

    try:
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
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
        all_violations.extend(_check_qtr002(filepath))
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
    print('QTR002: Checking cross-domain imports...')
    violations_qtr002 = run_qtr002(root)
    if violations_qtr002:
        print('\n'.join(violations_qtr002))
        print(f'QTR002: {len(violations_qtr002)} violation(s) found')
        exit_code = 1
    else:
        print('QTR002: OK')

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
