# TODO

## docstring_checker.py

### Test:
- 1 < Returns / No tuple in documented type

### FIX:
- If return: list[str] and docstring: list[int] prints mismatch as: list and list

- If (Type) is missing in docstring the argument is reported missing
    - Change to print missing type

- FIX IT ("Docstring not found" should cancel all comparisons with docstrings):
    - Docstring not found
    - Function arguments order does not match docstring arguments order:
        function:  ['main_window']
        docstring: [] 

### Add:

- Check for spaces by searching for ` \n`