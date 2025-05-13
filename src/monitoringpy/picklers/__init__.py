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

# Import available pickler modules
pickler_modules = []
for f in Path(__file__).parent.glob("*.py"):
    if f.name != "__init__.py" and f.is_file():
        module_name = f.stem
        try:
            # Ensure module can be imported from the correct path
            module_path = f"monitoringpy.picklers.{module_name}"
            if module_path not in sys.modules:
                module = importlib.import_module(f".{module_name}", package="monitoringpy.picklers")
                pickler_modules.append(module_name)
        except Exception as e:
            print(f"Failed to import pickler module {module_name}: {e}")

__all__ = pickler_modules 