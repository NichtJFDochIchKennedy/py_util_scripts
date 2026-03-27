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
import sys
from glob import glob
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)
AUTO_FIX = "--fix" in sys.argv or "--auto-fix" in sys.argv
LINE_LENGTH = 120
STDLIB_MODULES: frozenset[str] = frozenset(sys.stdlib_module_names)
SOURCE_DIR = Path(__file__).parent / "source"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _local_packages() -> set[str]:
    """Auto-detect local package names from the *source/* directory."""
    pkgs: set[str] = set()
    if not SOURCE_DIR.is_dir():
        return pkgs
    for item in SOURCE_DIR.iterdir():
        if item.is_dir() and (item / "__init__.py").exists():
            pkgs.add(item.name)
        elif item.suffix == ".py" and item.name != "__init__.py":
            pkgs.add(item.stem)
    return pkgs


def _classify(module: str, level: int, local_pkgs: set[str]) -> str:
    """Return the group key for an import."""
    if module == "__future__":
        return "future"
    if level > 0:
        return "local"
    top = module.split(".")[0]
    if top in local_pkgs:
        return "local"
    if top in STDLIB_MODULES:
        return "stdlib"
    return "third_party"


def _sort_key(node: ast.Import | ast.ImportFrom) -> tuple[int, str]:
    """Sort key: ``import`` before ``from``, then alphabetically by module."""
    if isinstance(node, ast.Import):
        return (0, node.names[0].name.lower())
    dots = "." * (node.level or 0)
    mod = f"{dots}{node.module}" if node.module else dots
    return (1, mod.lower())


def _format(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Return the formatted line(s) for a single import node."""
    if isinstance(node, ast.Import):
        out: list[str] = []
        for alias in sorted(node.names, key=lambda a: a.name.lower()):
            out.append(f"import {alias.name} as {alias.asname}" if alias.asname else f"import {alias.name}")
        return out
    assert isinstance(node, ast.ImportFrom)
    dots = "." * (node.level or 0)
    module = f"{dots}{node.module}" if node.module else dots
    sorted_names = sorted(node.names, key=lambda a: a.name.lower())
    parts = [f"{a.name} as {a.asname}" if a.asname else a.name for a in sorted_names]
    single = f"from {module} import {', '.join(parts)}"
    if len(single) <= LINE_LENGTH:
        return [single]
    lines = [f"from {module} import ("]
    for part in parts:
        lines.append(f"    {part},")
    lines.append(")")
    return lines


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------
def _process(path: Path, local_pkgs: set[str]) -> tuple[bool, list[str]]:
    """Check / fix one file.  Returns ``(changed, messages)``."""
    msgs: list[str] = []
    try:
        src = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, [f"  {Fore.RED}read error {path}: {e}{Style.RESET_ALL}"]
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, [f"  {Fore.RED}syntax error {path}: {e}{Style.RESET_ALL}"]
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

    # --- classify & optionally split multi-name bare imports ---------------
    groups: dict[str, list[ast.Import | ast.ImportFrom]] = {
        "future": [],
        "stdlib": [],
        "third_party": [],
        "local": [],
    }
    for node in nodes:
        if isinstance(node, ast.Import) and len(node.names) > 1:
            for alias in node.names:
                single = ast.Import(names=[alias])
                grp = _classify(alias.name, 0, local_pkgs)
                groups[grp].append(single)
        else:
            mod = node.names[0].name if isinstance(node, ast.Import) else (node.module or "")
            lvl = 0 if isinstance(node, ast.Import) else (node.level or 0)
            groups[_classify(mod, lvl, local_pkgs)].append(node)
    for g in groups.values():
        g.sort(key=_sort_key)

    # --- collect & consolidate TYPE_CHECKING blocks -----------------------
    tc_if_nodes: list[ast.If] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if is_tc:
            tc_if_nodes.append(node)

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

    # --- rebuild import block ----------------------------------------------
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
                sec_lines.extend(formatted)
        sections.append("\n".join(sec_lines))
    new_block = "\n\n".join(sections) + "\n"

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
                    grp = _classify(alias.name, 0, local_pkgs)
                    tc_groups[grp].append(single)
            else:
                mod = node.names[0].name if isinstance(node, ast.Import) else (node.module or "")
                lvl = 0 if isinstance(node, ast.Import) else (node.level or 0)
                tc_groups[_classify(mod, lvl, local_pkgs)].append(node)
        for g in tc_groups.values():
            g.sort(key=_sort_key)
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    """Run import sorting on all Python files."""
    local_pkgs = _local_packages()
    dirs: list[str] = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not dirs:
        dirs = ["source", "tests"]
    issues = 0
    for d in dirs:
        for fp in sorted(glob(f"{d}/**/*.py", recursive=True)):
            p = Path(fp)
            if "venv" in p.parts or "__pycache__" in p.parts:
                continue
            changed, msgs = _process(p, local_pkgs)
            for m in msgs:
                print(m)  # noqa: print
            if changed:
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
