"""
Custom pickler for Python's turtle module objects.

This module provides reduction functions for turtle types that aren't 
normally picklable, like Turtle and Screen.
"""

import turtle
import io
import sys

# Make sure this module is properly importable
__name__ = "monitoringpy.picklers.turtle"

def reduce_turtle(t):
    """Serialize a turtle by capturing its essential state"""
    state = {
        'position': t.position(),
        'heading': t.heading(),
        'pencolor': t.pencolor(),
        'fillcolor': t.fillcolor(),
        'pensize': t.pensize(),
        'speed': t.speed(),
        'isdown': t.isdown(),
        'isvisible': t.isvisible(),
        'shape': t.shape(),
        'resizemode': t._resizemode,
        'stretchfactor': t._stretchfactor,
        'shearfactor': t._shearfactor,
        'tilt': t._tilt,
        'outlinewidth': t._outlinewidth,
        'currentLine': t.currentLine if hasattr(t, 'currentLine') else []
    }
    # Use fully qualified name for the reconstruct function
    return (sys.modules[__name__].reconstruct_turtle, (state,))

def reconstruct_turtle(state):
    """Create a new turtle with the given state"""
    new_turtle = turtle.Turtle()
    
    # Set basic turtle properties
    new_turtle.penup()
    new_turtle.setposition(state['position'])
    new_turtle.setheading(state['heading'])
    new_turtle.pencolor(state['pencolor'])
    new_turtle.fillcolor(state['fillcolor'])
    new_turtle.pensize(state['pensize'])
    new_turtle.speed(state['speed'])
    
    # Set pen state (up/down)
    if state['isdown']:
        new_turtle.pendown()
    else:
        new_turtle.penup()
    
    # Set visibility
    if state['isvisible']:
        new_turtle.showturtle()
    else:
        new_turtle.hideturtle()
        
    # Set shape
    new_turtle.shape(state['shape'])
    
    # Set more advanced properties - Using setattr to avoid linter errors
    if hasattr(new_turtle, '_resizemode'):
        setattr(new_turtle, '_resizemode', state['resizemode'])
    if hasattr(new_turtle, '_stretchfactor'):
        setattr(new_turtle, '_stretchfactor', state['stretchfactor'])
    if hasattr(new_turtle, '_shearfactor'):
        setattr(new_turtle, '_shearfactor', state['shearfactor'])
    if hasattr(new_turtle, '_tilt'):
        setattr(new_turtle, '_tilt', state['tilt'])
    if hasattr(new_turtle, '_outlinewidth'):
        setattr(new_turtle, '_outlinewidth', state['outlinewidth'])
    
    # Ensure the turtle is ready to draw
    if state['isdown']:
        # Use setattr to call protected method
        if hasattr(new_turtle, '_update'):
            update_method = getattr(new_turtle, '_update')
            update_method()
    
    return new_turtle


def reduce_screen(screen):
    """Serialize a turtle screen by capturing its essential state"""
    state = {
        'canvwidth': screen.canvwidth,
        'canvheight': screen.canvheight,
        'xscale': screen._xscale if hasattr(screen, '_xscale') else 1.0,
        'yscale': screen._yscale if hasattr(screen, '_yscale') else 1.0,
        'mode': screen._mode,
        'delay': screen.delay(),
        'colormode': screen._colormode,
        'bgcolor': screen.bgcolor(),
        'bgpic_name': screen._bgpicname if hasattr(screen, '_bgpicname') else 'nopic',
        'tracing': screen._tracing
    }
    return (reconstruct_screen, (state,))

def reconstruct_screen(state):
    """Create a new screen with the given state"""
    screen = turtle.Screen()
    
    # Set basic screen properties
    screen.setup(width=state['canvwidth'], height=state['canvheight'])
    screen.mode(state['mode'])
    screen.delay(state['delay'])
    screen.colormode(state['colormode'])
    screen.bgcolor(state['bgcolor'])
    
    # Set more advanced properties if needed
    if state['bgpic_name'] != 'nopic':
        screen.bgpic(state['bgpic_name'])
    
    if state['tracing'] == 0:
        screen.tracer(0)
    else:
        screen.tracer(state['tracing'])
    
    return screen


def get_dispatch_table():
    """
    Return a dictionary mapping turtle types to their reduction functions.
    
    Returns:
        A dictionary where keys are turtle types and values are reduction functions
    """
    return {
        turtle.Turtle: reduce_turtle,
        turtle._Screen: reduce_screen,
        # Add more turtle types here as needed
    } 