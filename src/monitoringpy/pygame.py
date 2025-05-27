"""
Pygame wrapper module for handling serialization issues and overriding functions.
This module imports the original pygame and makes it available as monitoringpy.pygame.

Usage:
    from monitoringpy import pygame
    # Use pygame as normal
"""

import sys
import importlib
import pygame as original_pygame
from typing import List, Any, Optional, Union, Tuple
from .core import PyMonitoring

# Copy all attributes from the original pygame module to this module
for attr_name in dir(original_pygame):
    if not attr_name.startswith('__'):
        globals()[attr_name] = getattr(original_pygame, attr_name)

# Define a version attribute to indicate this is the wrapped version
try:
    __version__ = getattr(original_pygame, '__version__', 'unknown') + '-monitoringpy'
except AttributeError:
    __version__ = 'unknown-monitoringpy'

# Flag to control screen reuse
_reuse_screen = False
# Store the current screen instance
_current_screen = None
# Bypass the original display.update method
_bypass_display_update = False


# Override functions as needed

# Store the original set_mode function
_original_set_mode = original_pygame.display.set_mode

# Modified set_mode function that can reuse the existing screen
def modified_set_mode(size=(0, 0), flags=0, depth=0, display=0, vsync=0):
    """Modified set_mode that can reuse the existing screen when _reuse_screen is True
    
    Args:
        size: Size of the window (width, height)
        flags: Additional flags for the display
        depth: Color depth of the display
        display: Which display to use on multi-monitor setups
        vsync: Whether to enable vertical sync
        
    Returns:
        Surface object representing the screen
    """
    global _current_screen, _reuse_screen
    # If reuse flag is set and we have a valid screen, return it
    if _reuse_screen and _current_screen is not None:
        return _current_screen
    
    # Otherwise create a new screen and store it
    _current_screen = _original_set_mode(size, flags, depth, display, vsync)
    return _current_screen

# Replace display.set_mode with our modified version
globals()['display'].set_mode = modified_set_mode

# Function to control screen reuse
def set_screen_reuse(reuse=True):
    """Set whether to reuse the existing screen when set_mode is called
    
    Args:
        reuse: If True, subsequent calls to set_mode will return the existing screen
              If False, set_mode will create a new screen as usual
    """
    global _reuse_screen
    _reuse_screen = reuse

# Export the control function
globals()['set_screen_reuse'] = set_screen_reuse


def bypass_display_update(bypass=True):
    """Bypass the original display.update method
    
    Args:
        bypass: If True, the original display.update method will be bypassed
    """
    global _bypass_display_update
    _bypass_display_update = bypass

# Export the control function
globals()['bypass_display_update'] = bypass_display_update

_original_display_update = original_pygame.display.update

def modified_display_update(*args, **kwargs):
    """Modified display.update method to include event data
    """
    global _bypass_display_update
    if not _bypass_display_update:
        # Call the original display.update method
        return _original_display_update(*args, **kwargs)
    else:
        return None

globals()['display'].update = modified_display_update


# Clean up namespace but keep references we need
del sys, importlib 