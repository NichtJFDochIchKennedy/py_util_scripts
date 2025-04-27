# **py_util_scripts**

A collection of small Python utility scripts for code quality checks, analysis, and automation.

## Available Scripts

### 1. [docstring_checker.py](docstring_checker.py)

Checks all .py files in given directories recursively (excludes `venv` and `test`) and verifies:

- If function parameter names and types match between code and docstrings (Google-style expected).
- If the return type annotation matches the Returns: section in the docstring.
- If parameters with default values are correctly marked as "optional" in the docstring.
- If inconsistencies are found, detailed mismatch reports are printed.

Script options:
- -f List of files to ignore.
- -n List of function names to ignore.

Example usage:

```bash
py .\docstring_checker.py ..\project_dir -f file.py -n func
```

Useful for maintaining consistent and reliable documentation across a Python project.

### 2. [row_counter.py](row_counter.py)

Counts all lines in given directories recursively (excludes `venv`):

- Outputs:
    - Code percentage
    - Code to space ratio
    - Total empty lines
    - Total code lines in all directories

Script options:
- -v Provides percentage and filled line to total line ratio for each file.
- -e List of file extensions to count.

Example usage:

```bash
py .\row_counter.py ..\project_dir -e py -v
```

Useful for getting a quick overview of project size and structure.

## Requirements

- Python 3.8+
- No external dependencies