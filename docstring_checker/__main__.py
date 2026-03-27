"""Main entry point for docstring checker."""

import sys
from argparse import ArgumentParser
from pathlib import Path
from os.path import isdir, join
from os import walk as os_walk

from rich.console import Console, Group
from rich.panel import Panel

from .config import SKIP_DIRS, CONSOLE_THEME
from .formatter import fix_file
from .processor import process_file


def should_skip_directory(root: str, skip_dirs: list[str]) -> bool:
    """
    Check if a directory should be skipped during traversal.

    Args:
        root (str): The directory path.
        skip_dirs (list[str]): List of directory names to skip.

    Returns:
        bool: True if directory should be skipped, False otherwise.
    """
    path_parts = root.split("\\")
    for skip_dir in skip_dirs:
        if skip_dir in path_parts:
            return True
    return any(part in SKIP_DIRS for part in path_parts)


def main() -> None:
    """Main entry point for the docstring checker."""
    parser = ArgumentParser(description="Validates consistency between function signatures and docstrings.")
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Paths to directories or files to check docstrings.",
    )
    parser.add_argument("-d", "--dirs", nargs="+", help="List of directories to ignore.")
    parser.add_argument("-f", "--files", nargs="+", help="List of files to ignore.")
    parser.add_argument("-n", "--names", nargs="+", help="List of function names to ignore.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output.")
    parser.add_argument("--json-output", type=Path, help="Directory path for JSON issue report output.")
    args = parser.parse_args()
    args.dirs = args.dirs or []
    args.files = args.files or []
    args.names = args.names or []
    console = Console(theme=CONSOLE_THEME, force_terminal=True)
    total_files = 0
    total_functions = 0
    total_mismatches = 0
    total_fixed = 0
    all_issues = []
    for directory in args.paths:
        directory = Path(directory).resolve()
        if not isdir(directory):
            console.print(f"[bold red]Invalid directory:[/bold red] " f"[highlight_color]{directory}[/highlight_color]")
            continue
        for root, _, files in os_walk(directory):
            if should_skip_directory(root, args.dirs):
                continue
            for file in files:
                if file.endswith(".py") and file not in args.files:
                    total_files += 1
                    file_path = join(root, file)
                    relative_path = Path(file_path).relative_to(directory)
                    if fix_file(file_path):
                        total_fixed += 1
                        console.print(
                            f"[base_color]Fixed:[/base_color] [highlight_color]{relative_path}[/highlight_color]"
                        )
                    func_count, mismatch_count, mismatches_boxes, file_issues = process_file(
                        file_path, args.names, args.verbose
                    )
                    total_functions += func_count
                    total_mismatches += mismatch_count
                    if file_issues:
                        for issue in file_issues:
                            all_issues.append({"file": str(relative_path), **issue})
                    if mismatches_boxes:
                        console.print(
                            Panel(
                                Group(*mismatches_boxes),
                                title=f"[base_color]Checking file:[/base_color] "
                                f"[highlight_color]{relative_path}[/highlight_color]",
                                border_style="green",
                            )
                        )
        console.print(f"[base_color]Stats for [highlight_color]{directory}" f"[/highlight_color]:[/base_color]")
        console.print(
            f"    [base_color]Checked [second_highlight_color]{total_files}"
            f"[/second_highlight_color] files with "
            f"[second_highlight_color]{total_functions}[/second_highlight_color] "
            f"functions.[/base_color]"
        )
        console.print(
            f"    [base_color]Fixed docstring formatting in [second_highlight_color]{total_fixed}"
            f"[/second_highlight_color] file(s).[/base_color]"
        )
        console.print(
            f"    [base_color]Found [bold red]{total_mismatches}[/bold red] " f"mismatches in docstrings.[/base_color]"
        )
    if args.json_output:
        import json

        json_path = Path(args.json_output) / "docstring_issues.json"
        if all_issues:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(all_issues, indent=2, ensure_ascii=False), encoding="utf-8")
        elif json_path.exists():
            json_path.unlink()
        sys.stderr.write(f"DOCCHECK_MISMATCHES:{total_mismatches}\n")
        sys.stderr.flush()


if __name__ == "__main__":
    main()
