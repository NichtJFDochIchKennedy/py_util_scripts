from argparse import ArgumentParser
from ast import FunctionDef, parse, unparse, get_docstring, walk as ast_walk
from os import walk
from os.path import isdir, join
from pathlib import Path
from re import search, match, DOTALL


def get_function_args_with_defaults(function):
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


def extract_args_from_docstring(docstring):
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


def get_functions_from_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    tree = parse(source)
    functions = []
    for node in ast_walk(tree):
        if isinstance(node, FunctionDef):
            functions.append(node)
    return functions


def extract_return_from_function(function):
    if function.returns:
        return unparse(function.returns)
    return None


def extract_return_from_docstring(docstring):
    if not docstring:
        return None
    matches = search(r"Returns:\s*\n\s*([^\s:]+)", docstring)
    if matches:
        return matches.group(1)
    return None


def check_function(function):
    mismatches = []
    # Argument type check
    args_info = get_function_args_with_defaults(function)
    docstring = get_docstring(function)
    doc_args = extract_args_from_docstring(docstring)
    for name, info in args_info.items():
        type_hint = info["type"]
        default = info["default"]
        doc_type = doc_args.get(name)
        if doc_type is None and name != "self":
            mismatches.append(f"Argument '{name}' not in docstring.")
        else:
            expected_doc_type = f"{type_hint}, optional" if default is not None else type_hint
            if type_hint and not (doc_type == type_hint or doc_type == expected_doc_type):
                mismatches.append(f"TypeMismatch '{name}': function '{type_hint}', docstring '{doc_type}'.")
            if default is not None and "optional" not in doc_type:
                mismatches.append(f"Argument '{name}' has a default value, but 'optional' is missing in the docstring.")
            if default is None and doc_type and "optional" in doc_type:
                mismatches.append(f"Argument '{name}' has NO default value, but the docstring contains 'optional'.")
    # Return type check
    func_return = extract_return_from_function(function)
    doc_return = extract_return_from_docstring(docstring)
    if func_return and doc_return and func_return != doc_return:
        mismatches.append(f"Return TypeMismatch: function '{func_return}', docstring '{doc_return}'.")
    elif func_return and not doc_return and func_return != "None":
        mismatches.append(f"Return-type '{func_return}' not in docstring.")
    elif doc_return and not func_return:
        mismatches.append(f"Docstring return-type '{doc_return}' but function has 'None'.")
    return mismatches


def main():
    parser = ArgumentParser(description = "Compares names and types in docstrings with function params.")
    parser.add_argument("paths", nargs="+", type=Path, help="Paths to directories or files to check docstrings.")
    parser.add_argument("-f", "--files", nargs="+", help="List of files to ignore, like: file1.py file2.py")
    parser.add_argument("-n", "--names", nargs="+", help="List of function names to ignore, like: func1 func2") 
    args = parser.parse_args()
    if args.files is None:
        args.files = []
    if args.names is None:
        args.names = []
    total_files = 0
    total_functions = 0
    total_mismatches = 0
    for directory in args.paths:
        directory = Path(directory).resolve()
        if isdir(directory):
            for root, _, files in walk(directory):
                if "venv" in root or "test" in root:
                    continue
                for file in files:
                    if file.endswith(".py") and not file in args.files:
                        total_files += 1
                        file_path = join(root, file)
                        functions = get_functions_from_file(file_path)
                        file_path_printed = False
                        for func in functions:
                            if not func.name in args.names:
                                total_functions += 1
                                mismatches = check_function(func)
                                if mismatches:
                                    if not file_path_printed:
                                        file_path_printed = True
                                        print(f"Checking file: {file_path}")
                                    print(f"    Function '{func.name}' error:")
                                    for m in mismatches:
                                        total_mismatches += 1
                                        print(f"        - {m}")
                                    print()
        else:
            print(f"Invalid directory: {directory}")
        print(f"Stats for {directory}:")
        print(f"    Checked {total_files} files with {total_functions} functions.")
        print(f"    Found {total_mismatches} mismatches in docstrings.")


if __name__ == "__main__":
    main()