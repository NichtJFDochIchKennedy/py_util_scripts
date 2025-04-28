# TODO

## docstring_checker.py

### Add:

- Check if the function realy returns something
    - If not and a return type is specified -> Error
    - If no return type is specified but somethin is returned -> Error
- Make output more readable

### Test:

- Different pattern mismatches (like no "-> None" or something like that)
- Do I check the order of the params in func and doc

## row_counter.py

### Add:

- Different counters for documentation and code
    - To compare doc to code ratio
- .gitignore option for row_counter.py