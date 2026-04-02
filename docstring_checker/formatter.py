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
        - Custom headers ending in ``:`` cause subsequent lines to indent +4.
        - List items (``- item``, ``1. item``) under headers are indented +4.

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

    # Standard Google-style section keywords
    standard_sections = {"Args:", "Returns:", "Yields:", "Raises:", "Note:", "Notes:", "Attributes:", "Examples:"}

    # Pattern for parameter/type lines: "name (type): desc" or "type: desc" (incl. brackets)
    param_pattern = r"\w[\w\[\], |]*\s*(\([^)]*\))?\s*:"
    in_section = False
    is_param_line = False
    in_custom_header = False
    in_tuple_breakdown = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            is_param_line = False
            in_tuple_breakdown = False
            if not in_section:
                in_custom_header = False
            continue

        # Standard section keywords (Args:, Returns:, etc.)
        if stripped in standard_sections:
            result.append(f"{base}{stripped}")
            in_section = True
            in_custom_header = False
            is_param_line = False
            in_tuple_breakdown = False
            continue

        # Inside a standard section (Args/Returns/etc.)
        if in_section:
            # Sub-type lines in a tuple breakdown (e.g. "int: description")
            # but NOT new parameters with "(type)" notation
            if in_tuple_breakdown and re_match(param_pattern, stripped) and "(" not in stripped.split(":")[0]:
                result.append(f"{continuation_indent}{stripped}")
                continue
            if re_match(param_pattern, stripped):
                result.append(f"{section_indent}{stripped}")
                is_param_line = True

                # Detect tuple/complex type lines that expect a breakdown
                # Matches both "tuple[...]:desc" (Returns) and "name (tuple[...]): desc" (Args)
                in_tuple_breakdown = "tuple[" in stripped.lower() or "list[" in stripped.lower()
                continue
            if is_param_line:
                result.append(f"{continuation_indent}{stripped}")
                continue

            # Blank line already handled above; hitting non-param text exits section
            in_section = False

        # Custom description header ending in ":" (e.g. "Phases:", "Expects...:")
        if (
            stripped.endswith(":")
            and not stripped.startswith("-")
            and not stripped.startswith(("1", "2", "3", "4", "5", "6", "7", "8", "9"))
        ):
            result.append(f"{base}{stripped}")
            in_custom_header = True
            is_param_line = False
            continue

        # Content under a custom header (list items, numbered items, etc.)
        if in_custom_header:
            result.append(f"{section_indent}{stripped}")
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


