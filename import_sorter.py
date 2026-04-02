"""
Import sorter for Python files.

Groups imports into four ordered sections separated by blank lines:
    1. ``__future__`` imports
    2. Standard-library imports
    3. Third-party package imports
    4. Local / project imports

Within each section packages are sorted alphabetically (``import`` statements
before ``from … import`` statements).  Individual imported names inside
``from``-imports are also sorted alphabetically.

Usage:
    python import_sorter.py                 # check only (exit 1 on issues)
    python import_sorter.py --fix           # auto-fix all files
    python import_sorter.py --fix source/   # auto-fix specific directory
"""

from __future__ import annotations

import ast
import importlib.metadata
import sys
from glob import glob
from pathlib import Path
from typing import Optional

from colorama import Fore, init, Style

init(autoreset=True)
AUTO_FIX = "--fix" in sys.argv or "--auto-fix" in sys.argv
LINE_LENGTH = 120
STDLIB_MODULES: frozenset[str] = frozenset(sys.stdlib_module_names)

# Mapping of sub-module paths to their shortened parent module.
# e.g. ``from ui.tracking_overlay import X`` becomes ``from ui import X``.
PATH_ALIASES: dict[str, str] = {
    "ui.tracking_overlay": "ui",
}

# Tracks which names were shortened from which sub-modules during a run.
# Key: (package_name, sub_module), Value: set of imported names
# e.g. ("utils", "module1") -> {"func_a", "func_b"}
_init_updates: dict[tuple[str, str], set[str]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _third_party_packages() -> frozenset[str]:
    """
    Return top-level importable names of all installed distributions.

    Returns:
        frozenset[str]: Set of top-level package names (e.g. "requests", "numpy").
    """
    try:
        pd = importlib.metadata.packages_distributions()
        return frozenset(pd.keys())
    except AttributeError:
        # Python < 3.11 fallback
        pkgs: set[str] = set()
        for dist in importlib.metadata.distributions():
            top_level = dist.read_text("top_level.txt")
            if top_level:
                for name in top_level.strip().splitlines():
                    pkgs.add(name.strip())
            else:
                pkgs.add(dist.metadata["Name"].replace("-", "_"))
        return frozenset(pkgs)


def _classify(module: str, level: int, third_party_pkgs: frozenset[str]) -> str:
    """
    Return the group key for an import.

    Args:
        module (str): The module being imported (e.g. "os", "requests", "myproject.utils").
        level (int): The level of the import (0 for absolute, >0 for relative).
        third_party_pkgs (frozenset[str]): Set of known third-party package names.

    Returns:
        str: One of "future", "stdlib", "third_party", or "local".
    """
    if module == "__future__":
        return "future"
    if level > 0:
        return "local"
    top = module.split(".")[0]
    if top in STDLIB_MODULES:
        return "stdlib"
    if top in third_party_pkgs:
        return "third_party"
    return "local"


def _sort_key(node: ast.Import | ast.ImportFrom) -> tuple[int, str]:
    """
    Sort key: ``import`` before ``from``, then alphabetically by module.

    Args:
        node (ast.Import | ast.ImportFrom): The import node to generate a sort key for.

    Returns:
        tuple[int, str]:
            int: 0 for ``import``, 1 for ``from``.
            str: The module name in lowercase (e.g. "os", "requests", "myproject.utils").
    """
    if isinstance(node, ast.Import):
        return (0, node.names[0].name.lower())
    dots = "." * (node.level or 0)
    mod = f"{dots}{node.module}" if node.module else dots
    return (1, mod.lower())


def _apply_path_aliases(node: ast.ImportFrom, shorten_local: bool = False) -> ast.ImportFrom:
    """
    Shorten module paths according to ``PATH_ALIASES`` and optionally shorten local imports.

    Args:
        node (ast.ImportFrom): The import node to modify in-place.
        shorten_local (bool, optional): Whether to shorten local imports. Defaults to False.

    Returns:
    ast.ImportFrom: The modified node with updated module path.
    """
    if node.module and node.module in PATH_ALIASES:
        node.module = PATH_ALIASES[node.module]
    elif shorten_local and node.module and "." in node.module and not (node.level or 0):
        original_module = node.module
        parts = original_module.split(".")
        package = parts[0]
        sub_module = ".".join(parts[1:])

        # Track which names need to be re-exported from __init__.py
        imported_names = {alias.name for alias in node.names}
        key = (package, sub_module)
        if key not in _init_updates:
            _init_updates[key] = set()
        _init_updates[key].update(imported_names)
        node.module = package
    return node


def _merge_key(node: ast.ImportFrom) -> tuple[int, str]:
    """
    Return a key that identifies the module a from-import refers to.

    Args:
        node (ast.ImportFrom): The import node to generate a merge key for.

    Returns:
        tuple[int, str]:
            int: The level of the import (0 for absolute, >0 for relative).
            str: The module name with dots for relative levels (e.g. "os", "requests", ".utils").
    """
    dots = "." * (node.level or 0)
    mod = f"{dots}{node.module}" if node.module else dots
    return (node.level or 0, mod)


def _consolidate_from_imports(
    nodes: list[ast.Import | ast.ImportFrom],
) -> list[ast.Import | ast.ImportFrom]:
    """
    Merge multiple ``from X import …`` for the same module into one node.

    Args:
        nodes (list[ast.Import | ast.ImportFrom]): List of import nodes to consolidate.

    Returns:
    list[ast.Import | ast.ImportFrom]: Consolidated list of import nodes.
    """
    result: list[ast.Import | ast.ImportFrom] = []
    from_groups: dict[tuple[int, str], ast.ImportFrom] = {}
    order: list[tuple[int, str] | int] = []
    for idx, node in enumerate(nodes):
        if isinstance(node, ast.ImportFrom):
            _apply_path_aliases(node)
            key = _merge_key(node)
            if key in from_groups:
                existing = from_groups[key]
                existing_names = {(a.name, a.asname) for a in existing.names}
                for alias in node.names:
                    if (alias.name, alias.asname) not in existing_names:
                        existing.names.append(alias)
                        existing_names.add((alias.name, alias.asname))
            else:
                from_groups[key] = node
                order.append(key)
        else:
            order.append(idx)
            result.append(node)
    final: list[ast.Import | ast.ImportFrom] = []
    plain_iter = iter(result)
    for entry in order:
        if isinstance(entry, tuple):
            final.append(from_groups[entry])
        else:
            final.append(next(plain_iter))
    return final


def _format(node: ast.Import | ast.ImportFrom, trailing_comment: str = "") -> list[str]:
    """
    Return the formatted line(s) for a single import node.

    Args:
        node (ast.Import | ast.ImportFrom): The import node to format.
        trailing_comment (str, optional): An optional comment to append to the first line. Defaults to "".

    Returns:
        list[str]: The formatted import statement(s) as a list of lines.
    """
    if isinstance(node, ast.Import):
        out: list[str] = []
        for alias in sorted(node.names, key=lambda a: a.name.lower()):
            line = f"import {alias.name} as {alias.asname}" if alias.asname else f"import {alias.name}"
            out.append(line + trailing_comment if not out else line)
        return out
    assert isinstance(node, ast.ImportFrom)
    dots = "." * (node.level or 0)
    module = f"{dots}{node.module}" if node.module else dots
    sorted_names = sorted(node.names, key=lambda a: a.name.lower())
    parts = [f"{a.name} as {a.asname}" if a.asname else a.name for a in sorted_names]
    single = f"from {module} import {', '.join(parts)}"
    if len(single) + len(trailing_comment) <= LINE_LENGTH:
        return [single + trailing_comment]
    lines = [f"from {module} import ({trailing_comment}"]
    for part in parts:
        lines.append(f"    {part},")
    lines.append(")")
    return lines


def _extract_comments(
    lines: list[str],
    nodes: list[ast.Import | ast.ImportFrom],
) -> dict[int, str]:
    """
    Map ``{lineno: trailing_comment}`` from the original source lines.

    Args:
        lines (list[str]): The original source lines.
        nodes (list[ast.Import | ast.ImportFrom]): The import nodes to extract comments for.

    Returns:
        dict[int, str]: Mapping of line numbers to their trailing comments (including leading spaces).
    """
    comments: dict[int, str] = {}
    for node in nodes:
        line = lines[node.lineno - 1].rstrip("\n\r")
        idx = line.find("#")
        if idx != -1:
            comments[node.lineno] = "  " + line[idx:]
    return comments


def _find_import_segments(
    lines: list[str],
    nodes: list[ast.Import | ast.ImportFrom],
    first: int,
    last: int,
    pinned_lines: Optional[set[int]] = None,
) -> list[tuple[str, int, int]]:
    """
    Split ``[first, last]`` into ``("import", start, end)`` / ``("other", start, end)`` segments.

    Args:
        lines (list[str]): The original source lines.
        nodes (list[ast.Import | ast.ImportFrom]): The import nodes to identify import lines.
        first (int): The first line number (0-based) of the range to segment.
        last (int): The last line number (0-based) of the range to segment.
        pinned_lines (Optional[set[int]]): Line numbers that should be treated as "other" even if they contain imports.

    Returns:
        list[tuple[str, int, int]]: List of segments, where each segment is a tuple of (kind, start_line, end_line).
    """
    import_lines: set[int] = set()
    for node in nodes:
        end = (node.end_lineno or node.lineno) - 1
        for i in range(node.lineno - 1, end + 1):
            if first <= i <= last and (pinned_lines is None or i not in pinned_lines):
                import_lines.add(i)
    segments: list[tuple[str, int, int]] = []
    i = first
    while i <= last:
        kind = "import" if i in import_lines else "other"
        start = i
        while i <= last and (i in import_lines) == (kind == "import"):
            i += 1
        segments.append((kind, start, i - 1))
    return segments


def _collect_function_import_blocks(
    tree: ast.AST,
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[ast.Import | ast.ImportFrom]]]:
    """
    Collect all contiguous import blocks inside function bodies (not top-level).

    Args:
        tree (ast.AST): The AST of the source code to analyze.

    Returns:
    list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[ast.Import | ast.ImportFrom]]]:
        A list of tuples, each containing a function node and a list of import nodes.
    """
    results: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[ast.Import | ast.ImportFrom]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        current_block: list[ast.Import | ast.ImportFrom] = []
        for child in node.body:
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                current_block.append(child)
            else:
                if current_block:
                    results.append((node, list(current_block)))
                    current_block = []
        if current_block:
            results.append((node, list(current_block)))
    return results


