from argparse import ArgumentParser
from ast import FunctionDef, parse, unparse, get_docstring, walk as ast_walk, Return
from os import walk
from os.path import isdir, join
from pathlib import Path
from re import search, match, DOTALL
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme


def get_function_args_with_defaults(function: FunctionDef) -> dict:
    """
    Extracts argument names, types, and default values from a function definition.

    Args:
        function (FunctionDef): The function definition node.

    Returns:
        dict: A dictionary with argument names as keys and a dictionary of type and default value as values.
    """
    args = function.args.args
    defaults = function.args.defaults
    num_defaults = len(defaults)
    num_args = len(args)
    args_info = {}
    for i, arg in enumerate(args):
        has_default = i >= num_args - num_defaults
        default_value = None
        if has_default:
            default_node = defaults[i - (num_args - num_defaults)]
            default_value = unparse(default_node)
        arg_type = unparse(arg.annotation) if arg.annotation else None
        args_info[arg.arg] = {
            "type": arg_type,
            "default": default_value,
        }
    return args_info


def extract_args_from_docstring(docstring: str) -> dict:
    """
    Extracts argument names and types from a docstring.

    Args:
        docstring (str): The docstring to extract from.

    Returns:
        dict: A dictionary with argument names as keys and their types as values.
    """
    args = {}
    if not docstring:
        return args
    args_section = search(r"Args:\s*(.*?)(\n\n|\Z)", docstring, DOTALL)
    if args_section:
        args_text = args_section.group(1)
        lines = args_text.split('\n')
        for line in lines:
            matches = match(r'\s*(\w+)\s*\(([^)]+)\):', line)
            if matches:
                arg_name, arg_type = matches.groups()
                args[arg_name] = arg_type
    return args


def extract_docstring_arg_order(docstring: str) -> list[str]:
    """
    Extracts the order of argument names from a docstring.

    Args:
        docstring (str): The docstring to extract from.

    Returns:
        list[str]: A list of argument names in the order they appear in the docstring.
    """
    if not docstring:
        return []
    args = []
    in_args_section = False
    for line in docstring.splitlines():
        line = line.strip()
        if line.lower().startswith("args:"):
            in_args_section = True
            continue
        if in_args_section:
            if not line or not (line[0].isalpha() or line[0] == "_"):
                break
            matches = match(r"(\w+)(?:\s*\([^)]+\))?:", line)
            if matches:
                if matches.group(1) != "self":
                    args.append(matches.group(1))
    return args


