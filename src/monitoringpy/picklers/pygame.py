"""
Custom pickler for Pygame objects.

This module provides reduction functions for Pygame types that aren't
normally picklable, like Surface and Rect.
"""

# Check if pygame is installed
try:
    import pygame
except ImportError:
    raise ImportError("pygame is not installed. Please install it")


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
        pygame.Rect: reduce_rect,
        pygame.Color: reduce_color,
        pygame.event.EventType: reduce_pygame_event,
        pygame.time.Clock: reduce_pygame_clock,
        # Add more Pygame types here as needed
    }
