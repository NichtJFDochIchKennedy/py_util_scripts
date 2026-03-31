"""Docstring Checker - Validates consistency between function signatures and their docstrings."""

from .__main__ import main
from .formatter import fix_file, format_file_docstrings
from .processor import check_function, process_file

__all__ = ["check_function", "fix_file", "format_file_docstrings", "main", "process_file"]