def get_functions_from_file(filepath: str) -> list:
    """
    Parses a Python file and extracts all function definitions.

    Args:
        filepath (str): The path to the Python file.

    Returns:
        list: A list of function definition nodes.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    tree = parse(source)
    functions = []
    for node in ast_walk(tree):
        if isinstance(node, FunctionDef):
            functions.append(node)
    return functions


def function_has_return_value(function: FunctionDef) -> bool:
    """
    Checks if a function has a return value.

    Args:
        function (FunctionDef): The function definition node.

    Returns:
        bool: True if the function has a return value, False otherwise.
    """
    for node in ast_walk(function):
        if isinstance(node, Return) and node.value is not None:
            return True
    return False


def extract_return_from_function(function: FunctionDef) -> str:
    """
    Extracts the return type from a function definition.

    Args:
        function (FunctionDef): The function definition node.

    Returns:
        str: The return type as a string.
    """
    if function.returns:
        return unparse(function.returns)
    return None


def extract_return_from_docstring(docstring: str) -> str:
    """
    Extracts the return type from a docstring.

    Args:
        docstring (int): The docstring to extract from.

    Returns:
        str: The return type as a string.
    """
    if not docstring:
        return None
    matches = search(r"Returns:\s*\n\s*([^:]+)", docstring)
    if matches:
        return matches.group(1)
    return None


def check_function(function: FunctionDef, verbose: bool) -> list[str]:
    """
    Checks a function for mismatches between its arguments and the docstring.

    Args:
        function (FunctionDef): The function definition node.
        verbose (int): Whether to print verbose output.

    Returns:
        list[int]: A list of mismatches found in the function's docstring.
    """
    mismatches = []
    # Argument type check
    args_info = get_function_args_with_defaults(function)
    docstring = get_docstring(function)
    doc_args = extract_args_from_docstring(docstring)
    for name, info in args_info.items():
        type_hint = info["type"]
        default = info["default"]
        doc_type = doc_args.get(name)
        if name != "self":
            if type_hint and doc_type is None:
                    mismatches.append(f"[base_error_color]Argument [highlight_error_color]{name}[/highlight_error_color] not in docstring.[/base_error_color]")
            else:
                expected_doc_type = f"{type_hint}, optional" if default is not None else type_hint
                if not type_hint:
                    if doc_type:
                        mismatches.append(f"[base_error_color]Argument [highlight_error_color]{name}[/highlight_error_color] has no type, but docstring has [highlight_error_color]{doc_type}[/highlight_error_color].[/base_error_color]")
                    else:
                        if verbose:
                            mismatches.append(f"[base_error_color]Warning argument [highlight_error_color]{name}[/highlight_error_color] has no type.[/base_error_color]")
                if doc_type:
                    if type_hint and not (doc_type == type_hint or doc_type == expected_doc_type):
                        mismatches.append(f"[base_error_color]Argument TypeMismatch [highlight_error_color]{name}[/highlight_error_color]:\n{' ' * 8}function: [highlight_error_color]{type_hint}[/highlight_error_color]\n{' ' * 8}docstring: [highlight_error_color]{doc_type}[/highlight_error_color][/base_error_color]")
                    elif default is not None and "optional" not in doc_type:
                        mismatches.append(f"[base_error_color]Argument [highlight_error_color]{name}[/highlight_error_color] has a default value, but [highlight_error_color]optional[/highlight_error_color] is missing in the docstring.[/base_error_color]")
                    elif default is None and doc_type and "optional" in doc_type:
                        mismatches.append(f"[base_error_color]Argument [highlight_error_color]{name}[/highlight_error_color] has NO default value, but the docstring contains [highlight_error_color]optional[/highlight_error_color].[/base_error_color]")
                else:
                    mismatches.append(f"[base_error_color]Docstring not found.[/base_error_color]")
    # Return type check
    has_return = function_has_return_value(function)
    func_return = extract_return_from_function(function)
    doc_return = extract_return_from_docstring(docstring)
    if not func_return:
        mismatches.append(f"[base_error_color]Function has no return type.[/base_error_color]")
    elif has_return and func_return == "None":
        mismatches.append(f"[base_error_color]Function has a return value, but no return type is specified.[/base_error_color]")
    elif not has_return and func_return != "None":
        mismatches.append(f"[base_error_color]Function has no return value, but the return type is [highlight_error_color]{func_return}[/highlight_error_color].[/base_error_color]")
    elif func_return and doc_return and func_return != doc_return:
        # 
        print(str(func_return), doc_return)
        mismatches.append(f"[base_error_color]Return TypeMismatch:\n{' ' * 8}function:  [highlight_error_color]{func_return}[/highlight_error_color]\n{' ' * 8}docstring: [highlight_error_color]{doc_return}[/highlight_error_color][/base_error_color]")
    elif func_return and not doc_return and func_return != "None":
        mismatches.append(f"[base_error_color]Return-type [highlight_error_color]{func_return}[/highlight_error_color] not in docstring.[/base_error_color]")
    elif [arg.arg for arg in function.args.args if arg.arg != "self"] != extract_docstring_arg_order(docstring) and verbose:
        mismatches.append(f"[base_error_color]Function arguments order does not match docstring arguments order:\n{' ' * 8}function:  [highlight_error_color]{[arg.arg for arg in function.args.args if arg.arg != 'self']}[/highlight_error_color]\n{' ' * 8}docstring: [highlight_error_color]{extract_docstring_arg_order(docstring)}[/highlight_error_color][/base_error_color]")
    return mismatches


def main() -> None:
    parser = ArgumentParser(description = "Compares names and types in docstrings with function params.")
    parser.add_argument("paths", nargs="+", type=Path, help="Paths to directories or files to check docstrings.")
    parser.add_argument("-f", "--files", nargs="+", help="List of files to ignore, like: file1.py file2.py")
    parser.add_argument("-n", "--names", nargs="+", help="List of function names to ignore, like: func1 func2")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output.")
    args = parser.parse_args()
    if args.files is None:
        args.files = []
    if args.names is None:
        args.names = []
    total_files = 0
    total_functions = 0
    total_mismatches = 0
    theme = Theme({
        "base_color": "bold cyan",
        "highlight_color": "bold purple",
        "second_highlight_color": "bold blue",
        "base_error_color": "bold cyan",
        "highlight_error_color": "red",
    })
    console = Console(theme=theme)
    for directory in args.paths:
        directory = Path(directory).resolve()
        if isdir(directory):
            for root, _, files in walk(directory):
                if "venv" in root or "test" in root:
                    continue
                for file in files:
                    if file.endswith(".py") and not file in args.files:
                        mismatches_boxes = []
                        total_files += 1
                        file_path = join(root, file)
                        functions = get_functions_from_file(file_path)
                        for function in functions:
                            if not function.name in args.names:
                                total_functions += 1
                                mismatches = check_function(function, args.verbose)
                                if mismatches:
                                    mismatch_title = f"[base_color]Function [highlight_color]{function.name}[/highlight_color] [Line[second_highlight_color] {function.lineno}[/second_highlight_color]]:[/base_color]"
                                    mismatches_text = "\n\n".join(f"    [base_color]-[/base_color] {mismatch}" for mismatch in mismatches)
                                    total_mismatches += len(mismatches)
                                    mismatches_boxes.append(Panel(mismatches_text, title=mismatch_title, border_style="yellow", title_align="left"))
                        if mismatches_boxes:
                            # FIXME: Some padding is needed. Maybe some more styling
                            console.print(Panel(Group(*mismatches_boxes), title=f"[base_color]Checking file:[/base_color] [highlight_color]{file_path}[/highlight_color]"))
        else:
            console.print(f"[bold red]Invalid directory:[/bold red] [highlight_color]{directory}[/highlight_color]")
        console.print(f"[base_color]Stats for [highlight_color]{directory}[/highlight_color]:[/base_color]")
        console.print(f"    [base_color]Checked [second_highlight_color]{total_files}[/second_highlight_color] files with [second_highlight_color]{total_functions}[/second_highlight_color] functions.[/base_color]")
        console.print(f"    [base_color]Found [bold red]{total_mismatches}[/bold red] mismatches in docstrings.[/base_color]")


if __name__ == "__main__":
    main()