def _remove_unused_imports(source: str) -> str:
    """
    Remove unused top-level imports from Python source code.

    Uses pyflakes to detect unused imports.
    Respects ``# noqa`` comments - any import statement whose source lines contain ``noqa`` is left untouched.

    Args:
        source (str): The Python source code.

    Returns:
        str: The source with unused top-level imports removed.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    try:
        from pyflakes import checker as _pyflk, messages as _pyflk_msgs

    except ImportError:
        return source
    try:
        w = _pyflk.Checker(tree)
    except Exception:
        return source

    lines = source.splitlines(keepends=True)

    # Collect pyflakes-reported unused import keys per lineno.
    # message_args[0] formats: 'os', 'os.path', 'os as o', 'os.path as p', '.utils', '.utils.helper'
    unused_keys_by_lineno: dict[int, set[str]] = {}
    for msg in w.messages:
        if isinstance(msg, _pyflk_msgs.UnusedImport):
            unused_keys_by_lineno.setdefault(msg.lineno, set()).add(msg.message_args[0])
    if not unused_keys_by_lineno:
        return source

    # Build map: start lineno -> import nodes starting at that line
    import_nodes_by_lineno: dict[int, list[ast.Import | ast.ImportFrom]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_nodes_by_lineno.setdefault(node.lineno, []).append(node)

    def _alias_key(node: ast.Import | ast.ImportFrom, alias: ast.alias) -> str:
        """
        Compute the key string that pyflakes uses for this alias in its messages.

        Args:
            node (ast.Import | ast.ImportFrom): The import node.
            alias (ast.alias): The specific alias within the import statement.

        Returns:
            str: The key string representing this import as used in pyflakes messages.
        """
        if isinstance(node, ast.Import):
            if alias.asname:
                return f"{alias.name} as {alias.asname}"
            return alias.name

        # ImportFrom
        dots = "." * (node.level or 0)
        mod = node.module or ""
        full_module = f"{dots}{mod}" if mod else dots

        # Avoid double separator when full_module ends with a dot (e.g. 'from . import X')
        full_name = f"{full_module}{alias.name}" if full_module.endswith(".") else f"{full_module}.{alias.name}"
        if alias.asname:
            return f"{full_name} as {alias.asname}"
        return full_name

    def _has_noqa(start_lineno: int, end_lineno: int) -> bool:
        """
        Check if any line in the given range contains a "noqa" comment.

        Args:
            start_lineno (int): The starting line number (1-based).
            end_lineno (int): The ending line number (1-based).

        Returns:
            bool: True if any line in the range contains "noqa", False otherwise.
        """
        for i in range(start_lineno - 1, end_lineno):
            if i < len(lines) and "noqa" in lines[i]:
                return True
        return False

    # Map id(node) -> (node, set of alias.names to remove)
    unused_by_node: dict[int, tuple[ast.Import | ast.ImportFrom, set[str]]] = {}
    for lineno, bad_keys in unused_keys_by_lineno.items():
        for node in import_nodes_by_lineno.get(lineno, []):
            if _has_noqa(node.lineno, node.end_lineno or node.lineno):
                continue
            for alias in node.names:
                if _alias_key(node, alias) in bad_keys:
                    nid = id(node)
                    if nid not in unused_by_node:
                        unused_by_node[nid] = (node, set())
                    unused_by_node[nid][1].add(alias.name)
    if not unused_by_node:
        return source

    replacements: list[tuple[int, int, str | None]] = []
    for nid, (node, unused_alias_names) in unused_by_node.items():
        remaining = [a for a in node.names if a.name not in unused_alias_names]
        s = node.lineno - 1
        e = (node.end_lineno or node.lineno) - 1
        if not remaining:
            replacements.append((s, e, None))
        else:
            if isinstance(node, ast.ImportFrom):
                dots = "." * (node.level or 0)
                mod = node.module or ""
                full_module = f"{dots}{mod}" if mod else dots
                parts = [f"{a.name} as {a.asname}" if a.asname else a.name for a in remaining]
                single = f"from {full_module} import {', '.join(parts)}"
                if len(single) <= LINE_LENGTH:
                    new_text = single + "\n"
                else:
                    new_text = f"from {full_module} import (\n" + "".join(f"    {p},\n" for p in parts) + ")\n"
            else:
                parts = [f"{a.name} as {a.asname}" if a.asname else a.name for a in remaining]
                new_text = f"import {', '.join(parts)}\n"
            replacements.append((s, e, new_text))
    if not replacements:
        return source

    replacements.sort(key=lambda r: r[0], reverse=True)
    result_lines = list(lines)
    for s, e, replacement in replacements:
        if replacement is None:
            del result_lines[s : e + 1]
        else:
            result_lines[s : e + 1] = [replacement]

    # Collapse 3+ consecutive blank lines down to 2
    final_lines: list[str] = []
    blank_count = 0
    for line in result_lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                final_lines.append(line)
        else:
            blank_count = 0
            final_lines.append(line)
    return "".join(final_lines)


def fix_file(file_path: str) -> bool:
    """
    Reformat docstring quote placement and remove unused imports in a Python file in-place.

    Args:
        file_path (str): Path to the Python file to fix.

    Returns:
        bool: True if the file was modified, False if it was already correct.
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8")
    with_imports_removed = _remove_unused_imports(source)
    formatted = format_file_docstrings(with_imports_removed)
    if formatted != source:
        path.write_text(formatted, encoding="utf-8")
        return True
    return False
