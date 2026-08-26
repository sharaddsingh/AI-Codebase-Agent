"""Ignore rules: built-in deny-list and .gitignore."""

from __future__ import annotations

from pathlib import Path

from code_intelligence.ignore import IgnoreRules


def test_default_ignored_dirs() -> None:
    rules = IgnoreRules()
    assert rules.is_ignored_dir_name("node_modules")
    assert rules.is_ignored_dir_name(".git")
    assert rules.is_ignored_dir_name("__pycache__")
    assert not rules.is_ignored_dir_name("app")


def test_ignored_paths() -> None:
    rules = IgnoreRules()
    assert rules.is_ignored("node_modules", is_dir=True)
    assert rules.is_ignored("node_modules/leftpad/index.js", is_dir=False)
    assert rules.is_ignored("app/__pycache__/x.pyc", is_dir=False)
    assert rules.is_ignored("bundle.min.js", is_dir=False)
    assert rules.is_ignored("package-lock.json", is_dir=False)
    assert not rules.is_ignored("app/main.py", is_dir=False)
    assert not rules.is_ignored("", is_dir=True)  # root


def test_gitignore_respected(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.secret\nbuildme/\n")
    (tmp_path / "buildme").mkdir()
    rules = IgnoreRules.for_root(tmp_path, respect_gitignore=True)
    assert rules.is_ignored("creds.secret", is_dir=False)
    assert rules.is_ignored("buildme", is_dir=True)
    assert not rules.is_ignored("keep.py", is_dir=False)


def test_gitignore_can_be_disabled(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.secret\n")
    rules = IgnoreRules.for_root(tmp_path, respect_gitignore=False)
    assert not rules.is_ignored("creds.secret", is_dir=False)
