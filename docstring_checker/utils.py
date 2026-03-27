"""Utility functions for analyzing function properties."""

from ast import FunctionDef, AsyncFunctionDef, iter_child_nodes, Return, Yield
from typing import Iterator
from ast import AST


def _walk_excluding_nested_functions(node: AST) -> Iterator[AST]:
    """
    Walk AST nodes, skipping the bodies of nested function definitions.

    Args:
        node (AST): The AST node to walk.

    Returns:
        Iterator[AST]: Each descendant node that is not inside a nested function.
    """
    for child in iter_child_nodes(node):
        if isinstance(child, (FunctionDef, AsyncFunctionDef)):
            continue
        yield child
        yield from _walk_excluding_nested_functions(child)


def function_has_return_value(function: FunctionDef | AsyncFunctionDef) -> bool:
    """
    Check if a function has a return value.

    Args:
        function (FunctionDef | AsyncFunctionDef): The function definition node.

    Returns:
        bool: True if the function has a return value, False otherwise.
    """
    for node in _walk_excluding_nested_functions(function):
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
    return any(isinstance(node, Yield) for node in _walk_excluding_nested_functions(function))


def strip_rich_tags(text: str) -> str:
    """
    Remove Rich markup tags from text and unescape literal brackets.

    Args:
        text (str): Text containing Rich markup tags.

    Returns:
        str: Clean text without Rich markup.
    """
    from re import sub

    text = sub(r"(?<!\\)\[/?[\w_ ]+\]", "", text)
    text = text.replace("\\[", "[").replace("\\]", "]")
    return text
