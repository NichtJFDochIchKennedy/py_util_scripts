"""Validation checks for docstrings and function signatures."""

from ast import FunctionDef, AsyncFunctionDef
from typing import Optional

from config import SELF_PARAMS, GENERATOR_TYPES
from extractor import extract_docstring_arg_order
from utils import function_has_return_value, is_generator_function


def _normalize_type(type_str: str) -> str:
    """
    Normalize type string by removing surrounding quotes (for forward references).

    Args:
        type_str (str): The type string to normalize.

    Returns:
        str: The normalized type string.
    """
    return type_str.strip("\"'")


def check_docstring_line_endings(docstring: str) -> list[str]:
    """
    Check if docstring lines end with proper punctuation.

    Args:
        docstring (str): The docstring to check.

    Returns:
        list[str]: List of formatting errors found.
    """
    mismatches = []
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
        elif not stripped.endswith(".") and not stripped.endswith(":") and not stripped.startswith("-"):
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
                mismatches.append(
                    f"[base_error_color]Argument [highlight_error_color]{name}"
                    f"[/highlight_error_color] has no type, but docstring has "
                    f"[highlight_error_color]{doc_type}[/highlight_error_color]."
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
        if not (doc_type == type_hint or doc_type == expected_doc_type):
            mismatches.append(
                f"[base_error_color]Argument TypeMismatch [highlight_error_color]{name}"
                f"[/highlight_error_color]:\n{' ' * 8}function: "
                f"[highlight_error_color]{type_hint}[/highlight_error_color]\n"
                f"{' ' * 8}docstring: [highlight_error_color]{doc_type}"
                f"[/highlight_error_color][/base_error_color]"
            )
        _check_optional_consistency(name, type_hint, default, doc_type, mismatches)
    return mismatches


def _check_optional_consistency(
    name: str,
    type_hint: str,
    default: Optional[str],
    doc_type: str,
    mismatches: list[str],
) -> None:
    """
    Check if optional markers are consistent between type hint and docstring.

    Args:
        name (str): The argument name.
        type_hint (str): The type hint from the function signature.
        default (Optional[str]): The default value if present.
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
    elif default and "optional" not in doc_type:
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
    doc_return: Optional[str],
    mismatches: list[str],
) -> None:
    """
    Check generator function return types.

    Args:
        func_return (str): Return type from function signature.
        doc_return (Optional[str]): Return type from docstring.
        mismatches (list[str]): List to append errors to.
    """
    is_valid_generator_type = func_return in GENERATOR_TYPES or (func_return and func_return.startswith("Iterator"))
    if not is_valid_generator_type:
        mismatches.append(
            f"[base_error_color]Function is a generator (uses yield), but return "
            f"type is [highlight_error_color]{func_return}[/highlight_error_color]."
            f"[/base_error_color]"
        )
    if doc_return and _normalize_type(func_return) != _normalize_type(doc_return):
        mismatches.append(
            f"[base_error_color]Return TypeMismatch:\n{' ' * 8}function:  "
            f"[highlight_error_color]{func_return}[/highlight_error_color]\n"
            f"{' ' * 8}docstring: [highlight_error_color]{doc_return}"
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
    doc_return: Optional[str],
    mismatches: list[str],
) -> None:
    """
    Check regular (non-generator) function return types.

    Args:
        has_return (bool): Whether the function has a return statement.
        func_return (str): Return type from function signature.
        doc_return (Optional[str]): Return type from docstring.
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
    elif func_return and doc_return and _normalize_type(func_return) != _normalize_type(doc_return):
        func_return_escaped = func_return.replace("[", r"\[").replace("]", r"\]")
        doc_return_escaped = doc_return.replace("[", r"\[").replace("]", r"\]")
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
    func_return: Optional[str],
    doc_return: Optional[str],
) -> list[str]:
    """
    Check if function return type matches the docstring.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition.
        func_return (Optional[str]): Return type from function signature.
        doc_return (Optional[str]): Return type from docstring.

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
    docstring: Optional[str],
    verbose: bool,
) -> list[str]:
    """
    Check if function arguments order matches docstring order.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition.
        docstring (Optional[str]): The function's docstring.
        verbose (bool): Whether to report order mismatches.

    Returns:
        list[str]: List of order mismatch errors.
    """
    mismatches = []
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
