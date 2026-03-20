"""Configuration constants for docstring checker."""

from rich.theme import Theme

SKIP_DIRS = {"venv"}
SELF_PARAMS = {"self", "cls"}
GENERATOR_TYPES = {"Iterator", "Generator", "Iterable"}

CONSOLE_THEME = Theme(
    {
        "base_color": "bold cyan",
        "highlight_color": "bold purple",
        "second_highlight_color": "bold blue",
        "base_error_color": "bold cyan",
        "highlight_error_color": "red",
    }
)
