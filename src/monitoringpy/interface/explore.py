#!/usr/bin/env python3
"""
PyMonitor Database Explorer

A Tkinter-based GUI tool to explore and replay function executions 
stored in a PyMonitor database.
"""

import tkinter as tk
import tkinter.ttk as ttk
from typing import List, Optional, Any, Dict, Callable
from sqlalchemy.orm import Session as SQLASession
import typing
import logging
import argparse
import os
import sys

# Adjust imports for package structure
from ..core import (
    init_db, 
    init_monitoring, 
    start_session as start_live_session, 
    replay_session_from,
    reanimate_function,
    FunctionCall, 
    MonitoringSession,
    ObjectManager,
    FunctionCallTracker
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global variables --- 
# These will be initialized in the main function after parsing args
DB_PATH: Optional[str] = None
TARGET_FUNCTION_NAME: Optional[str] = None
live_monitor = None
read_session: Optional[SQLASession] = None
object_manager: Optional[ObjectManager] = None
call_tracker: Optional[FunctionCallTracker] = None
current_session_info: Optional[MonitoringSession] = None
initial_entry_point_id: Optional[int] = None
active_branch_root_id: Optional[int] = None 
branch_widgets: Dict[int, Dict[str, Any]] = {}
is_playing = False
play_timer_id = None
# Restore global initialization with type hints
checkbox_vars: List[tk.BooleanVar] = [] 
checkbox_labels: List[str] = []
checkbox_widgets: List[tk.Checkbutton] = [] 
root: Optional[tk.Tk] = None
sliders_frame: Optional[ttk.Frame] = None
checkbox_frame: Optional[tk.Frame] = None
play_pause_button: Optional[tk.Button] = None
status_label: Optional[tk.Label] = None
status_bar: Optional[ttk.Label] = None

# Add new global variables for the toggles
pygame_reuse_events_var = None  # Will be set if pygame flag is True
run_in_background_var = None  # Will be set to tk.BooleanVar
pygame_imitation_var = None  # Will be set by args

# --- Data Retrieval Functions (Adapted from example) ---
def get_branch_roots(session: SQLASession) -> List[int]:
    if session is None: return []
    roots = []
    main_session = session.query(MonitoringSession).first()
    if main_session and main_session.entry_point_call_id:
        roots.append(main_session.entry_point_call_id)
    branch_starts = session.query(FunctionCall).\
        filter(FunctionCall.parent_call_id != None).\
        order_by(FunctionCall.start_time).all()
    for call in branch_starts:
        if call.id is not None and call.id not in roots:
             roots.append(call.id)
    if main_session and main_session.entry_point_call_id is not None and main_session.entry_point_call_id not in roots:
         roots.append(main_session.entry_point_call_id)
    int_roots = [r for r in roots if isinstance(r, int)]
    return sorted(list(set(int_roots)))

def get_branch_sequence(session: SQLASession, root_call_id: int) -> List[int]:
    """
    Get a sequence of function call IDs that form a single branch.
    This ensures that each branch sequence only contains calls belonging strictly to that branch,
    stopping at points where child branches start.
    
    Args:
        session: The database session
        root_call_id: The ID of the root function call of the branch
        
    Returns:
        A list of function call IDs in sequence order
    """
    if session is None: return []
    sequence = []
    current_call_id: Optional[int] = root_call_id
    
    # First, identify all direct children of this branch to exclude them
    children_branches = set()
    all_direct_children = session.query(FunctionCall).filter(FunctionCall.parent_call_id == root_call_id).all()
    for child in all_direct_children:
        if child.id is not None:
            children_branches.add(child.id)
    
    # Now just follow the next_call_id chain but stop at child branch starts or cycles
    visited = set()  # Avoid cycles
    
    while current_call_id is not None and current_call_id not in visited:
        visited.add(current_call_id)
        call = session.get(FunctionCall, current_call_id)
        if call:
            sequence.append(call.id)
            # Get the next call in the sequence
            next_id = getattr(call, 'next_call_id', None)
            
            # Stop if we reach a NULL next_id
            if next_id is None:
                break
                
            # Stop if the next call is the start of a child branch
            if next_id in children_branches:
                logger.info(f"Branch sequence for {root_call_id} stops at {next_id} (direct child)")
                break
            
            # Check if next_id is any replay start (has a parent_call_id)
            next_call = session.get(FunctionCall, next_id)
            if next_call and next_call.parent_call_id is not None:
                # If it's a replay start, stop the sequence
                logger.info(f"Branch sequence for {root_call_id} stops at {next_id} (replay branch start)")
                break
            
            current_call_id = int(next_id)
        else:
            break
    
    logger.info(f"Sequence for root {root_call_id}: {sequence}")
    return sequence

def get_branch_depth(session: SQLASession, call_id: int, max_depth=10) -> int:
    """Calculates the depth of a call by traversing parent links."""
    if session is None: return 0
    depth = 0
    current_id: Optional[int] = call_id
    visited = set()
    while depth < max_depth:
        if current_id is None or current_id in visited:
            break # Reached root or cycle detected
        visited.add(current_id)
        call = session.get(FunctionCall, current_id)
        if call and call.parent_call_id is not None:
            current_id = typing.cast(typing.Optional[int], call.parent_call_id)
            depth += 1
        else:
            break # Reached the main branch root
    if depth >= max_depth:
        logger.warning(f"Max depth reached for call {call_id}, returning {max_depth}")
    return depth

# --- UI Callback Functions (Adapted from example) ---
def get_unchecked_globals() -> List[str]:
    """Returns a list of global variables that are currently unchecked."""
    unchecked = []
    for i, var in enumerate(checkbox_vars):
        if not var.get():  # If checkbox is unchecked
            unchecked.append(checkbox_labels[i])
    return unchecked

def update_active_branch_slider(selected_call_id_str: str, branch_root_id: int):
    """Callback when any branch slider changes."""
    global DB_PATH, status_label, status_bar
    set_active_branch(branch_root_id) # Mark this branch as active
    unchecked_globals = get_unchecked_globals()
    
    # Update status bar
    if status_bar:
        status_bar.config(text=f"Viewing call {selected_call_id_str} in branch {branch_root_id}")
    
    # Update position indicator for this branch
    if branch_root_id in branch_widgets and 'position_var' in branch_widgets[branch_root_id]:
        try:
            selected_call_id = int(selected_call_id_str)
            sequence = branch_widgets[branch_root_id]['sequence']
            current_index = sequence.index(selected_call_id)
            branch_widgets[branch_root_id]['position_var'].set(
                f"Position: {current_index + 1}/{len(sequence)}"
            )
        except (ValueError, IndexError):
            branch_widgets[branch_root_id]['position_var'].set(
                f"Position: ?/{len(branch_widgets[branch_root_id]['sequence'])}"
            )
    
    # Update status display
    if read_session is not None and status_label is not None:
        try:
            # Convert to integer and get call info
            selected_call_id = int(selected_call_id_str)
            call = read_session.get(FunctionCall, selected_call_id)
            
            if call:
                # Get branch sequence for position info
                sequence = branch_widgets[branch_root_id]['sequence']
                try:
                    current_index = sequence.index(selected_call_id)
                    position_info = f"Step {current_index + 1}/{len(sequence)}"
                except ValueError:
                    position_info = "Unknown position"
                
                # Format status text
                status_text = f"Current: Branch {branch_root_id} ({position_info})\n"
                status_text += f"Call ID: {selected_call_id} - Function: {call.function}"
                
                # Safely handle file path (might be a SQLAlchemy Column)
                file_path = None
                if hasattr(call, 'file') and call.file is not None:
                    # Convert SQLAlchemy Column to string if necessary
                    file_path = str(call.file)
                if file_path:
                    status_text += f" - File: {os.path.basename(file_path)}"
                
                # Safely handle line number
                line_num = None
                if hasattr(call, 'line') and call.line is not None:
                    # First convert to string to avoid type issues with Column objects
                    line_num = int(str(call.line)) if call.line else None
                if line_num:
                    status_text += f" - Line: {line_num}"
                
                # Add call timing information if available
                start_time = getattr(call, 'start_time', None)
                end_time = getattr(call, 'end_time', None)
                if start_time and end_time:
                    duration = end_time - start_time
                    duration_ms = duration.total_seconds() * 1000
                    status_text += f"\nDuration: {duration_ms:.2f} ms"
                
                status_label.config(text=status_text)
            else:
                status_label.config(text=f"Call ID {selected_call_id_str} not found")
        except (ValueError, TypeError) as e:
            status_label.config(text=f"Error displaying call info: {e}")
    
    # Ensure monitor recording is off for simple reanimation
    if DB_PATH:
        if status_bar:
            status_bar.config(text=f"Reanimating function call {selected_call_id_str}...")
        
        reanimate_function(
            selected_call_id_str, DB_PATH, ignore_globals=unchecked_globals
        )
        
        if status_bar:
            status_bar.config(text=f"Reanimation complete for call {selected_call_id_str}")
    else:
        logger.error("DB_PATH not set, cannot reanimate.")


def set_active_branch(branch_root_id: int):
    """Sets the currently active branch for controls."""
    global active_branch_root_id
    
    # Define colors
    ACTIVE_COLOR = "#e0e8f0"  # Highlight color for active branch
    DEPTH_COLORS = [
        "#f0f8ff",  # aliceblue - depth 0 (main branch)
        "#e6f2ff",  # lighter blue - depth 1
        "#d9ecff",  # light blue - depth 2
        "#ccf2ff",  # very light cyan - depth 3
        "#e6fff2",  # very light mint - depth 4
        "#f2ffe6",  # very light yellowgreen - depth 5
    ]
    
    # Only take action if changed
    if active_branch_root_id != branch_root_id and branch_root_id in branch_widgets:
        logger.info(f"Setting active branch to: {branch_root_id}")
        
        # Reset previous active branch appearance if it exists
        if active_branch_root_id in branch_widgets:
            prev_branch = branch_widgets[active_branch_root_id]
            # Restore original color based on depth
            if read_session:
                depth = get_branch_depth(read_session, active_branch_root_id)
                bg_color = DEPTH_COLORS[min(depth, len(DEPTH_COLORS)-1)]
                
                # Reset all widgets for this branch
                for key, widget in prev_branch.items():
                    if key not in ['sequence', 'position_var'] and hasattr(widget, 'configure'):
                        widget.configure(background=bg_color)
        
        # Set new active branch and highlight it
        active_branch_root_id = branch_root_id
        curr_branch = branch_widgets[branch_root_id]
        
        # Highlight all widgets for this branch
        for key, widget in curr_branch.items():
            if key not in ['sequence', 'position_var'] and hasattr(widget, 'configure'):
                widget.configure(background=ACTIVE_COLOR)
        
        # Refresh the call info immediately
        try:
            slider = curr_branch['slider']
            current_value = slider.get()
            update_active_branch_slider(str(int(current_value)), branch_root_id)
        except (ValueError, KeyError) as e:
            logger.error(f"Error updating active branch: {e}")

def set_slider_value(slider: tk.Scale, value: int):
    """Safely sets the slider value within bounds and triggers update."""
    min_val = slider.cget("from")
    max_val = slider.cget("to")
    new_value = max(min_val, min(max_val, value))
    slider.set(new_value)
    # update_slider(str(new_value)) # Command triggers this automatically

def prev_step():
    """Move active slider one step back."""
    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
        return
    slider = branch_widgets[active_branch_root_id]['slider']
    current_value = slider.get()
    sequence = branch_widgets[active_branch_root_id]['sequence']
    try:
        current_index = sequence.index(int(current_value))
        if current_index > 0:
            set_slider_value(slider, sequence[current_index - 1]) 
    except (ValueError, IndexError):
        pass 

def next_step():
    """Move active slider one step forward."""
    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
        return
    slider = branch_widgets[active_branch_root_id]['slider']
    current_value = slider.get()
    sequence = branch_widgets[active_branch_root_id]['sequence']
    try:
        current_index = sequence.index(int(current_value))
        if current_index < len(sequence) - 1:
            set_slider_value(slider, sequence[current_index + 1])
    except (ValueError, IndexError):
        pass 

def play_step():
    """Increment slider if playing, and schedule next step."""
    global play_timer_id, is_playing, root
    if root is None or play_pause_button is None: return

    if is_playing:
        if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
             toggle_play_pause() # Stop if no active branch
             return
        
        next_step() # Use existing next_step logic
        
        slider = branch_widgets[active_branch_root_id]['slider']
        sequence = branch_widgets[active_branch_root_id]['sequence']
        current_value = slider.get()
        try:
             current_index = sequence.index(int(current_value))
             if current_index < len(sequence) - 1:
                  play_timer_id = root.after(100, play_step) # Schedule next frame
             else:
                  toggle_play_pause() # Auto-pause at the end
        except ValueError:
             toggle_play_pause() # Stop if current value not in sequence

def toggle_play_pause():
    """Toggle between playing and pausing the slider animation."""
    global is_playing, play_timer_id, root, play_pause_button, status_bar
    if root is None or play_pause_button is None: return

    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
        logger.warning("Cannot play/pause: No active branch.")
        if status_bar:
            status_bar.config(text="Cannot play/pause: No active branch selected")
        return # Don't toggle if no active branch
        
    slider = branch_widgets[active_branch_root_id]['slider']
    sequence = branch_widgets[active_branch_root_id]['sequence']
    
    if is_playing:
        if play_timer_id:
            root.after_cancel(play_timer_id)
            play_timer_id = None
        is_playing = False
        play_pause_button.config(text="▶ Play")
        if status_bar:
            status_bar.config(text="Playback paused")
    else:
        is_playing = True
        play_pause_button.config(text="⏸ Pause")
        # Reset to start if at the end
        if sequence and slider.get() >= max(sequence): # Check if sequence is not empty
            set_slider_value(slider, min(sequence))
        if status_bar:
            status_bar.config(text="Playing sequence...")
        play_step() 

def reload_current():
    """Force reload the current function selected by the active slider."""
    global DB_PATH
    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
        return
    if DB_PATH is None:
        logger.error("DB_PATH not set, cannot reload.")
        return

    slider = branch_widgets[active_branch_root_id]['slider']
    current_value = slider.get()
    unchecked_globals = get_unchecked_globals()
    reanimate_function(
        str(int(current_value)), DB_PATH, ignore_globals=unchecked_globals
    )

def refresh_branch_ui():
    """Dynamically create/update sliders for each execution branch."""
    global active_branch_root_id, initial_entry_point_id, read_session, sliders_frame, status_bar
    if read_session is None or sliders_frame is None: 
        logger.error("Session or sliders_frame not initialized for refresh_branch_ui")
        return 
    
    # Update status bar
    if status_bar:
        status_bar.config(text="Refreshing branches...")
    
    # Refresh the session to get latest data
    try:
        logger.info("Refreshing database session before UI update...")
        read_session.expire_all()  # Expire all objects so they'll be reloaded from DB
        read_session.commit()  # Commit any pending changes
    except Exception as e:
        logger.error(f"Error refreshing database session: {e}")
        if status_bar:
            status_bar.config(text=f"Error refreshing data: {str(e)}")
        return
        
    logger.info("Refreshing Branch UI...") 
    branch_roots = get_branch_roots(read_session)
    found_active_root = False

    # Define indentation amount per depth level
    INDENT_STEP = 20 # pixels
    
    # Define branch colors based on depth
    DEPTH_COLORS = [
        "#f0f8ff",  # aliceblue - depth 0 (main branch)
        "#e6f2ff",  # lighter blue - depth 1
        "#d9ecff",  # light blue - depth 2
        "#ccf2ff",  # very light cyan - depth 3
        "#e6fff2",  # very light mint - depth 4
        "#f2ffe6",  # very light yellowgreen - depth 5
    ]
    ACTIVE_COLOR = "#e0e8f0"  # Highlight color for active branch

    # --- Clear existing slider widgets before redrawing ---
    # Create a copy of keys to iterate over, as we might modify the dict
    existing_roots_to_clear = list(branch_widgets.keys()) 
    for r_id in existing_roots_to_clear:
        if r_id in branch_widgets and 'frame' in branch_widgets[r_id]:
            branch_widgets[r_id]['frame'].destroy()
        if r_id in branch_widgets:
            del branch_widgets[r_id] # Remove entry after destroying frame
    # --- End Clear ---

    # Create a mapping of branches to their function names for better labels
    function_names = {}
    for root_id in branch_roots:
        call = read_session.get(FunctionCall, root_id)
        if call:
            function_names[root_id] = call.function

    # Create a lookup of child branches by parent call ID
    child_branches = {}
    for root_id in branch_roots:
        call = read_session.get(FunctionCall, root_id)
        if call and call.parent_call_id:
            if call.parent_call_id not in child_branches:
                child_branches[call.parent_call_id] = []
            child_branches[call.parent_call_id].append(root_id)
    
    # Draw connection lines between parent and child branches
    def draw_branch_connector(parent_id, child_id, parent_frame, indent):
        """Draw a visual connector line between parent and child branches"""
        if not (parent_frame and sliders_frame):
            return
            
        # Create a connector frame
        connector_height = 10  # pixels
        connector_frame = tk.Frame(sliders_frame, height=connector_height, bd=0)
        connector_frame.pack(fill=tk.X, pady=0, padx=(indent-10, 0))
        
        # Create canvas for drawing the connector
        connector_canvas = tk.Canvas(connector_frame, height=connector_height, 
                                   bd=0, highlightthickness=0, bg="#f5f5f5")
        connector_canvas.pack(fill=tk.X, expand=True)
        
        # Draw a line connecting parent to child
        connector_canvas.create_line(
            5, 0,                     # Start at left edge, top
            5, connector_height,      # Draw down
            indent+5, connector_height,   # Draw right to child indent
            width=1, fill="#666666"
        )

    # Sort branch_roots by depth to draw parent branches before children
    sorted_branch_roots = sorted(branch_roots, key=lambda r_id: get_branch_depth(read_session, r_id))
    
    for root_id in sorted_branch_roots:
        # Create UI for branch root: {root_id}
        branch_sequence = get_branch_sequence(read_session, root_id)
        if not branch_sequence:
            logger.warning(f"Skipping branch {root_id}: No sequence found.")
            continue
        
        # Calculate depth for indentation and coloring
        depth = get_branch_depth(read_session, root_id)
        indent_amount = depth * INDENT_STEP
        bg_color = DEPTH_COLORS[min(depth, len(DEPTH_COLORS)-1)]  # Get color based on depth
        
        # If this is a child branch, draw connector from parent
        parent_call = read_session.get(FunctionCall, root_id)
        if parent_call and parent_call.parent_call_id and parent_call.parent_call_id in branch_widgets:
            parent_frame = branch_widgets[parent_call.parent_call_id]['frame']
            draw_branch_connector(parent_call.parent_call_id, root_id, parent_frame, indent_amount)
        
        # Create frame with potential left padding for indentation
        branch_frame = tk.Frame(sliders_frame, bd=1, relief=tk.GROOVE, bg=bg_color)
        branch_frame.pack(fill=tk.X, pady=2, padx=(indent_amount, 0))
        
        # Create a more informative label with branch type indicator
        prefix = ""
        parent_info = ""
        if parent_call and parent_call.parent_call_id:
            # This is a replay branch - add visual indicator
            prefix = "🔄 "  # Replay symbol
            parent_func_name = ""
            if parent_call.parent_call_id in function_names:
                parent_func_name = f" ({function_names[parent_call.parent_call_id]})"
            
            label_text = f"{prefix}Replay Branch {root_id}: {parent_call.function} [{len(branch_sequence)} steps]"
            parent_info = f"From Branch {parent_call.parent_call_id}{parent_func_name} @ Call {parent_call.parent_call_id}"
        elif initial_entry_point_id is not None and root_id == initial_entry_point_id:
            prefix = "▶ "  # Main branch symbol
            label_text = f"{prefix}Main Branch: {parent_call.function if parent_call else 'Unknown'} [{len(branch_sequence)} steps]"
        else:
            prefix = "◆ "  # Regular branch symbol
            label_text = f"{prefix}Branch {root_id}: {parent_call.function if parent_call else 'Unknown'} [{len(branch_sequence)} steps]"
            
        # If this branch has child branches, indicate it
        has_children = False
        if root_id in child_branches and child_branches[root_id]:
            has_children = True
            child_count = len(child_branches[root_id])
            label_text += f" (Has {child_count} replay{'s' if child_count > 1 else ''})"

        # Use a Frame for the label area for more control
        label_frame = tk.Frame(branch_frame, bg=bg_color)
        label_frame.pack(side=tk.LEFT, padx=5, fill=tk.Y)
        
        # Main branch label
        branch_label = tk.Label(label_frame, text=label_text, justify=tk.LEFT, bg=bg_color, 
                               font=("Arial", 10, "bold" if has_children else "normal"))
        branch_label.pack(side=tk.TOP, anchor=tk.W)
        
        # Add parent info if applicable
        if parent_info:
            parent_label = tk.Label(label_frame, text=parent_info, justify=tk.LEFT, 
                                  bg=bg_color, font=("Arial", 9, "italic"))
            parent_label.pack(side=tk.TOP, anchor=tk.W)

        slider_min = min(branch_sequence)
        slider_max = max(branch_sequence)
        
        slider_command = lambda val, rid=root_id: update_active_branch_slider(val, rid)
        
        # Add a frame for slider area
        slider_frame = tk.Frame(branch_frame, bg=bg_color)
        slider_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Add current position indicator above slider
        position_var = tk.StringVar(value="Position: 0/0")
        position_label = tk.Label(slider_frame, textvariable=position_var, 
                                 bg=bg_color, font=("Arial", 8))
        position_label.pack(side=tk.TOP, anchor=tk.W)
        
        branch_slider = tk.Scale(
            slider_frame,
            from_=slider_min,
            to=slider_max,
            orient=tk.HORIZONTAL,
            command=slider_command,
            length=250,
            bg=bg_color,
            troughcolor="#e0e0e0"  # Light gray trough
        )
        branch_slider.pack(side=tk.TOP, fill=tk.X, expand=True)
        
        # Set initial slider value to the first item in the sequence
        branch_slider.set(slider_min) 

        # Configure click events
        branch_slider.bind("<Button-1>", lambda event, rid=root_id: set_active_branch(rid))
        branch_label.bind("<Button-1>", lambda event, rid=root_id: set_active_branch(rid))
        label_frame.bind("<Button-1>", lambda event, rid=root_id: set_active_branch(rid))

        # Create dictionary to track widget references for this branch
        branch_data = {
            'frame': branch_frame,
            'slider': branch_slider,
            'label': branch_label,
            'sequence': branch_sequence,
            'position_var': position_var,
            'label_frame': label_frame,
            'slider_frame': slider_frame
        }
        
        # Add parent label if it exists
        if parent_info:
            branch_data['parent_label'] = parent_label
            
        branch_widgets[root_id] = branch_data
        
        # Update position indicator
        try:
            current_value = branch_slider.get()
            current_index = branch_sequence.index(int(current_value))
            position_var.set(f"Position: {current_index + 1}/{len(branch_sequence)}")
        except (ValueError, IndexError):
            position_var.set(f"Position: ?/{len(branch_sequence)}")
        
        # Mark active branch
        if root_id == active_branch_root_id:
            found_active_root = True
            # Highlight the active branch
            branch_frame.configure(background=ACTIVE_COLOR)
            branch_label.configure(background=ACTIVE_COLOR)
            position_label.configure(background=ACTIVE_COLOR)
            label_frame.configure(background=ACTIVE_COLOR)
            slider_frame.configure(background=ACTIVE_COLOR)
            if parent_info:
                branch_data['parent_label'].configure(background=ACTIVE_COLOR)
    
    # Set active branch if current one was removed or none was set
    if not found_active_root and branch_roots:
         new_active_root = branch_roots[0]
         active_branch_root_id = new_active_root
         logger.info(f"Reset active branch to first available: {new_active_root}")
         if new_active_root in branch_widgets:
             # Use highlight color for the new active branch
             branch_widgets[new_active_root]['frame'].configure(background=ACTIVE_COLOR)
             branch_widgets[new_active_root]['label'].configure(background=ACTIVE_COLOR)
             if 'position_var' in branch_widgets[new_active_root]:
                 position_label = branch_widgets[new_active_root]['slider'].master.winfo_children()[0]
                 position_label.configure(background=ACTIVE_COLOR)
             # Configure all child frames
             for child in branch_widgets[new_active_root]['frame'].winfo_children():
                 child.configure(background=ACTIVE_COLOR)
    elif not branch_roots:
         active_branch_root_id = None 
         logger.info("No branches left, active_branch_root_id set to None.")
    
    # Trigger initial update for the (potentially new) active slider
    if active_branch_root_id in branch_widgets:
         active_slider = branch_widgets[active_branch_root_id]['slider']
         initial_val = active_slider.get()
         update_active_branch_slider(str(int(initial_val)), active_branch_root_id)
    
    # Update status bar
    if status_bar:
        branch_count = len(branch_roots)
        status_bar.config(text=f"Ready - {branch_count} branches available")

def replay_from_start():
    """Replay execution from the start of the active branch."""
    global DB_PATH, read_session, run_in_background_var
    if active_branch_root_id is None:
        logger.error("Error: No active branch root ID set.")
        return
    if DB_PATH is None:
        logger.error("DB_PATH not set, cannot replay.")
        return
        
    logger.info(f"Replaying from start of branch: {active_branch_root_id}")
    unchecked_globals = get_unchecked_globals()
    
    # Check if we should run in background
    run_in_bg = run_in_background_var and run_in_background_var.get()
    if run_in_bg and status_bar:
        status_bar.config(text="Starting background replay...")
    
    try:
        new_branch_start_id = replay_session_from(
            int(active_branch_root_id), DB_PATH, ignore_globals=unchecked_globals
        )
        
        if new_branch_start_id:
            logger.info(f"Replay started new branch with ID: {new_branch_start_id}")
            
            # Ensure database is refreshed before UI update
            if read_session:
                read_session.expire_all()  # Expire all objects to force reload
                
            # Refresh the UI to show the new slider/branch
            refresh_branch_ui()
            
            if status_bar:
                status_bar.config(text=f"Replay complete, new branch created: {new_branch_start_id}")
        else:
            logger.error("Replay failed.")
            if status_bar:
                status_bar.config(text="Replay failed - see logs for details")
    except Exception as e:
        logger.error(f"Error during replay: {str(e)}")
        # Show error in status label if available
        if status_label:
            status_label.config(text=f"Replay error: {str(e)}")
        if status_bar:
            status_bar.config(text=f"Replay error: {str(e)}")

def replay_from_here():
    """Replay execution starting from the currently selected call."""
    global DB_PATH, read_session, run_in_background_var
    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
         logger.error("Error: No active branch or valid selection.")
         return
    if DB_PATH is None:
        logger.error("DB_PATH not set, cannot replay.")
        return
        
    slider = branch_widgets[active_branch_root_id]['slider']
    current_value = slider.get()
    
    logger.info(f"Replaying from selected call: {current_value}")
    unchecked_globals = get_unchecked_globals()
    
    # Check if we should run in background
    run_in_bg = run_in_background_var and run_in_background_var.get()
    if run_in_bg and status_bar:
        status_bar.config(text="Starting background replay from current call...")
        if pygame_imitation_var:
            pygame.bypass_display_update(True)
    
    try:
        # The selected value IS the starting function ID for the new branch
        new_branch_start_id = replay_session_from(
            int(current_value), DB_PATH, ignore_globals=unchecked_globals
        )
        
        if new_branch_start_id:
            logger.info(f"Replay started new branch with ID: {new_branch_start_id}")
            
            # Ensure database is refreshed before UI update
            if read_session:
                read_session.expire_all()  # Expire all objects to force reload
                
            # Refresh the UI to show the new slider/branch
            refresh_branch_ui()
            
            if status_bar:
                status_bar.config(text=f"Replay complete, new branch created: {new_branch_start_id}")
            if pygame_imitation_var:
                pygame.bypass_display_update(False)
        else:
            logger.error("Replay failed.")
            if status_bar:
                status_bar.config(text="Replay failed - see logs for details")
    except Exception as e:
        logger.error(f"Error during replay: {str(e)}")
        # Show error in status label if available
        if status_label:
            status_label.config(text=f"Replay error: {str(e)}")
        if status_bar:
            status_bar.config(text=f"Replay error: {str(e)}")

def create_checkbox_command(root_id_ref: Callable[[], Optional[int]], widgets_ref: Dict[int, Dict[str, Any]]) -> Callable[[], None]:
    def command():
        current_root_id = root_id_ref()
        if current_root_id is not None and current_root_id in widgets_ref:
            slider = widgets_ref[current_root_id]['slider']
            current_val_str = str(int(slider.get()))
            # Call the slider update function directly
            update_active_branch_slider(current_val_str, current_root_id)
        else:
            logger.warning("Checkbox clicked, but no active branch/slider found.")
    return command

# --- Main Application Setup ---
def run_explorer(db_path: str, function_name: Optional[str] = None):
    """Sets up and runs the Tkinter explorer UI."""
    global DB_PATH, TARGET_FUNCTION_NAME, live_monitor, read_session, object_manager
    global call_tracker, current_session_info, initial_entry_point_id, active_branch_root_id
    global root, sliders_frame, checkbox_frame, play_pause_button, status_label, status_bar
    global checkbox_vars, checkbox_labels, checkbox_widgets # Keep global declaration
    
    # Add new global variables for the toggles
    global pygame_reuse_events_var, run_in_background_var
    pygame_reuse_events_var = None  # Will be set if pygame flag is True
    run_in_background_var = None  # Will be set to tk.BooleanVar

    DB_PATH = db_path
    TARGET_FUNCTION_NAME = function_name

    # --- Initialize Monitoring and DB Reading ---
    # Initialize a live monitor instance for recording replays
    logger.info(f"Initializing live monitor using DB: {DB_PATH}")
    live_monitor = init_monitoring(db_path=DB_PATH)

    # Start a session for this live monitor; needed for replay_session_from
    live_monitor_session_id = start_live_session("Replay Recording Session")
    if live_monitor_session_id is None:
        logger.warning("Failed to start live monitoring session for replay recording.")

    # Load the main database session for reading
    logger.info(f"Initializing read session for DB: {DB_PATH}")
    ReadSession = init_db(DB_PATH)
    read_session = ReadSession()
    object_manager = ObjectManager(read_session)
    call_tracker = FunctionCallTracker(read_session)
    current_session_info = read_session.query(MonitoringSession).first()
    if current_session_info is None:
        logger.error(f"No monitoring session found in database: {DB_PATH}")
        print(f"Error: Could not find monitoring session in {DB_PATH}")
        return # Exit if no session found
    
    # Determine initial entry point
    initial_entry_point_id = None
    if current_session_info.entry_point_call_id:
        # Fix type issue: Cast Column[Integer] to Optional[int]
        initial_entry_point_id = typing.cast(Optional[int], current_session_info.entry_point_call_id)
        logger.info(f"Initial Session Entry Point Call ID: {initial_entry_point_id}")
    elif TARGET_FUNCTION_NAME and TARGET_FUNCTION_NAME in current_session_info.function_calls_map:
        # Fix type issue: Handle conversion from ColumnElement to list correctly
        map_value = current_session_info.function_calls_map[TARGET_FUNCTION_NAME]
        try:
            # Handle different potential types safely
            str_list = []
            if hasattr(map_value, '__iter__') and not isinstance(map_value, str):
                # This handles both lists and other iterables
                str_list = [str(item) for item in map_value]
            elif map_value is not None:
                # If it's not iterable, convert single value to string
                str_list = [str(map_value)]
            
            ids_list = list(map(int, str_list))
            if ids_list:
                initial_entry_point_id = min(ids_list)
                logger.warning(f"Using fallback entry point ID (min call for {TARGET_FUNCTION_NAME}): {initial_entry_point_id}")
            else:
                logger.warning(f"No call IDs found for specified function '{TARGET_FUNCTION_NAME}' in the session map.")
        except (TypeError, ValueError) as e:
            logger.error(f"Error converting function calls map to integers: {e}")
    else:
        # Generic fallback: Find the earliest call ID across all functions in the first session
        all_call_ids = []
        if current_session_info.function_calls_map:
            for fname, ids in current_session_info.function_calls_map.items():
                # Ensure ids are cast to int before extending
                try:
                    str_ids = []
                    if hasattr(ids, '__iter__') and not isinstance(ids, str):
                        # This handles both lists and other iterables
                        str_ids = [str(item) for item in ids]
                    elif ids is not None:
                        # If it's not iterable, convert single value to string
                        str_ids = [str(ids)]
                    
                    all_call_ids.extend(map(int, str_ids))
                except (TypeError, ValueError) as e:
                    logger.error(f"Error converting {fname} calls to integers: {e}")
        if all_call_ids:
             initial_entry_point_id = min(all_call_ids)
             logger.warning(f"Using generic fallback entry point ID (earliest call in session): {initial_entry_point_id}")
        else:
            logger.error("Cannot determine session entry point. No calls recorded?")
            # Consider disabling buttons or exiting

    active_branch_root_id = initial_entry_point_id 
    assert isinstance(active_branch_root_id, int), f"Expected active_branch_root_id to be an integer, got {type(active_branch_root_id)}"
    if TARGET_FUNCTION_NAME is None:
        TARGET_FUNCTION_NAME = call_tracker.get_call(str(active_branch_root_id))["function"]
    else:
        logger.info(f"Initial active branch root ID set to: {active_branch_root_id} (for function: {TARGET_FUNCTION_NAME})")
    


    # --- Setup Tkinter UI ---
    root = tk.Tk()
    root.title(f"PyMonitor Explorer - {os.path.basename(DB_PATH)}")
    root.geometry("800x700") # Increased size for better visualization
    
    # Configure colors and styles
    bg_color = "#f5f5f5"  # Light gray background
    header_bg = "#e0e8f0"  # Light blue header
    button_bg = "#4a86e8"  # Blue buttons
    button_fg = "white"    # White text on buttons
    
    # Configure ttk styles
    style = ttk.Style()
    style.configure("TButton", font=("Arial", 10), padding=5)
    style.configure("TFrame", background=bg_color)
    style.configure("Header.TLabel", font=("Arial", 12, "bold"), background=header_bg, padding=5)
    style.configure("Status.TLabel", font=("Arial", 10), padding=3)
    
    # Define tooltip function for UI elements
    def create_tooltip(widget, text):
        """Create a tooltip for a widget."""
        if widget is None:
            return
            
        def show_tooltip(event=None):
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25
            
            # Create a toplevel window
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{x}+{y}")
            
            label = tk.Label(tooltip, text=text, justify=tk.LEFT,
                         background="#ffffd0", relief=tk.SOLID, borderwidth=1,
                         font=("Arial", 9, "normal"), padx=5, pady=2)
            label.pack(ipadx=1)
            
            def hide_tooltip(event=None):
                tooltip.destroy()
                
            tooltip.bind("<Leave>", hide_tooltip)
            widget.bind("<Leave>", hide_tooltip)
            
        widget.bind("<Enter>", show_tooltip)
        
    # Main UI Frames with improved styling
    main_frame = ttk.Frame(root, style="TFrame")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Header frame with title and refresh button
    header_frame = ttk.Frame(main_frame)
    header_frame.pack(fill=tk.X, side=tk.TOP, padx=5, pady=5)
    
    # Title label in header
    title_label = ttk.Label(header_frame, text="Execution Branches", style="Header.TLabel")
    title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    # Refresh button in header
    refresh_button = ttk.Button(header_frame, text="🔄 Refresh", command=refresh_branch_ui)
    refresh_button.pack(side=tk.RIGHT, padx=5)
    
    # Create scrollable frame for sliders
    canvas = tk.Canvas(main_frame, bg=bg_color)
    scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    
    # Create the sliders frame (ttk.Frame) and store in the global variable with proper type
    sliders_frame_local = ttk.Frame(canvas, style="TFrame")
    sliders_frame = sliders_frame_local  # Assign to global with proper type
    
    # Now we can safely use the local variable for binding
    sliders_frame_local.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=sliders_frame_local, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Button frames with improved styling - now split into two rows
    button_frame_row1 = ttk.Frame(main_frame)
    button_frame_row1.pack(fill=tk.X, side=tk.TOP, padx=5, pady=2)
    
    button_frame_row2 = ttk.Frame(main_frame)
    button_frame_row2.pack(fill=tk.X, side=tk.TOP, padx=5, pady=2)
    
    # Status frame for current call info
    status_frame = ttk.Frame(main_frame, relief=tk.SOLID, borderwidth=1)
    status_frame.pack(fill=tk.X, side=tk.TOP, padx=5, pady=5)
    
    # Status label for current call information
    status_label_local = ttk.Label(status_frame, style="Status.TLabel", anchor=tk.W, justify=tk.LEFT)
    status_label = status_label_local
    status_label_local.pack(fill=tk.X, expand=True, padx=5, pady=5)
    
    # Status bar at the bottom of the window
    status_bar_local = ttk.Label(root, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
    status_bar = status_bar_local  # Assign to global with proper type
    status_bar_local.pack(side=tk.BOTTOM, fill=tk.X)
    
    # Checkboxes frame for globals
    checkbox_frame_local = ttk.Frame(main_frame, relief=tk.SOLID, borderwidth=1)
    checkbox_frame = checkbox_frame_local
    checkbox_frame_local.pack(fill=tk.X, side=tk.TOP, padx=5, pady=5)
    
    # Row 1: Navigation buttons
    prev_button = ttk.Button(button_frame_row1, text="◀ Prev", command=prev_step)
    play_pause_button_local = ttk.Button(button_frame_row1, text="▶ Play", command=toggle_play_pause)
    play_pause_button = play_pause_button_local
    next_button = ttk.Button(button_frame_row1, text="Next ▶", command=next_step)
    
    # Row 2: Replay buttons and toggles
    reload_button = ttk.Button(button_frame_row2, text="🔄 Reload", command=reload_current)
    replay_start_button = ttk.Button(button_frame_row2, text="🔁 Replay Branch", command=replay_from_start)
    replay_here_button = ttk.Button(button_frame_row2, text="↪ Replay From Here", command=replay_from_here)
    
    # Add toggles to row 2
    toggle_frame = ttk.Frame(button_frame_row2)
    toggle_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
    
    # Run in background toggle
    run_in_background_var = tk.BooleanVar(value=False)
    run_bg_check = ttk.Checkbutton(
        toggle_frame,
        text="Run in background",
        variable=run_in_background_var
    )
    run_bg_check.pack(side=tk.RIGHT, padx=5)
    
    # Pygame reuse events toggle - only show if pygame flag is set
    # Check if pygame is available
    pygame_available = False
    try:
        import pygame
        pygame_available = True
    except ImportError:
        pygame_available = False
    
    # Check if pygame flag is set in args (can be passed from command line)
    pygame_flag = 'pygame' in sys.argv or '--pygame' in sys.argv
    
    if pygame_available and pygame_flag:
        # Import the monitoringpy.pygame module
        from .. import pygame as monitoringpy_pygame
        
        # Create pygame reuse events toggle
        pygame_reuse_events_var = tk.BooleanVar(value=True)  # Default to True
        pygame_check = ttk.Checkbutton(
            toggle_frame,
            text="Reuse Pygame events",
            variable=pygame_reuse_events_var,
            command=lambda: monitoringpy_pygame.set_screen_reuse(pygame_reuse_events_var.get() if pygame_reuse_events_var else True)
        )
        pygame_check.pack(side=tk.RIGHT, padx=5)
        
        # Initialize pygame screen reuse with the default value
        if pygame_reuse_events_var:
            monitoringpy_pygame.set_screen_reuse(pygame_reuse_events_var.get())
    
    # Retrieve Checkbox Labels (Use TARGET_FUNCTION_NAME if provided, else handle None)
    checkbox_labels = []
    if current_session_info and hasattr(current_session_info, 'common_globals') and isinstance(current_session_info.common_globals, dict):
        if TARGET_FUNCTION_NAME:
            checkbox_labels = current_session_info.common_globals.get(TARGET_FUNCTION_NAME, [])
            if not isinstance(checkbox_labels, list): checkbox_labels = []
            if not checkbox_labels:
                logger.warning(f"No common globals found for specified function: {TARGET_FUNCTION_NAME}")
        else:
            # Maybe show common globals for the entry point function? Or aggregate?
            # For now, just indicate none were specified.
            logger.info("No specific function name provided, not loading common globals checkboxes.")
            
    # Create Checkbox Widgets
    checkbox_vars = []  # Initialize or reset the list
    checkbox_widgets = []  # Initialize or reset the list
    
    if checkbox_labels: 
        for i, label in enumerate(checkbox_labels):
            var = tk.BooleanVar(value=True)  
            checkbox_vars.append(var)
            cb = ttk.Checkbutton(checkbox_frame_local, text=label, variable=var)
            checkbox_widgets.append(cb)
    else:
        no_globals_label = ttk.Label(checkbox_frame_local, text="No common globals found or function not specified.")
        no_globals_label.pack()

    # Set commands for checkboxes
    if checkbox_labels:
        checkbox_command = create_checkbox_command(lambda: active_branch_root_id, branch_widgets)
        for cb in checkbox_widgets:
            cb.configure(command=checkbox_command)
    
    # Pack navigation buttons in row 1
    for btn in [prev_button, play_pause_button_local, next_button]:
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)
    
    # Pack replay buttons in row 2
    for btn in [reload_button, replay_start_button, replay_here_button]:
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)
    
    # Set up checkbox grid
    if checkbox_labels:
        CHECKBOXES_PER_ROW = 4  # Adjusted for wider window
        for i, cb in enumerate(checkbox_widgets):
            row_num = i // CHECKBOXES_PER_ROW
            col_num = i % CHECKBOXES_PER_ROW
            cb.grid(row=row_num, column=col_num, padx=5, pady=2, sticky=tk.W)
    
    # Apply tooltips to buttons
    create_tooltip(prev_button, "Move to the previous step in the current branch")
    create_tooltip(next_button, "Move to the next step in the current branch")
    create_tooltip(play_pause_button_local, "Play/pause automatic stepping through the current branch")
    create_tooltip(reload_button, "Reload the current function state")
    create_tooltip(replay_start_button, "Start a new branch from the beginning of the current branch")
    create_tooltip(replay_here_button, "Start a new branch from the current call")
    create_tooltip(refresh_button, "Refresh the UI with the latest data")
    create_tooltip(run_bg_check, "Run replays in background mode")
    
    # Initial UI Population
    refresh_branch_ui()
    
    # Disable Buttons (If needed)
    if active_branch_root_id is None:
        logger.warning("Disabling controls as no active branch found initially.")
        replay_start_button.config(state=tk.DISABLED)
        replay_here_button.config(state=tk.DISABLED)
        prev_button.config(state=tk.DISABLED)
        play_pause_button_local.config(state=tk.DISABLED)
        next_button.config(state=tk.DISABLED)
        reload_button.config(state=tk.DISABLED)

    # Run mainloop
    root.mainloop()

    # Clean up read session when GUI closes
    if read_session:
        read_session.close()
        logger.info("Read session closed.")

# --- Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyMonitor Database Explorer GUI")
    parser.add_argument("db_path", help="Path to the monitoring database file (.db)")
    parser.add_argument("-f", "--function-name", 
                        help="Optional: Specific function name to focus on for globals", 
                        default=None)
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging (INFO level)")
    parser.add_argument("-pg", "--pygame", action="store_true", help="Activate pygame screen reuse")
    parser.add_argument("--background", action="store_true", help="Enable background mode for replays")
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"Error: Database file not found at {args.db_path}")
        exit(1)

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    else:
         logging.getLogger().setLevel(logging.WARNING) # Default to WARNING otherwise

    if args.pygame:
        from monitoringpy import pygame
        pygame_imitation_var = True
        pygame.set_screen_reuse(True)
    else:
        pygame_imitation_var = False

    # Here we just pass any processed flags to the explorer
    # The actual handling happens inside run_explorer
    run_explorer(args.db_path, args.function_name)
