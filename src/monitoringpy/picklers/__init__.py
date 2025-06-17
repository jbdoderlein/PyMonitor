"""
Custom picklers for handling serialization of objects from different modules.

This package contains modules with custom reduction functions for various library-specific types.
Each module should export a get_dispatch_table() function that returns a dictionary
mapping types to their reduction functions.

Example:
    # In pygame.py
    def get_dispatch_table():
        return {
            pygame.Surface: reduce_surface,
            pygame.Rect: reduce_rect,
            # Other pygame types...
        }
"""

# Make sure we can import modules from this package
from pathlib import Path
import importlib
import sys

# List available pickler modules without importing them automatically
pickler_modules = []
for f in Path(__file__).parent.glob("*.py"):
    if f.name != "__init__.py" and f.is_file():
        module_name = f.stem
        pickler_modules.append(module_name)

def get_pickler_module(name):
    """Lazy import a pickler module only when needed."""
    try:
        return importlib.import_module(f".{name}", package="monitoringpy.picklers")
    except Exception as e:
        print(f"Failed to import pickler module {name}: {e}")
        return None

__all__ = pickler_modules + ['get_pickler_module'] 