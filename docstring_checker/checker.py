"""Validation checks for docstrings and function signatures."""

from ast import AsyncFunctionDef, FunctionDef, get_docstring
from re import DOTALL, findall, search

from .config import GENERATOR_TYPES, SELF_PARAMS
from .extractor import extract_docstring_arg_order
from .utils import function_has_return_value, is_generator_function


def _normalize_type(type_str: str) -> str:
    """
    Normalize type string by removing surrounding quotes (for forward references).

    Args:
        type_str (str): The type string to normalize.

    Returns:
        str: The normalized type string.
    """
    return type_str.strip("\"'")


def _normalize_for_comparison(type_str: str) -> str:
    """
    Normalize type string for comparison: strip quotes, lowercase, remove spaces.

    Args:
        type_str (str): The type string to normalize.

    Returns:
        str: The normalized type string for comparison.
    """
    return _normalize_type(type_str).lower().replace(" ", "")


def check_docstring_line_endings(docstring: str) -> list[str]:
    """
    Check if docstring lines end with proper punctuation.

    Args:
        docstring (str): The docstring to check.

    Returns:
        list[str]: List of formatting errors found.
    """
    mismatches: list[str] = []
    if not docstring:
        return mismatches
    for idx, line in enumerate(docstring.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in ("Args:", "Returns:"):
            if not stripped.endswith(":"):
                mismatches.append(
                    f"[base_error_color]Docstring line {idx + 1} should end with ':' "
                    f"([highlight_error_color]{stripped}[/highlight_error_color])"
                    f"[/base_error_color]"
                )
        elif (
            not stripped.endswith(".")
            and not stripped.endswith(":")
            and not stripped.endswith(",")
            and not stripped.startswith("-")
        ):
            mismatches.append(
                f"[base_error_color]Docstring line {idx + 1} should end with '.' "
                f"([highlight_error_color]{stripped}[/highlight_error_color])"
                f"[/base_error_color]"
            )
    return mismatches


def check_argument_documentation(
    args_info: dict[str, dict],
    doc_args: dict[str, str],
    verbose: bool,
) -> list[str]:
    """
    Check if function arguments are properly documented in the docstring.

    Args:
        args_info (dict[str, dict]): Function arguments with type and default info.
        doc_args (dict[str, str]): Arguments extracted from docstring.
        verbose (bool): Whether to include verbose warnings.

    Returns:
        list[str]: List of argument documentation errors.
    """
    mismatches = []
    for name, info in args_info.items():
        if name in SELF_PARAMS:
            continue
        type_hint = info["type"]
        default = info["default"]
        doc_type = doc_args.get(name)
        if type_hint and doc_type is None:
            mismatches.append(
                f"[base_error_color]Argument [highlight_error_color]{name}"
                f"[/highlight_error_color] has type hint but missing type in docstring.[/base_error_color]"
            )
            continue
        expected_doc_type = f"{type_hint}, optional" if default else type_hint
        if not type_hint:
            if doc_type:
                doc_type_escaped = doc_type.replace("[", r"\[")
                mismatches.append(
                    f"[base_error_color]Argument [highlight_error_color]{name}"
                    f"[/highlight_error_color] has no type, but docstring has "
                    f"[highlight_error_color]{doc_type_escaped}[/highlight_error_color]."
                    f"[/base_error_color]"
                )
            elif verbose:
                mismatches.append(
                    f"[base_error_color]Warning argument [highlight_error_color]{name}"
                    f"[/highlight_error_color] has no type.[/base_error_color]"
                )
            continue
        if not doc_type:
            mismatches.append("[base_error_color]Docstring not found.[/base_error_color]")
            continue
        if not (
            _normalize_for_comparison(doc_type) == _normalize_for_comparison(type_hint)
            or _normalize_for_comparison(doc_type) == _normalize_for_comparison(expected_doc_type)
        ):
            type_hint_escaped = type_hint.replace("[", r"\[")
            doc_type_escaped = doc_type.replace("[", r"\[")
            mismatches.append(
                f"[base_error_color]Argument TypeMismatch [highlight_error_color]{name}"
                f"[/highlight_error_color]:\n{' ' * 8}function: "
                f"[highlight_error_color]{type_hint_escaped}[/highlight_error_color]\n"
                f"{' ' * 8}docstring: [highlight_error_color]{doc_type_escaped}"
                f"[/highlight_error_color][/base_error_color]"
            )
        _check_optional_consistency(name, type_hint, default, doc_type, mismatches)
    return mismatches


def _check_optional_consistency(
    name: str,
    type_hint: str,
    default: str,
    doc_type: str,
    mismatches: list[str],
) -> None:
    """
    Check if optional markers are consistent between type hint and docstring.

    Args:
        name (str): The argument name.
        type_hint (str): The type hint from the function signature.
        default (str): The default value if present.
        doc_type (str): The type from the docstring.
        mismatches (list[str]): List to append errors to.
    """
    if default and "Optional[" in type_hint and ", optional" in doc_type:
        mismatches.append(
            f"[base_error_color]Argument [highlight_error_color]{name}"
            f"[/highlight_error_color] is already optional due to type hint, "
            f"but docstring also contains [highlight_error_color]optional"
            f"[/highlight_error_color].[/base_error_color]"
        )
    elif default and "optional" not in doc_type and "Optional[" not in doc_type:
        mismatches.append(
            f"[base_error_color]Argument [highlight_error_color]{name}"
            f"[/highlight_error_color] has a default value, but "
            f"[highlight_error_color]optional[/highlight_error_color] is missing "
            f"in the docstring.[/base_error_color]"
        )
    elif not default and "Optional[" in doc_type:
        mismatches.append(
            f"[base_error_color]Argument [highlight_error_color]{name}"
            f"[/highlight_error_color] has NO default value, but the docstring "
            f"contains [highlight_error_color]Optional[]"
            f"[/highlight_error_color].[/base_error_color]"
        )
    elif not default and "optional" in doc_type:
        mismatches.append(
            f"[base_error_color]Argument [highlight_error_color]{name}"
            f"[/highlight_error_color] has NO default value, but the docstring "
            f"contains [highlight_error_color]optional[/highlight_error_color]."
            f"[/base_error_color]"
        )


def _check_generator_return(
    func_return: str,
    doc_return: str,
    mismatches: list[str],
) -> None:
    """
    Check generator function return types.

    Args:
        func_return (str): Return type from function signature.
        doc_return (str): Return type from docstring.
        mismatches (list[str]): List to append errors to.
    """
    is_valid_generator_type = func_return in GENERATOR_TYPES or (func_return and func_return.startswith("Iterator"))
    if not is_valid_generator_type:
        mismatches.append(
            f"[base_error_color]Function is a generator (uses yield), but return "
            f"type is [highlight_error_color]{func_return}[/highlight_error_color]."
            f"[/base_error_color]"
        )
    if doc_return and _normalize_for_comparison(func_return) != _normalize_for_comparison(doc_return):
        func_return_escaped = func_return.replace("[", r"\[")
        doc_return_escaped = doc_return.replace("[", r"\[")
        mismatches.append(
            f"[base_error_color]Return TypeMismatch:\n{' ' * 8}function:  "
            f"[highlight_error_color]{func_return_escaped}[/highlight_error_color]\n"
            f"{' ' * 8}docstring: [highlight_error_color]{doc_return_escaped}"
            f"[/highlight_error_color][/base_error_color]"
        )
    elif not doc_return:
        mismatches.append(
            f"[base_error_color]Generator return-type "
            f"[highlight_error_color]{func_return}[/highlight_error_color] "
            f"not in docstring.[/base_error_color]"
        )


def _check_regular_return(
    has_return: bool,
    func_return: str,
    doc_return: str,
    mismatches: list[str],
) -> None:
    """
    Check regular (non-generator) function return types.

    Args:
        has_return (bool): Whether the function has a return statement.
        func_return (str): Return type from function signature.
        doc_return (str): Return type from docstring.
        mismatches (list[str]): List to append errors to.
    """
    if has_return and func_return == "None":
        mismatches.append(
            "[base_error_color]Function has a return value, but no return type " "is specified.[/base_error_color]"
        )
    elif not has_return and func_return != "None":
        mismatches.append(
            f"[base_error_color]Function has no return value, but the return type "
            f"is [highlight_error_color]{func_return}[/highlight_error_color]."
            f"[/base_error_color]"
        )
    elif func_return and doc_return and _normalize_for_comparison(func_return) != _normalize_for_comparison(doc_return):
        func_return_escaped = func_return.replace("[", r"\[")
        doc_return_escaped = doc_return.replace("[", r"\[")
        mismatches.append(
            f"[base_error_color]Return TypeMismatch:\n{' ' * 8}function:  "
            f"[highlight_error_color]{func_return_escaped}[/highlight_error_color]\n"
            f"{' ' * 8}docstring: [highlight_error_color]{doc_return_escaped}"
            f"[/highlight_error_color][/base_error_color]"
        )
    elif func_return and not doc_return and func_return != "None":
        mismatches.append(
            f"[base_error_color]Return-type [highlight_error_color]{func_return}"
            f"[/highlight_error_color] not in docstring.[/base_error_color]"
        )


def check_return_type(
    function: FunctionDef | AsyncFunctionDef,
    func_return: str,
    doc_return: str,
) -> list[str]:
    """
    Check if function return type matches the docstring.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition.
        func_return (str): Return type from function signature.
        doc_return (str): Return type from docstring.

    Returns:
        list[str]: List of return type errors.
    """
    mismatches = []
    has_return = function_has_return_value(function)
    if not func_return:
        mismatches.append("[base_error_color]Function has no return type.[/base_error_color]")
        return mismatches
    if is_generator_function(function):
        _check_generator_return(func_return, doc_return, mismatches)
    else:
        _check_regular_return(has_return, func_return, doc_return, mismatches)
    return mismatches


def check_argument_order(
    function: FunctionDef | AsyncFunctionDef,
    docstring: str,
    verbose: bool,
) -> list[str]:
    """
    Check if function arguments order matches docstring order.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition.
        docstring (str): The function's docstring.
        verbose (bool): Whether to report order mismatches.

    Returns:
        list[str]: List of order mismatch errors.
    """
    mismatches: list[str] = []
    if not verbose or not docstring:
        return mismatches
    func_args = [arg.arg for arg in function.args.args if arg.arg != "self"]
    doc_args = extract_docstring_arg_order(docstring)
    if func_args != doc_args:
        mismatches.append(
            f"[base_error_color]Function arguments order does not match "
            f"docstring arguments order:\n{' ' * 8}function:  "
            f"[highlight_error_color]{func_args}[/highlight_error_color]\n"
            f"{' ' * 8}docstring: [highlight_error_color]{doc_args}"
            f"[/highlight_error_color][/base_error_color]"
        )
    return mismatches


def check_docstring_indentation(
    function: FunctionDef | AsyncFunctionDef,
    source: str,
) -> list[str]:
    """
    Check that the docstring indentation is consistent with the function body.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.
        source (str): The full source code of the file.

    Returns:
        list[str]: List of indentation errors found.
    """
    mismatches: list[str] = []
    if not function.body:
        return mismatches
    first_stmt = function.body[0]
    if not hasattr(first_stmt, "value") or not isinstance(getattr(first_stmt, "value", None), type(first_stmt)):
        pass
    docstring = get_docstring(function)
    if not docstring:
        return mismatches

    source_lines = source.splitlines()
    func_indent = function.col_offset
    expected_indent = func_indent + 4

    # Find the docstring lines in the source
    ds_node = function.body[0]
    ds_start = ds_node.lineno - 1
    ds_end = (ds_node.end_lineno or ds_node.lineno) - 1
    for line_idx in range(ds_start, min(ds_end + 1, len(source_lines))):
        line = source_lines[line_idx]
        if not line.strip():
            continue
        stripped = line.lstrip()

        # Skip the triple-quote lines themselves
        if stripped.startswith('"""') or stripped.startswith("'''"):
            actual_indent = len(line) - len(stripped)
            if actual_indent != expected_indent:
                mismatches.append(
                    f"[base_error_color]Docstring line {line_idx + 1} has "
                    f"[highlight_error_color]{actual_indent}[/highlight_error_color] spaces indent, "
                    f"expected [highlight_error_color]{expected_indent}[/highlight_error_color]."
                    f"[/base_error_color]"
                )
            continue
        actual_indent = len(line) - len(stripped)
        if actual_indent < expected_indent:
            mismatches.append(
                f"[base_error_color]Docstring line {line_idx + 1} has "
                f"[highlight_error_color]{actual_indent}[/highlight_error_color] spaces indent, "
                f"expected at least [highlight_error_color]{expected_indent}[/highlight_error_color]."
                f"[/base_error_color]"
            )
    return mismatches


def check_tuple_breakdown(
    args_info: dict[str, dict],
    docstring: str,
    func_return: str,
) -> list[str]:
    """
    Check that tuple types in args and return are broken down in the docstring.

    Args:
        args_info (dict[str, dict]): Function arguments with type and default info.
        docstring (str): The function's docstring.
        func_return (str): Return type from function signature.

    Returns:
        list[str]: List of tuple breakdown errors found.
    """
    mismatches: list[str] = []
    if not docstring:
        return mismatches

    def _count_tuple_elements(type_str: str) -> int:
        """
        Count the number of elements in a tuple type annotation.

        Args:
            type_str (str): The tuple type string, e.g. "Tuple[int, string]".

        Returns:
            int: The number of elements in the tuple, or 0 if it's not a valid tuple type.
        """
        m = search(r"tuple\[(.+)\]", type_str, DOTALL)
        if not m:
            return 0
        inner = m.group(1)

        # Simple comma split respecting bracket nesting
        depth = 0
        count = 1
        for ch in inner:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "," and depth == 0:
                count += 1
        return count

    def _check_breakdown_present(type_str: str, name: str, section: str) -> None:
        """
        Verify that the docstring has sub-type lines for the tuple elements.

        Args:
            type_str (str): The tuple type string to check.
            name (str): The argument name (empty for return type).
            section (str): "arg" for arguments, "return" for return type.
        """
        normalized = type_str.lower().replace(" ", "")
        if not normalized.startswith("tuple["):
            return
        num_elements = _count_tuple_elements(type_str)
        if num_elements < 2:
            return

        # Look for the section in the docstring to check for sub-type breakdown lines
        if section == "return":
            sec_match = search(r"Returns:\s*\n\s*[^\n]+\n(.*?)(\n\n|\Z)", docstring, DOTALL)
        else:
            # For args, search after the arg line
            pattern = rf"{name}\s*\([^)]*\):[^\n]*\n((?:\s+[^\s].*\n?)*)"
            sec_match = search(pattern, docstring, DOTALL)
        if sec_match:
            breakdown_text = sec_match.group(1)

            # Count sub-type lines (lines matching "type: description" pattern)
            sub_lines = findall(r"^\s+\w[\w\[\], |]*:", breakdown_text, flags=8)  # MULTILINE=8
            if len(sub_lines) >= num_elements:
                return

        type_escaped = type_str.replace("[", r"\[")
        mismatches.append(
            f"[base_error_color]{section.capitalize()} "
            f"[highlight_error_color]{name if section == 'arg' else ''}"
            f"[/highlight_error_color] has tuple type "
            f"[highlight_error_color]{type_escaped}[/highlight_error_color] "
            f"but the docstring does not break down all {num_elements} elements."
            f"[/base_error_color]"
        )

    # Check arguments
    for name, info in args_info.items():
        if name in SELF_PARAMS:
            continue
        type_hint = info["type"]
        if type_hint:
            _check_breakdown_present(type_hint, name, "arg")

    # Check return type
    if func_return:
        _check_breakdown_present(func_return, "", "return")
    return mismatches
