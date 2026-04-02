from argparse import ArgumentParser, Namespace
from os import walk
from os.path import exists, isdir, join, relpath
from pathlib import Path

from pathspec import PathSpec


def count_lines_in_file(file_path: str) -> tuple[int, int, int, int]:
    """
    Count lines of code in a file.

    Args:
        file_path (str): Path to the file.

    Returns:
        tuple[int, int, int, int]:
            int: Number of code lines.
            int: Total number of lines.
            int: Number of comment lines.
            int: Number of docstring lines.
    """
    try:
        total_lines = 0
        code_lines = 0
        comment_lines = 0
        docstring_lines = 0
        in_docstring = False
        docstring_delim = None
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            for line in file:
                total_lines += 1
                stripped = line.strip()

                # Docstring detection
                if not in_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                    in_docstring = True
                    docstring_delim = stripped[:3]
                    docstring_lines += 1

                    # One-line docstring
                    if stripped.count(docstring_delim) == 2:
                        in_docstring = False
                    continue
                elif in_docstring:
                    docstring_lines += 1
                    if docstring_delim and docstring_delim in stripped:
                        in_docstring = False
                    continue

                # Kommentar detection
                if stripped.startswith("#"):
                    comment_lines += 1
                    continue

                # Code line detection
                if stripped != "":
                    code_lines += 1
        return code_lines, total_lines, comment_lines, docstring_lines
    except Exception as e:
        print(f"Error while reading {file_path}: {e}")
        return 0, 0, 0, 0


def count_lines_in_directory(
    args: Namespace, directory_path: Path | str
) -> tuple[int, int, int, int, dict[str, list[int]]]:
    """
    Count lines of code in a directory and its subdirectories.

    Args:
        args (Namespace): Command line arguments.
        directory_path (Path | str): Path to the directory.

    Returns:
        tuple[int, int, int, int, dict[str, list[int]]]:
            int: Total number of code lines in the directory.
            int: Total number of lines in the directory.
            int: Total number of comment lines in the directory.
            int: Total number of docstring lines in the directory.
            dict[str, list[int]]: A dictionary mapping file paths to their respective counts of code lines,
            total lines, comment lines, and docstring lines.
    """
    total_lines = 0
    total_code_lines = 0
    total_comment_lines = 0
    total_docstring_lines = 0
    file_counts = {}
    gitignore_spec = load_gitignore_spec(directory_path) if args.gitignore else None
    for root, dirs, files in walk(directory_path):
        dirs[:] = [d for d in dirs if d not in args.directories]
        files[:] = [f for f in files if f not in args.files]
        if gitignore_spec and gitignore_spec.match_file(relpath(root, directory_path)):
            continue
        for file in files:
            file_path = join(root, file)
            rel_file_path = relpath(file_path, directory_path)
            if gitignore_spec and gitignore_spec.match_file(rel_file_path):
                continue
            if args.ext == [] or file.split(".")[-1] in args.ext:
                file_path = join(root, file)
                code_line_count, line_count, comment_lines, docstring_lines = count_lines_in_file(file_path)
                file_counts[file_path] = [code_line_count, line_count, comment_lines, docstring_lines]
                total_lines += line_count
                total_code_lines += code_line_count
                total_comment_lines += comment_lines
                total_docstring_lines += docstring_lines
    return total_code_lines, total_lines, total_comment_lines, total_docstring_lines, file_counts


def load_gitignore_spec(directory_path: Path | str) -> PathSpec | None:
    """
    Load the .gitignore file from the specified directory and return a PathSpec object.

    Args:
        directory_path (Path | str): Path to the directory.

    Returns:
        PathSpec | None: A PathSpec object representing the patterns in the .gitignore file.
    """
    gitignore_path = join(directory_path, ".gitignore")
    if not exists(gitignore_path):
        return None

    with open(gitignore_path, "r") as f:
        patterns = f.read().splitlines()
    return PathSpec.from_lines("gitwildmatch", patterns)


def main() -> None:
    """Main entry point for the line counter."""
    parser = ArgumentParser(description="Count lines of code in Python files.")
    parser.add_argument("paths", nargs="+", type=Path, help="Paths to directories or files to count lines of code.")
    parser.add_argument("-e", "--ext", nargs="+", help="List of file extensions, like: py pyw")
    parser.add_argument("-f", "--files", nargs="+", help="List of files to ignore, like: file1.py file2.py")
    parser.add_argument("-d", "--directories", nargs="+", help="List of directories to ignore, like: dir1 dir2")
    parser.add_argument("-g", "--gitignore", action="store_true", help="Ignore files in .gitignore")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    if args.ext is None:
        args.ext = []
    if args.files is None:
        args.files = []
    if args.directories is None:
        args.directories = []
    total_code_lines = 0
    total_lines = 0
    total_comment_lines = 0
    total_docstring_lines = 0
    for directory in args.paths:
        directory = Path(directory).resolve()
        if isdir(directory):
            directory_code_lines, directory_lines, directory_comment_lines, directory_docstring_lines, file_counts = (
                count_lines_in_directory(args, directory)
            )
            total_code_lines += directory_code_lines
            total_lines += directory_lines
            total_comment_lines += directory_comment_lines
            total_docstring_lines += directory_docstring_lines
            if args.verbose:
                print(f"Directory: {directory}")
                for file, lines in file_counts.items():
                    code, total, comment, docstring = lines
                    if total == 0:
                        print(f"{file}: {code}/{total} (comments: {comment}, docstrings: {docstring})")
                    else:
                        print(
                            f"{file}: {code}/{total} lines => {code / total * 100:.2f}% (comments: {comment}",
                            f", docstrings: {docstring})",
                        )
                print(
                    f"Total code lines in {directory}: {directory_code_lines}/{directory_lines} (comments: ",
                    f"{directory_comment_lines}, docstrings: {directory_docstring_lines})\n",
                )
        else:
            print(f"Invalid directory: {directory}")
    empty_lines = total_lines - total_code_lines - total_comment_lines - total_docstring_lines
    print(f"Code percentage: {total_code_lines / total_lines * 100:.2f}%")
    try:
        print(f"Code to space ratio: {total_code_lines / (empty_lines):.2f}/1")
    except ZeroDivisionError:
        print(f"Code to space ratio: {total_code_lines}/0")
    try:
        print(f"Code to comment ratio: {total_code_lines / total_comment_lines:.2f}/1")
    except ZeroDivisionError:
        print(f"Code to comment ratio: {total_code_lines}/0")
    try:
        print(f"Code to docstring ratio: {total_code_lines / total_docstring_lines:.2f}/1")
    except ZeroDivisionError:
        print(f"Code to docstring ratio: {total_code_lines}/0")
    print(f"Total empty lines: {empty_lines}")
    print(f"Total comment lines: {total_comment_lines}")
    print(f"Total docstring lines: {total_docstring_lines}")
    print(f"Total code lines in all directories: {total_code_lines}/{total_lines}")


if __name__ == "__main__":
    main()
