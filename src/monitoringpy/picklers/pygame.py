"""
Custom pickler for Pygame objects.

This module provides reduction functions for Pygame types that aren't 
normally picklable, like Surface and Rect.
"""

# Check if pygame is installed
try:
    import pygame
except ImportError:
    raise ImportError("pygame is not installed. Please install it using 'pip install pygame'.")

import sys

# Make sure this module is properly importable
__name__ = "monitoringpy.picklers.pygame"

def reduce_surface(surface):
    """
    Reduction function for pygame.Surface objects.
    Converts a surface to a string representation using pygame.image.tostring().
    
    Args:
        surface: The pygame.Surface object to pickle
        
    Returns:
        A tuple that can be used to reconstruct the surface
    """
    # Save the surface data and attributes
    size = surface.get_size()
    format = surface.get_bitsize()
    data = pygame.image.tostring(surface, 'RGBA')
    
    # Return constructor and arguments with fully qualified function name
    return (sys.modules[__name__].reconstruct_surface, (size, format, data))

def reconstruct_surface(size, format, data):
    """
    Reconstruct a pygame.Surface from saved data.
    
    Args:
        size: Size tuple (width, height)
        format: Bit size
        data: String representation of the surface
        
    Returns:
        A pygame.Surface object
    """
    try:
        # Create a new surface from the saved data
        surface = pygame.image.fromstring(data, size, 'RGBA')
        return surface
    except Exception as e:
        # If reconstruction fails, return a blank surface of the same size
        print(f"Error reconstructing surface: {e}")
        return pygame.Surface(size)

def reduce_rect(rect):
    """
    Reduction function for pygame.Rect objects.
    
    Args:
        rect: The pygame.Rect object to pickle
        
    Returns:
        A tuple that can be used to reconstruct the rect
    """
    # Return constructor and arguments
    return (pygame.Rect, (rect.x, rect.y, rect.width, rect.height))

def reduce_color(color):
    """
    Reduction function for pygame.Color objects.
    
    Args:
        color: The pygame.Color object to pickle
        
    Returns:
        A tuple that can be used to reconstruct the color
    """
    # Return constructor and arguments
    return (pygame.Color, (color.r, color.g, color.b, color.a))

def reduce_pygame_event(e):
    """
    Reduction function for pygame.event.EventType objects.
    
    Args:
        e: The pygame event to pickle
        
    Returns:
        A tuple that can be used to reconstruct the event
    """
    return (pygame.event.Event, (e.type, e.dict.copy()))

def reduce_pygame_clock(c):
    """
    Reduction function for pygame.time.Clock objects.
    
    Args:
        c: The pygame clock to pickle
        
    Returns:
        A tuple that can be used to reconstruct the clock
    """
    return (pygame.time.Clock, ())

def get_dispatch_table():
    """
    Return a dictionary mapping Pygame types to their reduction functions.
    
    Returns:
        A dictionary where keys are Pygame types and values are reduction functions
    """
    return {
        pygame.Surface: reduce_surface,
        pygame.Rect: reduce_rect,
        pygame.Color: reduce_color,
        pygame.event.EventType: reduce_pygame_event,
        pygame.time.Clock: reduce_pygame_clock,
        # Add more Pygame types here as needed
    } 