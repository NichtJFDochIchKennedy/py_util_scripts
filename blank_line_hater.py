import sys
from ast import (
    AST,
    AsyncFunctionDef,
    Constant,
    Dict,
    Expr,
    FunctionDef,
    Import,
    ImportFrom,
    List,
    parse,
    Set,
    Tuple,
    walk,
)
from collections import defaultdict
from glob import glob
from pathlib import Path

from colorama import Fore, init, Style

init(autoreset=True)

AUTO_FIX = "--fix" in sys.argv or "--auto-fix" in sys.argv


def apply_fixes_to_file(file_path: str, file_issues: list[dict]) -> bool:
    """
    Apply all fixes to a file. Works backwards to avoid line number shifts.

    Args:
        file_path (str): Path to the file to fix.
        file_issues (list[dict]): List of issues to fix, each with 'line' and 'type' keys.

    Returns:
        bool: True if fixes were applied successfully, False otherwise.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
        sorted_issues = sorted(file_issues, key=lambda x: x["line"], reverse=True)
        for issue in sorted_issues:
            line_idx = issue["line"] - 1
            if issue["type"] == "must_remove":
                if line_idx < len(lines) and lines[line_idx].strip() == "":
                    lines.pop(line_idx)
            elif issue["type"] == "must_add":
                if line_idx < len(lines):
                    lines.insert(line_idx, "\n")
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"{Fore.RED}Error fixing {file_path}: {e}{Style.RESET_ALL}")
        return False


def has_docstring(node: FunctionDef | AsyncFunctionDef) -> bool:
    """
    Check if the function has a docstring.

    Args:
        node (FunctionDef | AsyncFunctionDef): The function definition node.

    Returns:
        bool: True if the function has a docstring, False otherwise.
    """
    if node.body and isinstance(node.body[0], Expr):
        expr = node.body[0]
        if isinstance(expr.value, Constant) and isinstance(expr.value.value, str):
            return True
    return False


def get_docstring_end_index(node: FunctionDef | AsyncFunctionDef) -> int:
    """
    Return the 1-based line number where the docstring ends.

    Args:
        node (FunctionDef | AsyncFunctionDef): The function definition node.

    Returns:
        int: The line number where the docstring ends, or the function start line if no docstring.
    """
    if has_docstring(node):
        docstring_const = node.body[0].value
        return docstring_const.end_lineno
    return node.lineno - 1


def get_indent_level(line: str) -> int:
    """
    Return the indentation level of a line.

    Args:
        line (str): The line of code.

    Returns:
        int: The number of leading spaces in the line.
    """
    return len(line) - len(line.lstrip())


def is_block_start(line: str) -> bool:
    """
    Check if a line starts a new block (try, except, if, for, def, class, etc.).

    Args:
        line (str): The line of code.

    Returns:
        bool: True if the line starts a new block, False otherwise.
    """
    stripped = line.strip()
    return stripped.endswith(":") and any(
        stripped.startswith(kw)
        for kw in [
            "try:",
            "except",
            "if ",
            "elif ",
            "else:",
            "while ",
            "for ",
            "with ",
            "finally:",
            "def ",
            "async def ",
            "class ",
        ]
    )


def is_nested_def_or_class(line: str) -> bool:
    """
    Check if a line is a nested function or class definition.

    Args:
        line (str): The line of code.

    Returns:
        bool: True if the line is a nested function or class definition, False otherwise.
    """
    stripped = line.strip()
    return stripped.startswith("def ") or stripped.startswith("async def ") or stripped.startswith("class ")


def is_comment(line: str) -> bool:
    """
    Check if a line is a standalone comment (starts with #).

    Args:
        line (str): The line of code.

    Returns:
        bool: True if the line is a standalone comment, False otherwise.
    """
    stripped = line.strip()
    return len(stripped) > 0 and stripped.startswith("#")


def is_section_header_block(lines: list[str], block_start: int, block_end: int) -> bool:
    """
    Check if a comment block (block_start..block_end inclusive) is a section header.

    Args:
        lines (list[str]): The list of lines in the file.
        block_start (int): The starting line index of the comment block.
        block_end (int): The ending line index of the comment block.

    Returns:
        bool: True if the block is a section header, False otherwise.
    """
    for idx in range(block_start, block_end + 1):
        stripped = lines[idx].strip().lstrip("#").strip()
        if len(stripped) >= 3 and (all(ch == "=" for ch in stripped) or all(ch == "-" for ch in stripped)):
            return True
    return False


def collect_container_ranges(node: AST) -> set[int]:
    """
    Collect (start_line, end_line) 0-indexed ranges for multi-line container literals.

    Covers Dict, List, Set, and Tuple literals that span more than one line.

    Args:
        node (AST): The AST node to analyze.

    Returns:
        set[int]: A set of line indices (0-indexed) that are part of multi-line container literals.
    """
    ranges = set()
    for child in walk(node):
        if isinstance(child, (Dict, List, Set, Tuple)):
            if hasattr(child, "lineno") and hasattr(child, "end_lineno"):
                if child.end_lineno > child.lineno:
                    for ln in range(child.lineno - 1, child.end_lineno):
                        ranges.add(ln)
    return ranges


issues = defaultdict(list)

for file_path in sorted(glob("**/*.py", recursive=True)):
    if "venv" in Path(file_path).parts or "__pycache__" in Path(file_path).parts or file_path.startswith("."):
        continue
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
        tree = parse("".join(lines))
        for node in walk(tree):
            if isinstance(node, (FunctionDef, AsyncFunctionDef)):
                start = node.lineno - 1
                end = node.end_lineno
                docstring_end = get_docstring_end_index(node)
                func_indent = get_indent_level(lines[start])
                code_indent = func_indent + 4
                imports_in_func = {}
                first_code_index = None
                for idx, child in enumerate(node.body):
                    if idx == 0 and isinstance(child, Expr):
                        if isinstance(child.value, Constant) and isinstance(child.value.value, str):
                            continue
                    if first_code_index is None:
                        first_code_index = idx
                    if isinstance(child, (Import, ImportFrom)):
                        import_line_idx = child.lineno - 1
                        if import_line_idx < len(lines):
                            import_indent = get_indent_level(lines[import_line_idx])
                            if import_indent == code_indent:
                                imports_in_func[child.lineno] = (child, idx)
                for child in walk(node):
                    if isinstance(child, (Import, ImportFrom)):
                        import_line_idx = child.lineno - 1
                        if import_line_idx < len(lines) and child.lineno not in imports_in_func:
                            import_indent = get_indent_level(lines[import_line_idx])
                            if import_indent >= code_indent:
                                imports_in_func[child.lineno] = (child, -1)
                nested_body_lines = set()
                for child in walk(node):
                    if child is not node and isinstance(child, (FunctionDef, AsyncFunctionDef)):
                        for ln in range(child.lineno, child.end_lineno + 1):
                            nested_body_lines.add(ln)
                container_lines = collect_container_ranges(node)
                # Track end lines of multi-line imports for blank-line-after-import checks
                import_end_lines = {node.end_lineno for node, _ in imports_in_func.values()}
                i = docstring_end
                last_was_import = False
                while i < end:
                    line_num = i + 1
                    current_line = lines[i].strip()
                    if len(current_line) == 0:
                        empty_count = 1
                        j = i + 1
                        while j < end and len(lines[j].strip()) == 0:
                            empty_count += 1
                            j += 1
                        if empty_count >= 2:
                            issues[file_path].append(
                                {
                                    "function": node.name,
                                    "line": line_num,
                                    "file": file_path,
                                    "type": "must_remove",
                                    "reason": f"{empty_count} empty lines in a row",
                                    "async": isinstance(node, AsyncFunctionDef),
                                }
                            )
                        elif empty_count == 1:
                            line_before = i - 1
                            if line_before >= docstring_end:
                                while line_before >= docstring_end and lines[line_before].strip() == "":
                                    line_before -= 1
                                if line_before >= docstring_end:
                                    line_before_num = line_before + 1
                                    if line_before_num in imports_in_func or line_before_num in import_end_lines:
                                        i = j
                                        continue
                            if j < end and len(lines[j].strip()) > 0:
                                next_line_num = j + 1
                                # Rule 5: Remove blank between comment and function/class def
                                if (
                                    is_nested_def_or_class(lines[j])
                                    and line_before >= docstring_end
                                    and is_comment(lines[line_before])
                                ):
                                    issues[file_path].append(
                                        {
                                            "function": node.name,
                                            "line": line_num,
                                            "file": file_path,
                                            "type": "must_remove",
                                            "reason": "Blank between comment and def/class",
                                            "async": isinstance(node, AsyncFunctionDef),
                                        }
                                    )
                                elif is_nested_def_or_class(lines[j]):
                                    pass
                                # Rule 6: Keep blank before comment block (not in containers)
                                elif is_comment(lines[j]) and i not in container_lines:
                                    pass
                                # Rule 6: Keep blank after section-header comment block only
                                elif (
                                    line_before >= docstring_end
                                    and is_comment(lines[line_before])
                                    and i not in container_lines
                                ):
                                    # Walk back to find the comment block start
                                    blk_start = line_before
                                    while blk_start > docstring_end and is_comment(lines[blk_start - 1]):
                                        blk_start -= 1
                                    if is_section_header_block(lines, blk_start, line_before):
                                        pass  # keep blank after section header
                                    elif next_line_num in imports_in_func:
                                        pass  # keep blank before an import
                                    else:
                                        issues[file_path].append(
                                            {
                                                "function": node.name,
                                                "line": line_num,
                                                "file": file_path,
                                                "type": "must_remove",
                                                "reason": "Blank after comment (not a section header)",
                                                "async": isinstance(node, AsyncFunctionDef),
                                            }
                                        )
                                elif next_line_num in imports_in_func:
                                    pass
                                elif j >= end:
                                    pass
                                elif i > 0 and any(
                                    lines[i - 1].strip().startswith(kw)
                                    for kw in ["return", "yield", "pass", "raise", "break", "continue"]
                                ):
                                    pass
                                elif i > 0 and line_before >= docstring_end and (line_before + 1) in nested_body_lines:
                                    pass
                                elif i > 0:
                                    issues[file_path].append(
                                        {
                                            "function": node.name,
                                            "line": line_num,
                                            "file": file_path,
                                            "type": "must_remove",
                                            "reason": "Empty line in code",
                                            "async": isinstance(node, AsyncFunctionDef),
                                        }
                                    )
                        i = j
                        continue
                    if line_num in imports_in_func:
                        import_node, import_body_index = imports_in_func[line_num]
                        is_first_code_statement = import_body_index == first_code_index
                        # Account for multi-line imports (e.g. from X import (\n ...\n))
                        import_end_line = import_node.end_lineno  # 1-indexed last line
                        import_end_idx = import_end_line - 1  # 0-indexed
                        line_before_import = i - 1
                        line_before_is_block = False
                        line_before_is_import = False
                        while line_before_import >= docstring_end and lines[line_before_import].strip() == "":
                            line_before_import -= 1
                        if line_before_import >= docstring_end:
                            prev_line = lines[line_before_import]
                            line_before_is_block = is_block_start(prev_line)
                            line_before_num = line_before_import + 1
                            line_before_is_import = line_before_num in imports_in_func
                        # Check line after import end (not just i+1) for multi-line imports
                        after_import_idx = import_end_idx + 1  # 0-indexed
                        after_import_num = import_end_line + 1  # 1-indexed
                        if is_first_code_statement:
                            if after_import_idx < end:
                                if after_import_num not in imports_in_func:
                                    if lines[after_import_idx].strip() != "":
                                        issues[file_path].append(
                                            {
                                                "function": node.name,
                                                "line": after_import_num,
                                                "file": file_path,
                                                "type": "must_add",
                                                "reason": "Import needs empty line after",
                                                "async": isinstance(node, AsyncFunctionDef),
                                            }
                                        )
                        elif line_before_is_block or line_before_is_import:
                            if after_import_idx < end:
                                if after_import_num not in imports_in_func:
                                    if lines[after_import_idx].strip() != "":
                                        issues[file_path].append(
                                            {
                                                "function": node.name,
                                                "line": after_import_num,
                                                "file": file_path,
                                                "type": "must_add",
                                                "reason": "Import needs empty line after",
                                                "async": isinstance(node, AsyncFunctionDef),
                                            }
                                        )
                        else:
                            if after_import_idx < end:
                                if after_import_num not in imports_in_func:
                                    if lines[after_import_idx].strip() != "":
                                        issues[file_path].append(
                                            {
                                                "function": node.name,
                                                "line": after_import_num,
                                                "file": file_path,
                                                "type": "must_add",
                                                "reason": "Import needs empty line after",
                                                "async": isinstance(node, AsyncFunctionDef),
                                            }
                                        )
                            if i > docstring_end and lines[i - 1].strip() != "":
                                issues[file_path].append(
                                    {
                                        "function": node.name,
                                        "line": line_num,
                                        "file": file_path,
                                        "type": "must_add",
                                        "reason": "Import needs empty line before",
                                        "async": isinstance(node, AsyncFunctionDef),
                                    }
                                )
                        last_was_import = True
                        # Skip past multi-line import body
                        if import_end_idx > i:
                            i = import_end_idx
                    else:
                        last_was_import = False
                        # Rule 6: Ensure blank lines around comment blocks (skip inside containers)
                        if current_line.startswith("#") and i not in container_lines:
                            prev_is_comment = i > docstring_end and is_comment(lines[i - 1])
                            next_is_comment = (i + 1) < end and is_comment(lines[i + 1])
                            # First comment in block: need blank line above
                            if not prev_is_comment and i > docstring_end:
                                prev_line = lines[i - 1].strip()
                                if (
                                    prev_line != ""
                                    and not prev_line.startswith("#")
                                    and not is_block_start(lines[i - 1])
                                ):
                                    issues[file_path].append(
                                        {
                                            "function": node.name,
                                            "line": line_num,
                                            "file": file_path,
                                            "type": "must_add",
                                            "reason": "Comment needs empty line before",
                                            "async": isinstance(node, AsyncFunctionDef),
                                        }
                                    )
                            # Last comment in block: need blank line below
                            # ONLY for section-header blocks (containing # === or # --- lines)
                            # (unless followed by a function/class def — rule 5)
                            if not next_is_comment and (i + 1) < end:
                                next_line = lines[i + 1].strip()
                                if (
                                    next_line != ""
                                    and not is_nested_def_or_class(lines[i + 1])
                                    and not next_line.startswith("#")
                                    and (i + 2) not in imports_in_func
                                ):
                                    # Walk backwards to find the start of this comment block

                                    block_start = i
                                    while block_start > docstring_end and is_comment(lines[block_start - 1]):
                                        block_start -= 1
                                    if is_section_header_block(lines, block_start, i):
                                        issues[file_path].append(
                                            {
                                                "function": node.name,
                                                "line": line_num + 1,
                                                "file": file_path,
                                                "type": "must_add",
                                                "reason": "Section header comment needs empty line after",
                                                "async": isinstance(node, AsyncFunctionDef),
                                            }
                                        )
                    i += 1
    except SyntaxError:
        print(f"{Fore.RED}x Syntax error in {file_path}{Style.RESET_ALL}")
    except Exception:
        print(f"{Fore.YELLOW}! Error in {file_path}{Style.RESET_ALL}")

if AUTO_FIX and issues:
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Auto-fixing issues...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")
    fixed_count = 0
    failed_count = 0
    for file_path, file_issues in issues.items():
        if apply_fixes_to_file(file_path, file_issues):
            fixed_count += len(file_issues)
            print(f"{Fore.GREEN}[+] Fixed {len(file_issues)} issue(s) in {file_path}{Style.RESET_ALL}")
        else:
            failed_count += len(file_issues)
            print(f"{Fore.RED}[-] Failed to fix {len(file_issues)} issue(s) in {file_path}{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Fixed: {fixed_count} issue(s){Style.RESET_ALL}")
    if failed_count > 0:
        print(f"{Fore.RED}Failed: {failed_count} issue(s){Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")
    sys.exit(0 if failed_count == 0 else 1)
if issues:
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.RED}Problems found:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")
    must_remove = defaultdict(list)

    must_add = defaultdict(list)
    for file_path, file_issues in issues.items():
        for issue in file_issues:
            if issue["type"] == "must_remove":
                must_remove[file_path].append(issue)
            else:
                must_add[file_path].append(issue)
    if must_remove:
        print(f"{Fore.RED}[v] EMPTY LINES TO REMOVE{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'-' * 80}{Style.RESET_ALL}\n")
        total_remove = 0
        for file_path in sorted(must_remove.keys(), key=lambda x: Path(x).as_posix()):
            print(f"{Fore.CYAN}{file_path}{Style.RESET_ALL}")
            for issue in sorted(must_remove[file_path], key=lambda x: x["line"]):
                func_type = f"{Fore.YELLOW}async {Style.RESET_ALL}" if issue["async"] else ""
                file_abs = str(Path(issue["file"]).resolve())
                powershell_cmd = f'code "{file_abs}:{issue["line"]}"'
                print(
                    f"  {func_type}{Fore.GREEN}{issue['function']}(){Style.RESET_ALL} "
                    f"- {Fore.RED}Line {issue['line']}{Style.RESET_ALL}: {issue['reason']}"
                )
                print(f"    {Fore.CYAN}>>> {powershell_cmd}{Style.RESET_ALL}")
                total_remove += 1
            print()
    if must_add:
        print(f"\n{Fore.GREEN}[^] EMPTY LINES TO ADD{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'-' * 80}{Style.RESET_ALL}\n")
        total_add = 0
        for file_path in sorted(must_add.keys(), key=lambda x: Path(x).as_posix()):
            print(f"{Fore.CYAN}{file_path}{Style.RESET_ALL}")
            for issue in sorted(must_add[file_path], key=lambda x: x["line"]):
                func_type = f"{Fore.YELLOW}async {Style.RESET_ALL}" if issue["async"] else ""
                file_abs = str(Path(issue["file"]).resolve())
                powershell_cmd = f'code "{file_abs}:{issue["line"]}"'
                print(
                    f"  {func_type}{Fore.GREEN}{issue['function']}(){Style.RESET_ALL} "
                    f"- {Fore.RED}Line {issue['line']}{Style.RESET_ALL}: {issue['reason']}"
                )
                print(f"    {Fore.CYAN}>>> {powershell_cmd}{Style.RESET_ALL}")
                total_add += 1
            print()
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    total = sum(len(v) for v in must_remove.values()) + sum(len(v) for v in must_add.values())
    if total == 1:
        print(f"{Fore.RED}Total: {total} problem{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Total: {total} problem(s){Style.RESET_ALL}")
    if must_remove:
        remove_count = sum(len(v) for v in must_remove.values())
        print(f"  {Fore.RED}[v] {remove_count} lines to remove{Style.RESET_ALL}")
    if must_add:
        add_count = sum(len(v) for v in must_add.values())
        print(f"  {Fore.GREEN}[^] {add_count} lines to add{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")
    print(
        f"{Fore.YELLOW}Tip: Run 'python blank_line_hater.py --fix' to automatically fix these issues{Style.RESET_ALL}\n"
    )
    sys.exit(1)
else:
    print(f"{Fore.GREEN}+ No problems found!{Style.RESET_ALL}\n")
    sys.exit(0)
