"""Docstring Checker - Validates consistency between function signatures and their docstrings."""

from .processor import check_function, process_file
from .formatter import fix_file, format_file_docstrings

__all__ = ["check_function", "process_file", "fix_file", "format_file_docstrings"]
