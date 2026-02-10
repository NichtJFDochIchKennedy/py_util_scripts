"""Utility functions for analyzing function properties."""

from ast import FunctionDef, AsyncFunctionDef, walk as ast_walk, Return, Yield


def function_has_return_value(function: FunctionDef | AsyncFunctionDef) -> bool:
    """
    Check if a function has a return value.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.

    Returns:
        bool: True if the function has a return value, False otherwise.
    """
    for node in ast_walk(function):
        if isinstance(node, Return) and node.value is not None:
            return True
        if isinstance(node, Yield):
            return True
    return False


def is_generator_function(function: FunctionDef | AsyncFunctionDef) -> bool:
    """
    Check if a function is a generator (uses yield).

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.

    Returns:
        bool: True if the function is a generator, False otherwise.
    """
    return any(isinstance(node, Yield) for node in ast_walk(function))