# ---------------------------------------------------------------------------
# Unused import removal (pyflakes-based)
# ---------------------------------------------------------------------------
def _remove_unused_imports(src: str, lines: list[str]) -> tuple[str, list[str]]:
    """
    Remove unused imports (top-level and inside functions) detected by pyflakes.

    Respects ``# noqa`` lines.  Returns ``(new_src, list_of_removed_keys)``.

    Args:
        src (str): The original source code.
        lines (list[str]): The original source lines (with line breaks).

    Returns:
        tuple[str, list[str]]:
            str: The modified source code with unused imports removed.
            list[str]: A list of "module.name" keys for the removed imports.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, []
    try:
        from pyflakes import checker as _pyflk, messages as _pyflk_msgs

    except ImportError:
        return src, []
    try:
        w = _pyflk.Checker(tree)
    except Exception:
        return src, []

    # Collect lineno -> set of "module.name" keys for unused imports
    unused_keys_by_lineno: dict[int, set[str]] = {}
    for msg in w.messages:
        if isinstance(msg, _pyflk_msgs.UnusedImport):
            unused_keys_by_lineno.setdefault(msg.lineno, set()).add(msg.message_args[0])
    if not unused_keys_by_lineno:
        return src, []

    # Build map: lineno -> import nodes at any scope (top-level and inside functions)
    import_nodes_by_lineno: dict[int, list[ast.Import | ast.ImportFrom]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_nodes_by_lineno.setdefault(node.lineno, []).append(node)

    def _alias_key(node: ast.Import | ast.ImportFrom, alias: ast.alias) -> str:
        """
        Return the "module.name" key for an imported name.

        Args:
            node (ast.Import | ast.ImportFrom): The import node containing the alias.
            alias (ast.alias): The alias to generate the key for.

        Returns:
            str: The "module.name" key representing the imported name (e.g. "os.path", "requests.get").
        """
        if isinstance(node, ast.Import):
            if alias.asname:
                return f"{alias.name} as {alias.asname}"
            return alias.name
        dots = "." * (node.level or 0)
        mod = node.module or ""
        full_module = f"{dots}{mod}" if mod else dots
        full_name = f"{full_module}{alias.name}" if full_module.endswith(".") else f"{full_module}.{alias.name}"
        if alias.asname:
            return f"{full_name} as {alias.asname}"
        return full_name

    def _has_noqa(start_lineno: int, end_lineno: int) -> bool:
        """
        Check if any line in the given range has a "noqa" comment.

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

    def _line_indent(lineno: int) -> str:
        """
        Return the leading whitespace of a source line (1-based lineno).

        Args:
            lineno (int): The line number (1-based) to get the indent for.

        Returns:
            str: The leading whitespace of the specified line, or an empty string if the line number is out of range.
        """
        raw = lines[lineno - 1] if lineno - 1 < len(lines) else ""
        return raw[: len(raw) - len(raw.lstrip())]

    unused_by_node: dict[int, tuple[ast.Import | ast.ImportFrom, set[str]]] = {}
    removed_keys: list[str] = []
    for lineno, bad_keys in unused_keys_by_lineno.items():
        for node in import_nodes_by_lineno.get(lineno, []):
            if _has_noqa(node.lineno, node.end_lineno or node.lineno):
                continue
            for alias in node.names:
                key = _alias_key(node, alias)
                if key in bad_keys:
                    nid = id(node)
                    if nid not in unused_by_node:
                        unused_by_node[nid] = (node, set())
                    unused_by_node[nid][1].add(alias.name)
                    removed_keys.append(key)
    if not unused_by_node:
        return src, []

    replacements: list[tuple[int, int, str | None]] = []
    for nid, (node, unused_alias_names) in unused_by_node.items():
        remaining = [a for a in node.names if a.name not in unused_alias_names]
        s = node.lineno - 1
        e = (node.end_lineno or node.lineno) - 1
        if not remaining:
            replacements.append((s, e, None))
        else:
            indent = _line_indent(node.lineno)
            if isinstance(node, ast.ImportFrom):
                dots = "." * (node.level or 0)
                mod = node.module or ""
                full_module = f"{dots}{mod}" if mod else dots
                parts = [f"{a.name} as {a.asname}" if a.asname else a.name for a in remaining]
                single = f"{indent}from {full_module} import {', '.join(parts)}"
                new_text = (
                    single + "\n"
                    if len(single) <= LINE_LENGTH
                    else (
                        f"{indent}from {full_module} import (\n"
                        + "".join(f"{indent}    {p},\n" for p in parts)
                        + f"{indent})\n"
                    )
                )
            else:
                parts = [f"{a.name} as {a.asname}" if a.asname else a.name for a in remaining]
                new_text = f"{indent}import {', '.join(parts)}\n"
            replacements.append((s, e, new_text))
    replacements.sort(key=lambda r: r[0], reverse=True)
    result_lines = list(lines)
    for s, e, replacement in replacements:
        if replacement is None:
            del result_lines[s : e + 1]
        else:
            result_lines[s : e + 1] = [replacement]

    # Collapse 3+ consecutive blank lines to 2
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
    return "".join(final_lines), removed_keys


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------
def _process(path: Path, third_party_pkgs: frozenset[str]) -> tuple[bool, list[str]]:
    """
    Check / fix one file.  Returns ``(changed, messages)``.

    Args:
        path (Path): The path to the file to process.
        third_party_pkgs (frozenset[str]): Set of known third-party package names.

    Returns:
        tuple[bool, list[str]]:
            bool: True if the file was modified, False otherwise.
            list[str]: A list of messages describing any issues found or fixes applied.
    """
    msgs: list[str] = []
    try:
        src = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, [f"  {Fore.RED}read error {path}: {e}{Style.RESET_ALL}"]
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, [f"  {Fore.RED}syntax error {path}: {e}{Style.RESET_ALL}"]

    changed = False

    # --- remove unused imports first ----------------------------------------
    lines_for_unused = src.splitlines(keepends=True)
    new_src, removed_keys = _remove_unused_imports(src, lines_for_unused)
    if removed_keys:
        file_abs = str(path.resolve()).replace("\\", "/")
        msgs.append(
            f"  {Fore.YELLOW}Unused imports in{Style.RESET_ALL} " f'{Fore.CYAN}>>> code "{file_abs}:1"{Style.RESET_ALL}'
        )
        for key in removed_keys:
            msgs.append(f"    {Fore.RED}  - {key}{Style.RESET_ALL}")
        if AUTO_FIX:
            path.write_text(new_src, encoding="utf-8")
            src = new_src
            try:
                tree = ast.parse(src)
            except SyntaxError:
                pass
            msgs.append(f"    {Fore.GREEN}-> fixed{Style.RESET_ALL}")
        changed = True

    # --- process top-level imports ------------------------------------------
    top_changed, top_msgs = _process_top_level(tree, src, path, third_party_pkgs)
    msgs.extend(top_msgs)
    if top_changed:
        changed = True

        # Re-read and re-parse after top-level fix
        if AUTO_FIX:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)

    # --- process function-level imports -------------------------------------
    func_changed, func_msgs = _process_function_imports(tree, src, path, third_party_pkgs)
    msgs.extend(func_msgs)
    if func_changed:
        changed = True
        if AUTO_FIX:
            src = path.read_text(encoding="utf-8")

    # --- sort __all__ lists --------------------------------------------------
    all_changed, all_msgs = _sort_dunder_all(src, path)
    msgs.extend(all_msgs)
    if all_changed:
        changed = True
    return changed, msgs


