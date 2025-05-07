from argparse import ArgumentParser, Namespace
from os import walk
from os.path import isdir, join, exists, relpath
from pathlib import Path
from pathspec import PathSpec


def count_lines_in_file(file_path: str) -> tuple[int, int]:
    """
    Count lines of code in a file.

    Args:
        file_path (str): Path to the file.

    Returns:
        tuple[int, int]: Number of code lines and total lines in the file.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            code_lines = sum(1 for line in file if line.strip() != "")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            total_lines = sum(1 for _ in file)
        return code_lines, total_lines
    except Exception as e:
        print(f"Error while reading {file_path}: {e}")
        return 0, 0


def count_lines_in_directory(args: Namespace, directory_path: str) -> tuple[int, int, dict[str, list[int]]]:
    """
    Count lines of code in a directory and its subdirectories.

    Args:
        args (Namespace): Command line arguments.
        directory_path (str): Path to the directory.

    Returns:
        tuple[int, int, dict[str, list[int]]]: Total code lines, total lines, and a dictionary with file paths as keys and a list of code lines and total lines as values.
    """
    total_lines = 0
    total_code_lines = 0
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
                code_line_count, line_count = count_lines_in_file(file_path)
                file_counts[file_path] = [code_line_count, line_count]
                total_lines += line_count
                total_code_lines += code_line_count
    return total_code_lines, total_lines, file_counts


def load_gitignore_spec(directory_path: str) -> PathSpec:
    """
    Load the .gitignore file from the specified directory and return a PathSpec object.

    Args:
        directory_path (str): Path to the directory.

    Returns:
        PathSpec: A PathSpec object representing the patterns in the .gitignore file.
    """
    gitignore_path = join(directory_path, ".gitignore")
    if not exists(gitignore_path):
        return None

    with open(gitignore_path, "r") as f:
        patterns = f.read().splitlines()
    return PathSpec.from_lines("gitwildmatch", patterns)


def main() -> None:
    parser = ArgumentParser(description = "Count lines of code in Python files.")
    parser.add_argument("paths", nargs = "+", type = Path, help = "Paths to directories or files to count lines of code.")
    parser.add_argument("-e", "--ext", nargs = "+", help = "List of file extensions, like: py pyw")
    parser.add_argument("-f", "--files", nargs = "+", help = "List of files to ignore, like: file1.py file2.py")
    parser.add_argument("-d", "--directories", nargs = "+", help = "List of directories to ignore, like: dir1 dir2")
    parser.add_argument("-g", "--gitignore", action = "store_true", help = "Ignore files in .gitignore")
    parser.add_argument("-v", "--verbose", action = "store_true", help = "Verbose output")
    args = parser.parse_args()
    if args.ext is None:
        args.ext = []
    if args.files is None:
        args.files = []
    if args.directories is None:
        args.directories = []
    total_code_lines = 0
    total_lines = 0
    for directory in args.paths:
        directory = Path(directory).resolve()
        if isdir(directory):
            directory_code_lines, directory_lines, file_counts = count_lines_in_directory(args, directory)
            total_code_lines += directory_code_lines
            total_lines += directory_lines
            if args.verbose:
                print(f"Directory: {directory}")
                for file, lines in file_counts.items():
                    if lines[1] == 0:
                        print(f"{file}: {lines[0]}/{lines[1]}")
                    else:
                        print(f"{file}: {lines[0]}/{lines[1]} lines => {lines[0] / lines[1] * 100:.2f}%")
                print(f"Total code lines in {directory}: {directory_code_lines}/{directory_lines}\n")
        else:
            print(f"Invalid directory: {directory}")
    print(f"Code percentage: {total_code_lines / total_lines * 100:.2f}%")
    print(f"Code to space ratio: {total_code_lines / (total_lines - total_code_lines):.2f}/1")
    print(f"Total empty lines: {total_lines - total_code_lines}")
    print(f"Total code lines in all directories: {total_code_lines}/{total_lines}")


if __name__ == "__main__":
    main()