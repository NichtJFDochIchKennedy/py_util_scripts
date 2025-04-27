from argparse import ArgumentParser
from os import walk
from os.path import isdir, join
from pathlib import Path


def count_lines_in_file(file_path: str) -> tuple[int, int]:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            code_lines = sum(1 for line in file if line.strip() != "")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            total_lines = sum(1 for _ in file)
        return code_lines, total_lines
    except Exception as e:
        print(f"Error while reading {file_path}: {e}")
        return 0


def count_lines_in_directory(directory_path: str, extensions: list[str] = ["py"]):
    total_lines = 0
    total_code_lines = 0
    file_counts = {}
    for root, _, files in walk(directory_path):
        if "venv" in root:
            continue
        for file in files:
            if extensions == [] or file.split(".")[-1] in extensions:
                file_path = join(root, file)
                code_line_count, line_count = count_lines_in_file(file_path)
                file_counts[file_path] = [code_line_count, line_count]
                total_lines += line_count
                total_code_lines += code_line_count
    return total_code_lines, total_lines, file_counts


def main():
    parser = ArgumentParser(description = "Count lines of code in Python files.")
    parser.add_argument("paths", nargs="+", type=Path, help="Paths to directories or files to count lines of code.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-e", "--ext", nargs="+", help="List of file extensions, like: py pyw")
    args = parser.parse_args()
    if args.ext is None:
        args.ext = []
    total_code_lines = 0
    total_lines = 0
    for directory in args.paths:
        directory = Path(directory).resolve()
        if isdir(directory):
            directory_code_lines, directory_lines, file_counts = count_lines_in_directory(directory, args.ext)
            total_code_lines += directory_code_lines
            total_lines += directory_lines
            if args.verbose:
                print(f"Directory: {directory}")
                for file, lines in file_counts.items():
                    print(f"{file}: {lines[0]}/{lines[1]} lines")
                print(f"Total code lines in {directory}: {directory_code_lines}/{directory_lines}\n")
        else:
            print(f"Invalid directory: {directory}")
    print(f"Code percentage: {total_code_lines / total_lines * 100:.2f}%")
    print(f"Code to space ratio: {total_code_lines / (total_lines - total_code_lines):.2f}/1")
    print(f"Total empty lines: {total_lines - total_code_lines}")
    print(f"Total code lines in all directories: {total_code_lines}/{total_lines}")


if __name__ == "__main__":
    main()