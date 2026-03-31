"""Auto-formatter for docstring quote-placement style."""

import ast
import inspect
from pathlib import Path
from re import match as re_match

LINE_LENGTH = 120


def _collect_docstring_entries(tree: ast.AST, source: str) -> list[tuple[ast.Constant, str]]:
    """
    Collect all docstring Constant AST nodes together with their cleaned content.

    Args:
        tree (ast.AST): Parsed module AST.
        source (str): The original source code text.

    Returns:
    list[tuple[ast.Constant, str]]: List of (constant node, clean content) pairs.
    """
    entries: list[tuple[ast.Constant, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.body:
                continue
            first = node.body[0]
            if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)):
                continue
            if not isinstance(first.value.value, str):
                continue
            raw_segment = ast.get_source_segment(source, first.value)
            if raw_segment is None:
                continue
            content = None
            for delim in ('"""', "'''"):
                if raw_segment.startswith(delim) and raw_segment.endswith(delim) and len(raw_segment) >= len(delim) * 2:
                    content = raw_segment[len(delim) : -len(delim)]
                    break
            if content is None:
                continue
            content = inspect.cleandoc(content)
            entries.append((first.value, content))
    return entries


def _normalize_block_spacing(lines: list[str]) -> list[str]:
    """
    Normalize spacing between docstring blocks (description, Args, Returns).

    Args:
        lines (list[str]): The docstring content lines.

    Returns:
        list[str]: Lines with normalized spacing between blocks.
    """
    if not lines:
        return lines

    result: list[str] = []
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped in ("Args:", "Returns:"):
            while result and not result[-1].strip():
                result.pop()
            if result:
                result.append("")
            result.append(lines[i])
        else:
            result.append(lines[i])
        i += 1
    return result


def _normalize_docstring_structure(lines: list[str], outer_indent: str) -> list[str]:
    """
    Normalize the indentation structure of docstring content.

    Rules:
    - Description text, ``Args:``, ``Returns:`` are at base level (outer_indent).
    - Lines inside Args/Returns blocks are indented +4 from base.
    - Continuation lines (long descriptions that wrap) are indented +8 from base.
    - Further continuation lines stay at +8 (no additional indent).

    Args:
        lines (list[str]): The docstring content lines (from inspect.cleandoc, relative indent).
        outer_indent (str): The base indentation string for the docstring body.

    Returns:
        list[str]: Lines with corrected indentation structure.
    """
    result: list[str] = []
    base = outer_indent
    section_indent = base + "    "
    continuation_indent = base + "        "
    in_section = False
    is_param_line = False

    # Pattern for parameter/type lines: "name (type): desc" or "type: desc" (incl. brackets)
    param_pattern = r"\w[\w\[\], |]*\s*(\([^)]*\))?\s*:"

    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            in_section = False
            is_param_line = False
            continue
        if stripped in ("Args:", "Returns:", "Yields:", "Raises:", "Note:", "Notes:", "Attributes:", "Examples:"):
            result.append(f"{base}{stripped}")
            in_section = True
            is_param_line = False
            continue
        if in_section:
            if re_match(param_pattern, stripped):
                result.append(f"{section_indent}{stripped}")
                is_param_line = True
                continue
            if is_param_line:
                result.append(f"{continuation_indent}{stripped}")
                continue
        result.append(f"{base}{stripped}")

    return result


def _build_formatted_docstring(content: str, indent: str) -> str:
    """
    Build the correctly formatted docstring string (including triple-quotes).

    Args:
        content (str): The cleaned docstring content (as returned by ast.get_docstring).
        indent (str): Whitespace string matching the column offset of the opening quotes.

    Returns:
        str: The formatted docstring including triple-quote delimiters.
    """
    lines = content.splitlines()
    lines = [line.rstrip() for line in lines]
    lines = _normalize_block_spacing(lines)
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return '""""""'

    if len(lines) == 1:
        return f'"""{lines[0]}"""'

    body_lines = _normalize_docstring_structure(lines, indent)
    inner = "\n".join(body_lines)
    return f'"""\n{inner}\n{indent}"""'


def format_file_docstrings(source: str) -> str:
    """
    Reformat all docstrings in a Python source string to the canonical quote style.

    Args:
        source (str): The Python source code to reformat.

    Returns:
        str: The source code with canonically formatted docstrings.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines_with_endings = source.splitlines(keepends=True)
    line_starts: list[int] = [0]
    pos = 0
    for line in lines_with_endings:
        pos += len(line)
        line_starts.append(pos)
    entries = _collect_docstring_entries(tree, source)
    replacements: list[tuple[int, int, str]] = []
    for const_node, content in entries:
        start_col = const_node.col_offset

        # Use ast.get_source_segment to correctly handle multi-byte characters
        # (AST col_offset/end_col_offset are UTF-8 byte offsets, not char offsets).
        segment = ast.get_source_segment(source, const_node)
        if segment is None:
            continue
        approx_pos = line_starts[const_node.lineno - 1]
        char_start = source.find(segment, approx_pos)
        if char_start == -1:
            continue
        char_end = char_start + len(segment)
        current_text = source[char_start:char_end]
        if not (current_text.startswith('"""') or current_text.startswith("'''")):
            continue

        indent = " " * start_col
        formatted = _build_formatted_docstring(content, indent)
        if current_text.startswith("'''"):
            formatted = formatted
        if current_text != formatted:
            replacements.append((char_start, char_end, formatted))
    if not replacements:
        return source

    replacements.sort(key=lambda r: r[0], reverse=True)
    result = source
    for char_start, char_end, new_text in replacements:
        result = result[:char_start] + new_text + result[char_end:]
    return result


def fix_file(file_path: str) -> bool:
    """
    Reformat docstring quote placement in a Python file in-place.

    Args:
        file_path (str): Path to the Python file to fix.

    Returns:
        bool: True if the file was modified, False if it was already correct.
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8")
    formatted = format_file_docstrings(source)
    if formatted != source:
        path.write_text(formatted, encoding="utf-8")
        return True
    return False
