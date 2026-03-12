"""Tests for .gitignore filtering in file operations."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from opendev.core.context_engineering.tools.implementations.file_ops import FileOperations


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with .gitignore and sample files."""
    # Create .gitignore
    (tmp_path / ".gitignore").write_text("*.log\nbuild/\nvendor/\n")

    # Create normal files
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "README.md").write_text("# Project\n")

    # Create gitignored files
    (tmp_path / "debug.log").write_text("some log\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "output.js").write_text("compiled\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("vendor code\n")

    # Create subdirectory with its own .gitignore
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.py").write_text("import os\n")
    (sub / ".gitignore").write_text("*.tmp\n")
    (sub / "cache.tmp").write_text("temp data\n")

    return tmp_path


@pytest.fixture
def file_ops(tmp_project):
    """Create FileOperations instance for the temp project."""
    config = MagicMock()
    config.permissions.file_read.is_allowed.return_value = True
    return FileOperations(config, tmp_project)


class TestGlobFilesExcludesGitignored:
    def test_excludes_log_files(self, file_ops, tmp_project):
        results = file_ops.glob_files("**/*")
        names = [Path(r).name for r in results]
        assert "main.py" in names
        assert "README.md" in names
        assert "debug.log" not in names

    def test_excludes_build_directory(self, file_ops):
        results = file_ops.glob_files("**/*.js")
        names = [Path(r).name for r in results]
        assert "output.js" not in names

    def test_excludes_vendor_directory(self, file_ops):
        results = file_ops.glob_files("**/*.py")
        names = [Path(r).name for r in results]
        assert "app.py" in names
        assert "lib.py" not in names


class TestListDirectoryExcludesGitignored:
    def test_excludes_build_and_vendor(self, file_ops, tmp_project):
        tree = file_ops.list_directory(str(tmp_project))
        assert "build" not in tree
        assert "vendor" not in tree
        assert "src" in tree

    def test_excludes_gitignored_files(self, file_ops, tmp_project):
        tree = file_ops.list_directory(str(tmp_project))
        assert "debug.log" not in tree
        assert "main.py" in tree


class TestReadFileWarnsOnGitignored:
    def test_warns_for_gitignored_file(self, file_ops, tmp_project):
        result = file_ops.read_file(str(tmp_project / "debug.log"))
        assert "Note: debug.log is in .gitignore" in result
        # Content is still readable
        assert "some log" in result

    def test_no_warning_for_normal_file(self, file_ops, tmp_project):
        result = file_ops.read_file(str(tmp_project / "main.py"))
        assert "Note:" not in result
        assert "print" in result


class TestPythonGrepExcludesGitignored:
    def test_skips_vendor_files(self, file_ops, tmp_project):
        matches = file_ops._python_grep("vendor code", None, 50, False)
        file_names = [Path(m["file"]).name for m in matches]
        assert "lib.py" not in file_names

    def test_finds_normal_files(self, file_ops, tmp_project):
        matches = file_ops._python_grep("hello", None, 50, False)
        file_names = [Path(m["file"]).name for m in matches]
        assert "main.py" in file_names


class TestNoGitignoreGracefulDegradation:
    def test_all_files_returned_without_gitignore(self, tmp_path):
        # No .gitignore in this directory
        (tmp_path / "file1.py").write_text("content\n")
        (tmp_path / "file2.log").write_text("log\n")

        config = MagicMock()
        ops = FileOperations(config, tmp_path)
        results = ops.glob_files("**/*")
        names = [Path(r).name for r in results]
        assert "file1.py" in names
        assert "file2.log" in names


class TestPathOutsideRepoNotFiltered:
    def test_absolute_path_outside_repo(self, file_ops, tmp_path):
        # Path outside working_dir should not be filtered
        outside = tmp_path / "outside_project"
        assert not file_ops._is_gitignored(outside)


class TestNestedGitignore:
    def test_subdirectory_gitignore_applies(self, file_ops, tmp_project):
        results = file_ops.glob_files("**/*")
        names = [Path(r).name for r in results]
        assert "app.py" in names
        assert "cache.tmp" not in names

    def test_nested_gitignore_in_tree(self, file_ops, tmp_project):
        tree = file_ops.list_directory(str(tmp_project / "src"))
        assert "app.py" in tree
        assert "cache.tmp" not in tree
