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



# Store the original get event function
# We use a module-level variable since modifying original_pygame directly might not work with all imports
_original_get_event = original_pygame.event.get

# Modified event.get function with monitoring - preserving original signature
def modified_get_event(eventtype=None, pump=True, exclude=None):
    """Modified get_event method to include event data
    
    Args:
        eventtype: Type of events to get (optional)
        pump: Whether to call pygame.event.pump() first (default: True)
        exclude: Type of events to exclude (optional)
    
    Returns:
        List of pygame events
    """
    # Call original get function with all original parameters
    events = _original_get_event(eventtype, pump, exclude)
    monitor_instance = PyMonitoring.get_instance()
    if monitor_instance and len(events) > 0:  # Check if monitor exists and events were retrieved
        # Handle event buffering in a way that's compatible with the PyMonitoring class
        # Store events in a way that respects the class design
        if not hasattr(monitor_instance, '_pygame_event_buffer'):
            # Initialize the buffer if it doesn't exist
            monitor_instance._pygame_event_buffer = [] # type: ignore
        try:
            # Save events in monitor - using a safe approach with getattr/setattr
            monitor_instance._pygame_event_buffer.extend(events) # type: ignore
            
        except Exception as e:
            print(f"Error buffering pygame event: {e}")
    # Return the original list of events for game logic
    return events

# Replace the event.get function with our modified version
globals()['event'].get = modified_get_event

# Handle non-serializable objects
# Example:
# class SerializableSurface(original_pygame.Surface):
#     def __reduce__(self):
#         # Custom serialization logic
#         return (self.__class__, (self.get_size(),))
# 
# globals()['Surface'] = SerializableSurface


# add utility functions

def capture_buffered_pygame_events(monitor : PyMonitoring, code, offset, return_value):
    """
    PyMonitoring start_hook to capture and clear buffered pygame events
    and prepare them for storage in call_metadata.
    """
    if monitor and hasattr(monitor, '_pygame_event_buffer') and len(monitor._pygame_event_buffer)>0: # type: ignore
        # Retrieve and clear the buffer in one step
        collected_events_raw = monitor._pygame_event_buffer # type: ignore
        monitor._pygame_event_buffer = [] # type: ignore
        events = {"events":list(map(lambda event: event.dict | {"type": event.type}, collected_events_raw))}
        return monitor.call_tracker._store_variables(events) # type: ignore
    else:
        return {}

# Clean up namespace but keep references we need
del sys, importlib 