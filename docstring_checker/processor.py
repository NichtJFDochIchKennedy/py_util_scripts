"""File processing and output generation for docstring checker."""

import ast
import inspect
from ast import get_docstring, FunctionDef, AsyncFunctionDef

from .extractor import (
    get_function_args_with_defaults,
    extract_args_from_docstring,
    extract_return_from_function,
    extract_return_from_docstring,
    get_functions_from_file,
)
from .checker import (
    check_docstring_line_endings,
    check_argument_documentation,
    check_return_type,
    check_argument_order,
)
from .utils import strip_rich_tags


def _get_raw_docstring(function: FunctionDef | AsyncFunctionDef, source: str) -> str | None:
    """
    Extract the raw docstring text from source, preserving escape sequences as literals.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.
        source (str): The full source code of the file.

    Returns:
        str | None: The cleaned raw docstring content, or None if not present.
    """
    if not function.body:
        return None
    first = function.body[0]
    if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)):
        return None
    if not isinstance(first.value.value, str):
        return None
    raw_segment = ast.get_source_segment(source, first.value)
    if raw_segment is None:
        return None
    for delim in ('"""', "'''"):
        if raw_segment.startswith(delim) and raw_segment.endswith(delim) and len(raw_segment) >= len(delim) * 2:
            return inspect.cleandoc(raw_segment[len(delim) : -len(delim)])
    return None


def check_function(function: FunctionDef | AsyncFunctionDef, verbose: bool, source: str = "") -> list[str]:
    """
    Check a function for mismatches between its signature and docstring.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.
        verbose (bool): Whether to include verbose warnings.
        source (str, optional): The full source text of the file.
            Used to extract the raw docstring without interpreting escape sequences. Defaults to empty string.

    Returns:
        list[str]: List of mismatches found.
    """
    mismatches = []
    docstring = get_docstring(function)
    if not docstring:
        mismatches.append("[base_error_color]Function has no docstring.[/base_error_color]")
        return mismatches
    raw_docstring = _get_raw_docstring(function, source) if source else docstring
    mismatches.extend(check_docstring_line_endings(raw_docstring or ""))
    args_info = get_function_args_with_defaults(function)
    doc_args = extract_args_from_docstring(docstring or "")
    mismatches.extend(check_argument_documentation(args_info, doc_args, verbose))
    func_return = extract_return_from_function(function)
    doc_return = extract_return_from_docstring(docstring or "")
    mismatches.extend(check_return_type(function, func_return or "", doc_return or ""))
    mismatches.extend(check_argument_order(function, docstring, verbose))
    return mismatches


def process_file(
    file_path: str,
    ignore_names: list[str],
    verbose: bool,
) -> tuple[int, int, list, list[dict]]:
    """
    Process a single Python file for docstring mismatches.

    Args:
        file_path (str): Path to the Python file.
        ignore_names (list[str]): Function names to ignore.
        verbose (bool): Whether to include verbose output.

    Returns:
        tuple[int, int, list, list[dict]]: function_count, mismatch_count, mismatch panels, structured issues.
    """
    from rich.panel import Panel

    functions, source = get_functions_from_file(file_path)
    mismatches_boxes = []
    file_issues = []
    total_functions = 0
    total_mismatches = 0
    for function in functions:
        if function.name not in ignore_names:
            total_functions += 1
            mismatches = check_function(function, verbose, source)
            if mismatches:
                mismatch_title = (
                    f"[base_color]Function [highlight_color]{function.name}"
                    f"[/highlight_color] [Line[second_highlight_color] "
                    f"{function.lineno}[/second_highlight_color]]:[/base_color]"
                )
                mismatches_text = "\n\n".join(f"    [base_color]-[/base_color] {mismatch}" for mismatch in mismatches)
                total_mismatches += len(mismatches)
                mismatches_boxes.append(
                    Panel(
                        mismatches_text,
                        title=mismatch_title,
                        border_style="yellow",
                        title_align="left",
                    )
                )
                file_issues.append(
                    {
                        "function": function.name,
                        "line": function.lineno,
                        "issues": [strip_rich_tags(m) for m in mismatches],
                    }
                )
    return total_functions, total_mismatches, mismatches_boxes, file_issues
