"""Extract information from function signatures and docstrings."""

from ast import (
    FunctionDef,
    AsyncFunctionDef,
    parse,
    unparse,
    walk as ast_walk,
)
from re import search, match, DOTALL
from typing import Optional


def get_function_args_with_defaults(
    function: FunctionDef | AsyncFunctionDef,
) -> dict[str, dict]:
    """
    Extract argument names, types, and default values from a function definition.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.

    Returns:
        dict[str, dict]: Dictionary with argument names as keys and type/default info as values.
    """
    args = function.args.args
    defaults = function.args.defaults
    num_defaults = len(defaults)
    num_args = len(args)
    args_info = {}
    for i, arg in enumerate(args):
        has_default = i >= num_args - num_defaults
        default_value = None
        if has_default:
            default_node = defaults[i - (num_args - num_defaults)]
            default_value = unparse(default_node)
        arg_type = unparse(arg.annotation) if arg.annotation else None
        args_info[arg.arg] = {
            "type": arg_type,
            "default": default_value,
        }
    return args_info


def extract_args_from_docstring(docstring: str) -> dict[str, str]:
    """
    Extract argument names and types from a docstring.

    Args:
        docstring (str): The docstring to extract from.

    Returns:
        dict[str, str]: Dictionary with argument names as keys and types as values.
    """
    args = {}
    if not docstring:
        return args
    args_section = search(r"Args:\s*(.*?)(\n\n|\Z)", docstring, DOTALL)
    if args_section:
        args_text = args_section.group(1)
        lines = args_text.split("\n")
        for line in lines:
            matches = match(r"\s*(\w+)\s*\(([^)]+)\):", line)
            if matches:
                arg_name, arg_type = matches.groups()
                args[arg_name] = arg_type
    return args


def extract_docstring_arg_order(docstring: str) -> list[str]:
    """
    Extract the order of argument names from a docstring.

    Args:
        docstring (str): The docstring to extract from.

    Returns:
        list[str]: List of argument names in docstring order.
    """
    if not docstring:
        return []
    args = []
    in_args_section = False
    for line in docstring.splitlines():
        line = line.strip()
        if line.lower().startswith("args:"):
            in_args_section = True
            continue
        if in_args_section:
            if not line or not (line[0].isalpha() or line[0] == "_"):
                break
            matches = match(r"(\w+)(?:\s*\([^)]+\))?:", line)
            if matches and matches.group(1) != "self":
                args.append(matches.group(1))
    return args


def extract_return_from_function(
    function: FunctionDef | AsyncFunctionDef,
) -> Optional[str]:
    """
    Extract the return type from a function definition.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.

    Returns:
        Optional[str]: The return type as a string.
    """
    if function.returns:
        return unparse(function.returns)
    return None


def extract_return_from_docstring(docstring: str) -> Optional[str]:
    """
    Extract the return type from a docstring.

    Args:
        docstring (str): The docstring to extract from.

    Returns:
        Optional[str]: The return type as a string, with quotes removed.
    """
    if not docstring:
        return None
    matches = search(r"Returns:\s*\n\s*([^:]+)", docstring)
    if matches:
        return_type = matches.group(1).strip()
        return_type = return_type.strip("'\"")
        return return_type
    return None


def get_functions_from_file(filepath: str) -> list[FunctionDef | AsyncFunctionDef]:
    """
    Parse a Python file and extract all function definitions.

    Args:
        filepath (str): Path to the Python file.

    Returns:
        list[FunctionDef | AsyncFunctionDef]: List of function definition nodes.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    tree = parse(source)
    functions = []
    for node in ast_walk(tree):
        if isinstance(node, (FunctionDef, AsyncFunctionDef)):
            functions.append(node)
    return functions
