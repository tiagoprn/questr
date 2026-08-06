"""Unit tests for the custom architecture linter.

Tests build synthetic project trees under tmp_path and assert on the
run_qtrNNN() entry points directly. No database, no containers.
"""

from pathlib import Path

import pytest

from scripts import lint_custom

FORM_B = 'from questr.infrastructure.orm.models import UserORMModel\n'
FORM_C = 'from questr.infrastructure.orm import models\n'
FORM_A = 'import questr.infrastructure.orm.models\n'


def _write(tree: Path, relpath: str, content: str) -> None:
    target = tree / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')


def _tree(tmp_path: Path) -> Path:
    """Build a synthetic project root containing a questr/ package."""
    root = tmp_path / 'project'
    (root / 'questr').mkdir(parents=True)
    return root


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (FORM_B, 1),
        (FORM_C, 1),
        (FORM_A, 1),
    ],
)
def test_qtr001_flags_orm_imports(tmp_path, source, expected):
    root = _tree(tmp_path)
    _write(root, 'questr/domains/users/service.py', source)
    found = lint_custom.run_qtr001(root)
    assert len(found) == expected
    assert all('QTR001' in violation for violation in found)


def test_qtr001_allows_repository_files(tmp_path):
    root = _tree(tmp_path)
    _write(root, 'questr/domains/users/repository.py', FORM_B)
    assert lint_custom.run_qtr001(root) == []


def test_qtr001_allows_shell_file(tmp_path):
    root = _tree(tmp_path)
    _write(root, 'questr/shell.py', FORM_C)
    assert lint_custom.run_qtr001(root) == []


def test_qtr001_ignores_non_orm_imports(tmp_path):
    root = _tree(tmp_path)
    _write(
        root,
        'questr/domains/users/service.py',
        'from questr.domains.users.repository import User\n',
    )
    assert lint_custom.run_qtr001(root) == []


def test_qtr001_skips_files_outside_questr(tmp_path):
    root = _tree(tmp_path)
    _write(root, 'scripts/whatever.py', FORM_B)
    assert lint_custom.run_qtr001(root) == []


def test_qtr001_ignores_non_python_files(tmp_path):
    root = _tree(tmp_path)
    _write(root, 'questr/notes.txt', FORM_B)
    assert lint_custom.run_qtr001(root) == []


def test_qtr002_flags_cross_domain_import(tmp_path):
    root = _tree(tmp_path)
    _write(
        root,
        'questr/domains/users/service.py',
        'from questr.domains.hello import service\n',
    )
    found = lint_custom.run_qtr002(root)
    assert len(found) == 1
    assert 'QTR002' in found[0]


def test_qtr002_flags_cross_domain_form_a(tmp_path):
    root = _tree(tmp_path)
    source = 'import questr.domains.hello\n'
    _write(root, 'questr/domains/users/service.py', source)
    found = lint_custom.run_qtr002(root)
    assert len(found) == 1


def test_qtr002_allows_same_domain_import(tmp_path):
    root = _tree(tmp_path)
    _write(
        root,
        'questr/domains/users/service.py',
        'from questr.domains.users.repository import User\n',
    )
    assert lint_custom.run_qtr002(root) == []


def test_qtr002_skips_files_outside_domains(tmp_path):
    root = _tree(tmp_path)
    _write(
        root,
        'questr/shell.py',
        'from questr.domains.users.repository import User\n',
    )
    assert lint_custom.run_qtr002(root) == []


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (FORM_B, 1),
        (FORM_C, 1),
        (FORM_A, 1),
    ],
)
def test_qtr003_flags_orm_imports(tmp_path, source, expected):
    root = _tree(tmp_path)
    _write(root, 'scripts/whatever.py', source)
    found = lint_custom.run_qtr003(root)
    assert len(found) == expected
    assert all('QTR003' in violation for violation in found)


def test_qtr003_exempts_fast_shell_init(tmp_path):
    root = _tree(tmp_path)
    _write(root, 'scripts/fast_shell/__init__.py', FORM_B)
    assert lint_custom.run_qtr003(root) == []


def test_qtr003_flags_other_init_files(tmp_path):
    root = _tree(tmp_path)
    _write(root, 'scripts/other_pkg/__init__.py', FORM_B)
    found = lint_custom.run_qtr003(root)
    assert len(found) == 1


def test_qtr003_allows_repository_imports(tmp_path):
    root = _tree(tmp_path)
    _write(
        root,
        'scripts/tool.py',
        'from questr.domains.users.repository import User\n',
    )
    assert lint_custom.run_qtr003(root) == []


def test_qtr003_ignores_non_python_files(tmp_path):
    root = _tree(tmp_path)
    _write(root, 'scripts/notes.txt', FORM_B)
    assert lint_custom.run_qtr003(root) == []


def test_qtr003_main_reports_violations(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    _write(root, 'scripts/whatever.py', FORM_B)
    monkeypatch.setattr(lint_custom, 'PROJECT_ROOT', root)
    assert lint_custom.main() == 1


def test_qtr003_main_clean_tree_exits_zero(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    _write(
        root,
        'scripts/whatever.py',
        'from questr.domains.users.repository import User\n',
    )
    monkeypatch.setattr(lint_custom, 'PROJECT_ROOT', root)
    assert lint_custom.main() == 0
