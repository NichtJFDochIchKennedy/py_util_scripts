"""File processing and output generation for docstring checker."""

from ast import get_docstring, FunctionDef, AsyncFunctionDef

from extractor import (
    get_function_args_with_defaults,
    extract_args_from_docstring,
    extract_return_from_function,
    extract_return_from_docstring,
    get_functions_from_file,
)
from checker import (
    check_docstring_line_endings,
    check_argument_documentation,
    check_return_type,
    check_argument_order,
)


def check_function(function: FunctionDef | AsyncFunctionDef, verbose: bool) -> list[str]:
    """
    Check a function for mismatches between its signature and docstring.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.
        verbose (bool): Whether to include verbose warnings.

    Returns:
        list[str]: List of mismatches found.
    """
    mismatches = []
    docstring = get_docstring(function)
    mismatches.extend(check_docstring_line_endings(docstring))
    args_info = get_function_args_with_defaults(function)
    doc_args = extract_args_from_docstring(docstring)
    mismatches.extend(check_argument_documentation(args_info, doc_args, verbose))
    func_return = extract_return_from_function(function)
    doc_return = extract_return_from_docstring(docstring)
    mismatches.extend(check_return_type(function, func_return, doc_return))
    if docstring:
        mismatches.extend(check_argument_order(function, docstring, verbose))
    return mismatches


def process_file(
    file_path: str,
    ignore_names: list[str],
    verbose: bool,
) -> tuple[int, int, list]:
    """
    Process a single Python file for docstring mismatches.

    Args:
        file_path (str): Path to the Python file.
        ignore_names (list[str]): Function names to ignore.
        verbose (bool): Whether to include verbose output.

    Returns:
        tuple: (function_count, mismatch_count, list of mismatch panels)
    """
    from rich.panel import Panel

    functions = get_functions_from_file(file_path)
    mismatches_boxes = []
    total_functions = 0
    total_mismatches = 0
    for function in functions:
        if function.name not in ignore_names:
            total_functions += 1
            mismatches = check_function(function, verbose)
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
    return total_functions, total_mismatches, mismatches_boxes