def _process_top_level(
    tree: ast.AST,
    src: str,
    path: Path,
    third_party_pkgs: frozenset[str],
) -> tuple[bool, list[str]]:
    """
    Sort and consolidate top-level imports.

    Args:
        tree (ast.AST): The AST of the source code to process.
        src (str): The original source code.
        path (Path): The path to the file being processed (for messages).
        third_party_pkgs (frozenset[str]): Set of known third-party package names.

    Returns:
        tuple[bool, list[str]]:
            bool: True if the file was modified, False otherwise.
            list[str]: A list of messages describing any issues found or fixes applied.
    """
    msgs: list[str] = []
    nodes: list[ast.Import | ast.ImportFrom] = [
        n for n in ast.iter_child_nodes(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    if not nodes:
        return False, []
    lines = src.splitlines(keepends=True)
    first = nodes[0].lineno - 1
    last = nodes[-1].end_lineno
    if last is None:
        last = nodes[-1].lineno
    last -= 1

    # --- extract inline comments from original source ----------------------
    comments = _extract_comments(lines, nodes)

    # --- detect pinned imports (``# noqa: sort``) ---------------------------
    pinned_lines: set[int] = set()
    pinned_nodes: set[int] = set()  # indices into ``nodes``
    for idx, node in enumerate(nodes):
        line = lines[node.lineno - 1].rstrip("\n\r")
        if "noqa: sort" in line or "noqa:sort" in line:
            end = (node.end_lineno or node.lineno) - 1
            for i in range(node.lineno - 1, end + 1):
                pinned_lines.add(i)
            pinned_nodes.add(idx)
    sortable_nodes = [n for idx, n in enumerate(nodes) if idx not in pinned_nodes]

    # --- extract __future__ imports for strict first-position enforcement ----
    future_nodes = [n for n in sortable_nodes if isinstance(n, ast.ImportFrom) and n.module == "__future__"]
    non_future_sortable = [n for n in sortable_nodes if n not in future_nodes]

    # --- split into segments (import vs non-import code) -------------------
    segments = _find_import_segments(lines, nodes, first, last, pinned_lines)

    # --- helper: build sorted import text for a list of nodes --------------
    def _build_sorted_block(seg_nodes: list[ast.Import | ast.ImportFrom]) -> str:
        """
        Build a sorted import block from the given nodes, preserving comments and applying path aliases.

        Args:
            seg_nodes (list[ast.Import | ast.ImportFrom]): The import nodes to sort and format.

        Returns:
            str: The formatted import block as a string.
        """
        groups: dict[str, list[ast.Import | ast.ImportFrom]] = {
            "future": [],
            "stdlib": [],
            "third_party": [],
            "local": [],
        }
        for node in seg_nodes:
            if isinstance(node, ast.Import) and len(node.names) > 1:
                for alias in node.names:
                    single = ast.Import(names=[alias])
                    single.lineno = node.lineno
                    grp = _classify(alias.name, 0, third_party_pkgs)
                    groups[grp].append(single)
            else:
                if isinstance(node, ast.ImportFrom):
                    _apply_path_aliases(node)
                mod = node.names[0].name if isinstance(node, ast.Import) else (node.module or "")
                lvl = 0 if isinstance(node, ast.Import) else (node.level or 0)
                grp = _classify(mod, lvl, third_party_pkgs)

                # Shorten local sub-module paths to top-level package
                if grp == "local" and isinstance(node, ast.ImportFrom):
                    _apply_path_aliases(node, shorten_local=True)
                groups[grp].append(node)

        # Consolidate from-imports within each group
        for key in groups:
            groups[key] = _consolidate_from_imports(groups[key])
            groups[key].sort(key=_sort_key)
        sections: list[str] = []
        for key in ("future", "stdlib", "third_party", "local"):
            if not groups[key]:
                continue
            sec_lines: list[str] = []
            seen: set[str] = set()
            for node in groups[key]:
                comment = comments.get(getattr(node, "lineno", -1), "")
                formatted = _format(node, comment)
                block = "\n".join(formatted)
                if block not in seen:
                    seen.add(block)
                    sec_lines.extend(formatted)
            sections.append("\n".join(sec_lines))
        return "\n\n".join(sections)

    # --- process: merge imports across blank-line gaps, keep code boundaries --
    merged_nodes: list[ast.Import | ast.ImportFrom] = []
    output_chunks: list[str] = []

    def _flush_merged() -> None:
        """Flush the currently merged import nodes into a sorted block and clear the merge buffer."""
        if merged_nodes:
            output_chunks.append(_build_sorted_block(list(merged_nodes)))
            merged_nodes.clear()

    for kind, seg_start, seg_end in segments:
        if kind == "import":
            seg_nodes = [n for n in non_future_sortable if seg_start <= n.lineno - 1 <= seg_end]
            merged_nodes.extend(seg_nodes)
        else:
            has_code = any(lines[i].strip() for i in range(seg_start, seg_end + 1))
            if has_code:
                _flush_merged()
                code_lines = [lines[i].rstrip("\n\r") for i in range(seg_start, seg_end + 1)]
                while code_lines and not code_lines[0].strip():
                    code_lines.pop(0)
                while code_lines and not code_lines[-1].strip():
                    code_lines.pop()
                output_chunks.append("\n".join(code_lines))
    _flush_merged()

    # --- prepend __future__ imports (strict first-position rule) -----------
    if future_nodes:
        consolidated_future = _consolidate_from_imports(list(future_nodes))
        consolidated_future.sort(key=_sort_key)
        future_lines: list[str] = []
        for fnode in consolidated_future:
            comment = comments.get(getattr(fnode, "lineno", -1), "")
            future_lines.extend(_format(fnode, comment))
        future_block = "\n".join(future_lines)
        if output_chunks:
            new_block = future_block + "\n\n" + "\n\n".join(output_chunks) + "\n"
        else:
            new_block = future_block + "\n"
    else:
        new_block = "\n\n".join(output_chunks) + "\n"

    # --- collect & consolidate TYPE_CHECKING blocks -----------------------
    tc_if_nodes: list[ast.If] = []
    for child_node in ast.iter_child_nodes(tree):
        if not isinstance(child_node, ast.If):
            continue
        test = child_node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if is_tc:
            tc_if_nodes.append(child_node)

    # Scan forward from the import block to collect adjacent TC blocks
    # (allow blank lines between imports and TYPE_CHECKING)
    tc_collected: list[ast.If] = []
    scan = last + 1
    while scan < len(lines):
        stripped = lines[scan].strip()
        if stripped == "":
            scan += 1
            continue
        matched = False
        for tc_node in tc_if_nodes:
            if tc_node.lineno - 1 == scan:
                tc_collected.append(tc_node)
                blk_last = (tc_node.end_lineno or tc_node.lineno) - 1
                scan = blk_last + 1
                matched = True
                break
        if not matched:
            break

    # Also include TC blocks within the import range (rare but possible)
    for tc_node in tc_if_nodes:
        blk_first = tc_node.lineno - 1
        blk_last = (tc_node.end_lineno or tc_node.lineno) - 1
        if blk_first >= first and blk_last <= last and tc_node not in tc_collected:
            tc_collected.append(tc_node)

    # Extend replacement range to cover collected TC blocks
    if tc_collected:
        last = max(last, max((n.end_lineno or n.lineno) - 1 for n in tc_collected))

    # Extract imports and non-import statements from TC blocks
    tc_import_nodes: list[ast.Import | ast.ImportFrom] = []
    tc_other_stmts: list[str] = []
    for tc_node in tc_collected:
        for child in tc_node.body:
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                tc_import_nodes.append(child)
            else:
                stmt_first = child.lineno - 1
                stmt_last = (child.end_lineno or child.lineno) - 1
                raw_lines = "".join(lines[stmt_first : stmt_last + 1]).splitlines()
                first_line = raw_lines[0] if raw_lines else ""
                base_indent = len(first_line) - len(first_line.lstrip())
                re_indented = []
                for ln in raw_lines:
                    if len(ln) >= base_indent and ln[:base_indent].strip() == "":
                        re_indented.append("    " + ln[base_indent:])
                    else:
                        re_indented.append("    " + ln.lstrip())
                tc_other_stmts.append("\n".join(re_indented))

    # --- append consolidated TYPE_CHECKING block ---------------------------
    if tc_import_nodes or tc_other_stmts:
        tc_groups: dict[str, list[ast.Import | ast.ImportFrom]] = {
            "future": [],
            "stdlib": [],
            "third_party": [],
            "local": [],
        }
        for node in tc_import_nodes:
            if isinstance(node, ast.Import) and len(node.names) > 1:
                for alias in node.names:
                    single = ast.Import(names=[alias])
                    grp = _classify(alias.name, 0, third_party_pkgs)
                    tc_groups[grp].append(single)
            else:
                if isinstance(node, ast.ImportFrom):
                    _apply_path_aliases(node)
                mod = node.names[0].name if isinstance(node, ast.Import) else (node.module or "")
                lvl = 0 if isinstance(node, ast.Import) else (node.level or 0)
                grp = _classify(mod, lvl, third_party_pkgs)
                if grp == "local" and isinstance(node, ast.ImportFrom):
                    _apply_path_aliases(node, shorten_local=True)
                tc_groups[grp].append(node)
        for key in tc_groups:
            tc_groups[key] = _consolidate_from_imports(tc_groups[key])
            tc_groups[key].sort(key=_sort_key)
        tc_sections: list[str] = []
        for key in ("future", "stdlib", "third_party", "local"):
            if not tc_groups[key]:
                continue
            sec_lines: list[str] = []
            seen: set[str] = set()
            for node in tc_groups[key]:
                formatted = _format(node)
                block = "\n".join(formatted)
                if block not in seen:
                    seen.add(block)
                    sec_lines.extend(f"    {line}" for line in formatted)
            tc_sections.append("\n".join(sec_lines))
        tc_content_parts = tc_sections + tc_other_stmts
        tc_body = "\n\n".join(tc_content_parts)
        new_block += "\nif TYPE_CHECKING:\n" + tc_body + "\n"

    # --- compare -----------------------------------------------------------
    original = "".join(lines[first : last + 1])
    if not original.endswith("\n"):
        original += "\n"
    if original == new_block:
        return False, []

    # Changes needed
    file_abs = str(path.resolve()).replace("\\", "/")
    msgs.append(
        f"  {Fore.YELLOW}Import order issues in{Style.RESET_ALL} "
        f'{Fore.CYAN}>>> code "{file_abs}:{nodes[0].lineno}"{Style.RESET_ALL}'
    )
    if AUTO_FIX:
        rebuilt = lines[:first] + [new_block] + lines[last + 1 :]
        path.write_text("".join(rebuilt), encoding="utf-8")
        msgs.append(f"    {Fore.GREEN}-> fixed{Style.RESET_ALL}")
    return True, msgs


def _process_function_imports(
    tree: ast.AST,
    src: str,
    path: Path,
    third_party_pkgs: frozenset[str],
) -> tuple[bool, list[str]]:
    """
    Sort and consolidate imports inside function bodies.

    Args:
        tree (ast.AST): The AST of the source code to process.
        src (str): The original source code.
        path (Path): The path to the file being processed (for messages).
        third_party_pkgs (frozenset[str]): Set of known third-party package names.

    Returns:
        tuple[bool, list[str]]:
            bool: True if the file was modified, False otherwise.
            list[str]: A list of messages describing any issues found or fixes applied.
    """
    msgs: list[str] = []
    func_blocks = _collect_function_import_blocks(tree)
    if not func_blocks:
        return False, []

    lines = src.splitlines(keepends=True)

    # Process from bottom to top so line-number offsets remain valid.
    func_blocks.sort(key=lambda fb: fb[1][0].lineno, reverse=True)
    changed = False
    for func_node, imp_nodes in func_blocks:
        first = imp_nodes[0].lineno - 1
        last_end = imp_nodes[-1].end_lineno
        if last_end is None:
            last_end = imp_nodes[-1].lineno
        last = last_end - 1

        # Determine indentation from the first import line
        first_line = lines[first]
        indent = first_line[: len(first_line) - len(first_line.lstrip())]

        # Apply path aliases and consolidate
        for node in imp_nodes:
            if isinstance(node, ast.ImportFrom):
                _apply_path_aliases(node)
                mod = node.module or ""
                lvl = node.level or 0
                if _classify(mod, lvl, third_party_pkgs) == "local":
                    _apply_path_aliases(node, shorten_local=True)
        consolidated = _consolidate_from_imports(list(imp_nodes))
        consolidated.sort(key=_sort_key)

        # Group and format
        groups: dict[str, list[ast.Import | ast.ImportFrom]] = {
            "future": [],
            "stdlib": [],
            "third_party": [],
            "local": [],
        }
        for node in consolidated:
            if isinstance(node, ast.Import) and len(node.names) > 1:
                for alias in node.names:
                    single = ast.Import(names=[alias])
                    single.lineno = node.lineno
                    grp = _classify(alias.name, 0, third_party_pkgs)
                    groups[grp].append(single)
            else:
                mod = node.names[0].name if isinstance(node, ast.Import) else (node.module or "")
                lvl = 0 if isinstance(node, ast.Import) else (node.level or 0)
                groups[_classify(mod, lvl, third_party_pkgs)].append(node)
        for g in groups.values():
            g.sort(key=_sort_key)
        sections: list[str] = []
        for key in ("future", "stdlib", "third_party", "local"):
            if not groups[key]:
                continue
            sec_lines: list[str] = []
            seen: set[str] = set()
            for node in groups[key]:
                formatted = _format(node)
                block = "\n".join(formatted)
                if block not in seen:
                    seen.add(block)
                    for fl in formatted:
                        sec_lines.append(f"{indent}{fl}")
            sections.append("\n".join(sec_lines))
        new_block = "\n\n".join(sections) + "\n"
        original = "".join(lines[first : last + 1])
        if not original.endswith("\n"):
            original += "\n"
        if original == new_block:
            continue

        changed = True
        file_abs = str(path.resolve()).replace("\\", "/")
        msgs.append(
            f"  {Fore.YELLOW}Import order issues in {func_node.name}(){Style.RESET_ALL} "
            f'{Fore.CYAN}>>> code "{file_abs}:{imp_nodes[0].lineno}"{Style.RESET_ALL}'
        )
        if AUTO_FIX:
            lines = lines[:first] + [new_block] + lines[last + 1 :]
            msgs.append(f"    {Fore.GREEN}-> fixed{Style.RESET_ALL}")
    if AUTO_FIX and changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed, msgs


def _sort_dunder_all(src: str, path: Path) -> tuple[bool, list[str]]:
    """
    Sort ``__all__`` lists alphabetically in-place.

    Args:
        src (str): The original source code.
        path (Path): The path to the file being processed (for messages).

    Returns:
        tuple[bool, list[str]]:
            bool: True if the file was modified, False otherwise.
            list[str]: A list of messages describing any issues found or fixes applied.
    """
    msgs: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False, []

    lines = src.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id == "__all__"):
            continue
        value = node.value
        if not isinstance(value, ast.List):
            continue
        elements = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                elements.append(elt.value)
            else:
                # Non-string element, skip sorting this __all__
                elements = []
                break
        if not elements:
            continue

        sorted_elements = sorted(elements, key=str.lower)
        if sorted_elements == elements:
            continue

        first_line = node.lineno - 1
        last_line = (node.end_lineno or node.lineno) - 1

        # Determine indentation from original
        original_line = lines[first_line]
        indent = original_line[: len(original_line) - len(original_line.lstrip())]

        # Build new __all__ assignment
        quoted = [f'"{e}"' for e in sorted_elements]
        single = f"{indent}__all__ = [{', '.join(quoted)}]"
        if len(single) <= LINE_LENGTH:
            new_text = single + "\n"
        else:
            inner = ",\n".join(f"{indent}    {q}" for q in quoted)
            new_text = f"{indent}__all__ = [\n{inner},\n{indent}]\n"
        replacements.append((first_line, last_line, new_text))
    if not replacements:
        return False, []

    # Apply replacements from bottom to top
    replacements.sort(key=lambda r: r[0], reverse=True)
    for first_line, last_line, new_text in replacements:
        lines[first_line : last_line + 1] = [new_text]
    file_abs = str(path.resolve()).replace("\\", "/")
    first_lineno = replacements[0][0] + 1
    msgs.append(
        f"  {Fore.YELLOW}__all__ not sorted in{Style.RESET_ALL} "
        f'{Fore.CYAN}>>> code "{file_abs}:{first_lineno}"{Style.RESET_ALL}'
    )
    if AUTO_FIX:
        path.write_text("".join(lines), encoding="utf-8")
        msgs.append(f"    {Fore.GREEN}-> fixed{Style.RESET_ALL}")
    return True, msgs


def _update_init_files(base_dirs: list[str]) -> list[str]:
    """
    Update ``__init__.py`` files to re-export names shortened during local import consolidation.

    Args:
        base_dirs (list[str]): List of base directories to search for packages.

    Returns:
        list[str]: A list of messages describing any updates made to ``__init__.py`` files.
    """
    msgs: list[str] = []
    if not _init_updates or not AUTO_FIX:
        return msgs

    for (package, sub_module), names in _init_updates.items():
        # Find the package directory in any of the base dirs
        init_path = None
        for d in base_dirs:
            candidate = Path(d) / package / "__init__.py"
            if candidate.exists():
                init_path = candidate
                break
        if init_path is None:
            continue

        # Parse existing __init__.py to find what's already exported
        try:
            init_src = init_path.read_text(encoding="utf-8")
            init_tree = ast.parse(init_src)
        except (SyntaxError, OSError):
            continue

        # Collect already-imported names from this sub-module
        existing_names: set[str] = set()
        existing_node: ast.ImportFrom | None = None
        for node in ast.iter_child_nodes(init_tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level == 1 and node.module == sub_module:
                existing_node = node
                for alias in node.names:
                    existing_names.add(alias.name)
        missing_names = sorted(names - existing_names, key=str.lower)
        if not missing_names:
            continue

        init_lines = init_src.splitlines(keepends=True)
        file_abs = str(init_path.resolve()).replace("\\", "/")
        if existing_node:
            # Add missing names to existing import line
            all_names = sorted(
                existing_names | set(missing_names),
                key=str.lower,
            )
            new_import = f"from .{sub_module} import {', '.join(all_names)}"
            if len(new_import) > LINE_LENGTH:
                parts_str = ",\n".join(f"    {n}" for n in all_names)
                new_import = f"from .{sub_module} import (\n{parts_str},\n)"
            first_line = existing_node.lineno - 1
            last_line = (existing_node.end_lineno or existing_node.lineno) - 1
            init_lines[first_line : last_line + 1] = [new_import + "\n"]
        else:
            # Add new import line at the end of existing imports
            new_import = f"from .{sub_module} import {', '.join(missing_names)}"
            if len(new_import) > LINE_LENGTH:
                parts_str = ",\n".join(f"    {n}" for n in missing_names)
                new_import = f"from .{sub_module} import (\n{parts_str},\n)"

            # Find insertion point: after last import statement
            insert_at = len(init_lines)
            for i, node_i in enumerate(ast.iter_child_nodes(init_tree)):
                if isinstance(node_i, (ast.Import, ast.ImportFrom)):
                    insert_at = node_i.end_lineno or node_i.lineno
            init_lines.insert(insert_at, new_import + "\n")
        init_path.write_text("".join(init_lines), encoding="utf-8")

        # Update __all__ list if it exists
        updated_src = init_path.read_text(encoding="utf-8")
        try:
            updated_tree = ast.parse(updated_src)
        except SyntaxError:
            updated_tree = None
        if updated_tree:
            for node in ast.iter_child_nodes(updated_tree):
                if not isinstance(node, ast.Assign):
                    continue
                if len(node.targets) != 1:
                    continue
                target = node.targets[0]
                if not (isinstance(target, ast.Name) and target.id == "__all__"):
                    continue
                if not isinstance(node.value, ast.List):
                    continue
                current_all: list[str] = []
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        current_all.append(elt.value)
                new_all = sorted(set(current_all) | set(missing_names), key=str.lower)
                if new_all != current_all:
                    all_lines = updated_src.splitlines(keepends=True)
                    all_first = node.lineno - 1
                    all_last = (node.end_lineno or node.lineno) - 1
                    all_indent = all_lines[all_first][: len(all_lines[all_first]) - len(all_lines[all_first].lstrip())]
                    quoted = [f'"{e}"' for e in new_all]
                    single = f"{all_indent}__all__ = [{', '.join(quoted)}]"
                    if len(single) <= LINE_LENGTH:
                        new_text = single + "\n"
                    else:
                        inner = ",\n".join(f"{all_indent}    {q}" for q in quoted)
                        new_text = f"{all_indent}__all__ = [\n{inner},\n{all_indent}]\n"
                    all_lines[all_first : all_last + 1] = [new_text]
                    init_path.write_text("".join(all_lines), encoding="utf-8")
                break

        msgs.append(
            f"  {Fore.YELLOW}Updated __init__.py for {package}.{sub_module}{Style.RESET_ALL} "
            f'{Fore.CYAN}>>> code "{file_abs}:1"{Style.RESET_ALL}'
        )
        msgs.append(f"    {Fore.GREEN}-> added re-exports: {', '.join(missing_names)}{Style.RESET_ALL}")
    _init_updates.clear()
    return msgs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    """
    Run import sorting on all Python files.

    Returns:
        int: Exit code (0 if all imports are correctly sorted or fixed, 1 if issues remain).
    """
    third_party_pkgs = _third_party_packages()
    dirs: list[str] = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not dirs:
        dirs = ["source", "tests"]
    issues = 0
    for d in dirs:
        for fp in sorted(glob(f"{d}/**/*.py", recursive=True)):
            p = Path(fp)
            if "venv" in p.parts or "__pycache__" in p.parts:
                continue
            changed, msgs = _process(p, third_party_pkgs)
            for m in msgs:
                print(m)  # noqa: print
            if changed:
                issues += 1

    # Update __init__.py files for consolidated local imports
    init_msgs = _update_init_files(dirs)
    for m in init_msgs:
        print(m)  # noqa: print
    if init_msgs:
        issues += 1
    if issues == 0:
        print(f"{Fore.GREEN}All imports are correctly sorted{Style.RESET_ALL}")  # noqa: print
        return 0
    if AUTO_FIX:
        print(f"\n{Fore.GREEN}Fixed imports in {issues} file(s){Style.RESET_ALL}")  # noqa: print
        return 0
    print(f"\n{Fore.RED}Import issues in {issues} file(s){Style.RESET_ALL}")  # noqa: print
    print(f"{Fore.YELLOW}Run 'python import_sorter.py --fix' to auto-fix{Style.RESET_ALL}")  # noqa: print
    return 1


if __name__ == "__main__":
    sys.exit(main())
