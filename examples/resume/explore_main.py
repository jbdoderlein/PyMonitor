import monitoringpy
import tkinter as tk
from typing import List, Optional, Any, Dict, Callable
import tkinter.ttk as ttk
from sqlalchemy.orm import Session as SQLASession
import typing
import logging

DB = "examples/resume/main.db"
FUNCTION_NAME = "play_game"

# 2. Data Retrieval Functions
def get_branch_roots(session: SQLASession) -> List[int]:
    roots = []
    main_session = session.query(monitoringpy.MonitoringSession).first()
    if main_session and main_session.entry_point_call_id:
        roots.append(main_session.entry_point_call_id)
    branch_starts = session.query(monitoringpy.FunctionCall).\
        filter(monitoringpy.FunctionCall.parent_call_id != None).\
        order_by(monitoringpy.FunctionCall.start_time).all()
    for call in branch_starts:
        if call.id is not None and call.id not in roots:
             roots.append(call.id)
    if main_session and main_session.entry_point_call_id is not None and main_session.entry_point_call_id not in roots:
         roots.append(main_session.entry_point_call_id)
    int_roots = [r for r in roots if isinstance(r, int)]
    return sorted(list(set(int_roots)))

def get_branch_sequence(session: SQLASession, root_call_id: int) -> List[int]:
    sequence = []
    current_call_id: Optional[int] = root_call_id
    while current_call_id is not None:
        call = session.get(monitoringpy.FunctionCall, current_call_id)
        if call:
            sequence.append(call.id)
            # Ensure we handle None next_call_id gracefully
            next_id = getattr(call, 'next_call_id', None) 
            current_call_id = int(next_id) if next_id is not None else None 
        else:
            break
    print(f"Sequence for root {root_call_id}: {sequence}")
    return sequence

def get_branch_depth(session: SQLASession, call_id: int, max_depth=10) -> int:
    """Calculates the depth of a call by traversing parent links."""
    depth = 0
    current_id: Optional[int] = call_id
    visited = set()
    while depth < max_depth:
        if current_id is None or current_id in visited:
            break # Reached root or cycle detected
        visited.add(current_id)
        call = session.get(monitoringpy.FunctionCall, current_id)
        if call and call.parent_call_id is not None:
            current_id = typing.cast(typing.Optional[int], call.parent_call_id)
            depth += 1
        else:
            break # Reached the main branch root
    if depth >= max_depth:
        print(f"Warning: Max depth reached for call {call_id}, returning {max_depth}")
    return depth

# Initialize a live monitor instance for recording replays
# Use the main DB so replay branches are stored alongside original trace
live_monitor = monitoringpy.init_monitoring(db_path=DB)

# Set logging level to INFO to see more details
logging.getLogger().setLevel(logging.ERROR)

# Start a session for this live monitor; needed for replay_session_from
# We don't necessarily need the ID unless we explicitly manage this session later
live_monitor_session_id = monitoringpy.start_session("Replay Recording Session")
if live_monitor_session_id is None:
    print("WARNING: Failed to start live monitoring session for replay recording.")
    # Handle this case if needed, maybe disable replay button?

# Load the main database session for reading
Session = monitoringpy.init_db(DB)
session = Session()
object_manager = monitoringpy.ObjectManager(session)
call_tracker = monitoringpy.FunctionCallTracker(session)
current_session = session.query(monitoringpy.MonitoringSession).first()
assert current_session is not None

# Keep track of the root ID of the branch currently being viewed/controlled
# Initially, it's the entry point of the first session loaded.
initial_entry_point_id = None
if current_session and current_session.entry_point_call_id:
    initial_entry_point_id = current_session.entry_point_call_id
    print(f"Initial Session Entry Point Call ID: {initial_entry_point_id}")
elif current_session and FUNCTION_NAME in current_session.function_calls_map and current_session.function_calls_map[FUNCTION_NAME]:
    # Fallback if entry_point_call_id wasn't set (shouldn't happen ideally)
    ids_list = list(map(int, current_session.function_calls_map[FUNCTION_NAME]))
    if ids_list:
        initial_entry_point_id = min(ids_list)
        print(f"Warning: Using fallback entry point ID: {initial_entry_point_id}")
    else:
        print("Warning: No call IDs found for function in the session map.")
else:
    print("Error: Cannot determine session entry point. Disabling replay buttons.")
    # Consider disabling buttons here

# 4. Global UI State
active_branch_root_id: Optional[int] = initial_entry_point_id 
branch_widgets: Dict[int, Dict[str, Any]] = {}
is_playing = False
play_timer_id = None
checkbox_vars = []
checkbox_labels = []

# 5. Tkinter Root Window
root = tk.Tk()
root.title("Main Controls")
root.geometry("400x300") 

# 6. Main UI Frames
main_frame = tk.Frame(root)
main_frame.pack(fill=tk.BOTH, expand=True)
sliders_frame = tk.Frame(main_frame)
sliders_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP, padx=5, pady=5)
button_frame = tk.Frame(main_frame)
button_frame.pack(fill=tk.X, side=tk.TOP, padx=5)
checkbox_frame = tk.Frame(main_frame, bd=1, relief=tk.SOLID)
checkbox_frame.pack(fill=tk.X, side=tk.TOP, padx=5, pady=5)

# 7. Widget Creation (No commands yet)
prev_button = tk.Button(button_frame, text="Prev")
play_pause_button = tk.Button(button_frame, text="Play") 
next_button = tk.Button(button_frame, text="Next")
reload_button = tk.Button(button_frame, text="Reload")
replay_start_button = tk.Button(button_frame, text="Replay from Start")
replay_here_button = tk.Button(button_frame, text="Replay from Here")

# Retrieve Checkbox Labels
if current_session and hasattr(current_session, 'common_globals') and isinstance(current_session.common_globals, dict):
    checkbox_labels = current_session.common_globals.get(FUNCTION_NAME, [])
    if not isinstance(checkbox_labels, list): checkbox_labels = []
elif not current_session: pass
else: pass

# Create Checkbox Widgets
checkbox_widgets: List[tk.Checkbutton] = []
if checkbox_labels: 
    for i, label in enumerate(checkbox_labels):
        var = tk.BooleanVar(value=True)  
        checkbox_vars.append(var)
        cb = tk.Checkbutton(checkbox_frame, text=label, variable=var)
        checkbox_widgets.append(cb)
else:
    no_globals_label = tk.Label(checkbox_frame, text="No common globals found.")

# 8. UI Callback Functions
def get_unchecked_globals() -> List[str]:
    """Returns a list of global variables that are currently unchecked."""
    unchecked = []
    for i, var in enumerate(checkbox_vars):
        if not var.get():  # If checkbox is unchecked
            unchecked.append(checkbox_labels[i])
    return unchecked

def update_active_branch_slider(selected_call_id_str: str, branch_root_id: int):
    """Callback when any branch slider changes."""
    # print(f"Slider for branch {branch_root_id} changed to {selected_call_id_str}") # Reduced verbosity
    set_active_branch(branch_root_id) # Mark this branch as active
    unchecked_globals = get_unchecked_globals()
    # Ensure monitor recording is off for simple reanimation
    monitoringpy.reanimate_function(
        selected_call_id_str, DB, ignore_globals=unchecked_globals
    )

def set_active_branch(branch_root_id: int):
    """Sets the currently active branch for controls."""
    global active_branch_root_id
    # Only print if changed?
    if active_branch_root_id != branch_root_id and branch_root_id in branch_widgets:
        print(f"Setting active branch to: {branch_root_id}")
        active_branch_root_id = branch_root_id
    # elif branch_root_id not in branch_widgets:
    #     print(f"Warning: Attempted to set non-existent branch {branch_root_id} as active.")

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
    global play_timer_id, is_playing
    if is_playing:
        if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
             toggle_play_pause() # Stop if no active branch
             return
        slider = branch_widgets[active_branch_root_id]['slider']
        sequence = branch_widgets[active_branch_root_id]['sequence']
        
        current_value = slider.get()
        try:
             current_index = sequence.index(int(current_value))
             if current_index < len(sequence) - 1:
                  next_step() # Use existing next_step logic
                  play_timer_id = root.after(100, play_step) # Schedule next frame
             else:
                  toggle_play_pause() # Auto-pause at the end
        except ValueError:
             toggle_play_pause() # Stop if current value not in sequence

def toggle_play_pause():
    """Toggle between playing and pausing the slider animation."""
    global is_playing, play_timer_id
    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
        print("Cannot play/pause: No active branch.")
        return # Don't toggle if no active branch
        
    slider = branch_widgets[active_branch_root_id]['slider']
    sequence = branch_widgets[active_branch_root_id]['sequence']
    
    if is_playing:
        if play_timer_id:
            root.after_cancel(play_timer_id)
            play_timer_id = None
        is_playing = False
        play_pause_button.config(text="Play")
    else:
        is_playing = True
        play_pause_button.config(text="Pause")
        # Reset to start if at the end
        if slider.get() >= slider.cget("to"):
             if sequence: # Check if sequence is not empty
                  set_slider_value(slider, sequence[0])
        play_step() 

def reload_current():
    """Force reload the current function selected by the active slider."""
    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
        return
    slider = branch_widgets[active_branch_root_id]['slider']
    current_value = slider.get()
    unchecked_globals = get_unchecked_globals()
    monitoringpy.reanimate_function(
        str(int(current_value)), DB, ignore_globals=unchecked_globals
    )

def refresh_branch_ui():
    """Dynamically create/update sliders for each execution branch."""
    # print("Refreshing Branch UI...") # Reduced verbosity
    global active_branch_root_id 
    branch_roots = get_branch_roots(session)
    found_active_root = False

    # Define indentation amount per depth level
    INDENT_STEP = 20 # pixels

    for root_id in branch_roots:
        if root_id not in branch_widgets:
            print(f"Creating UI for new branch root: {root_id}")
            branch_sequence = get_branch_sequence(session, root_id)
            if not branch_sequence:
                print(f"Skipping branch {root_id}: No sequence found.")
                continue
            
            # Calculate depth for indentation
            depth = get_branch_depth(session, root_id)
            indent_amount = depth * INDENT_STEP
            print(f"Branch {root_id} depth: {depth}, indent: {indent_amount}")

            # Create frame with potential left padding for indentation
            branch_frame = tk.Frame(sliders_frame, bd=1, relief=tk.GROOVE)
            # Pack the frame first, then pack items inside it
            branch_frame.pack(fill=tk.X, pady=2, padx=(indent_amount, 0))

            parent_call = session.get(monitoringpy.FunctionCall, root_id)
            label_text = f"Branch {root_id}"
            if parent_call and parent_call.parent_call_id:
                 label_text += f" (from Call {parent_call.parent_call_id})"
            elif initial_entry_point_id is not None and root_id == initial_entry_point_id:
                 label_text = f"Main Branch (Start: {root_id})"

            branch_label = tk.Label(branch_frame, text=label_text)
            branch_label.pack(side=tk.LEFT, padx=5)

            slider_min = min(branch_sequence)
            slider_max = max(branch_sequence)
            
            slider_command = lambda val, rid=root_id: update_active_branch_slider(val, rid)
            branch_slider = tk.Scale(
                branch_frame,
                from_=slider_min,
                to=slider_max,
                orient=tk.HORIZONTAL,
                command=slider_command,
                length=250 
            )
            branch_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            branch_slider.bind("<Button-1>", lambda event, rid=root_id: set_active_branch(rid))
            branch_label.bind("<Button-1>", lambda event, rid=root_id: set_active_branch(rid))
            # Frame is already packed above

            branch_widgets[root_id] = {
                'frame': branch_frame,
                'slider': branch_slider,
                'label': branch_label,
                'sequence': branch_sequence
            }
        else:
            # TODO: Maybe update indentation if parent structure changes?
            pass 

        if root_id == active_branch_root_id:
            found_active_root = True

    existing_roots = list(branch_widgets.keys())
    for root_id in existing_roots:
        if root_id not in branch_roots:
            print(f"Removing UI for obsolete branch root: {root_id}")
            branch_widgets[root_id]['frame'].destroy()
            del branch_widgets[root_id]
            if root_id == active_branch_root_id:
                active_branch_root_id = initial_entry_point_id 
                found_active_root = True 

    if not found_active_root and branch_roots:
         active_branch_root_id = branch_roots[0] 
         print(f"Reset active branch to first available: {active_branch_root_id}")
    elif not branch_roots:
         active_branch_root_id = None 
         print("No branches left, active_branch_root_id set to None.")

    # print(f"Branch UI Refresh Complete. Active root: {active_branch_root_id}") # Reduced verbosity

def replay_from_start():
    """Replay execution from the start of the active branch."""
    if active_branch_root_id is None:
        print("Error: No active branch root ID set.")
        return
    print(f"Replaying from start of branch: {active_branch_root_id}")
    unchecked_globals = get_unchecked_globals()
    new_branch_start_id = monitoringpy.replay_session_from(
        int(active_branch_root_id), DB, ignore_globals=unchecked_globals
    )
    if new_branch_start_id:
        print(f"Replay started new branch with ID: {new_branch_start_id}")
        # TODO: Refresh the UI to show the new slider/branch
        refresh_branch_ui()
    else:
        print("Replay failed.")

def replay_from_here():
    """Replay execution starting from the currently selected call."""
    if active_branch_root_id is None or active_branch_root_id not in branch_widgets:
         print("Error: No active branch or valid selection.")
         return
    slider = branch_widgets[active_branch_root_id]['slider']
    current_value = slider.get()
    if active_branch_root_id is None: # Should also check if current_value is valid
         print("Error: No active branch or valid selection.")
         return
    print(f"Replaying from selected call: {current_value}")
    unchecked_globals = get_unchecked_globals()
    # The selected value IS the starting function ID for the new branch
    new_branch_start_id = monitoringpy.replay_session_from(
        int(current_value), DB, ignore_globals=unchecked_globals
    )
    if new_branch_start_id:
        print(f"Replay started new branch with ID: {new_branch_start_id}")
        # TODO: Refresh the UI to show the new slider/branch
        refresh_branch_ui()
    else:
        print("Replay failed.")

def create_checkbox_command(root_id_ref: Callable[[], Optional[int]], widgets_ref: Dict[int, Dict[str, Any]]) -> Callable[[], None]:
    def command():
        current_root_id = root_id_ref()
        if current_root_id is not None and current_root_id in widgets_ref:
            slider = widgets_ref[current_root_id]['slider']
            current_val_str = str(int(slider.get()))
            # Call the slider update function directly
            update_active_branch_slider(current_val_str, current_root_id)
        else:
            print("Checkbox clicked, but no active branch/slider found.")
    return command

# 9. Assign Commands
prev_button.config(command=prev_step)
play_pause_button.config(command=toggle_play_pause) 
next_button.config(command=next_step)
reload_button.config(command=reload_current)
replay_start_button.config(command=replay_from_start)
replay_here_button.config(command=replay_from_here)

if checkbox_labels:
    checkbox_command = create_checkbox_command(lambda: active_branch_root_id, branch_widgets)
    for cb in checkbox_widgets:
        cb.config(command=checkbox_command)

# 10. Pack Widgets
prev_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
play_pause_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
next_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
reload_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
replay_start_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True) 
replay_here_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True) 

if checkbox_labels:
    CHECKBOXES_PER_ROW = 3
    for i, cb in enumerate(checkbox_widgets):
        row_num = i // CHECKBOXES_PER_ROW
        col_num = i % CHECKBOXES_PER_ROW
        cb.grid(row=row_num, column=col_num, padx=5, pady=2, sticky=tk.W)
else:
    no_globals_label.pack() 

# 11. Initial UI Population
refresh_branch_ui() 

# 12. Disable Buttons (If needed)
if active_branch_root_id is None:
    print("Disabling controls as no active branch found initially.")
    # ... (disable buttons as before) ...
    replay_start_button.config(state=tk.DISABLED)
    replay_here_button.config(state=tk.DISABLED)
    prev_button.config(state=tk.DISABLED)
    play_pause_button.config(state=tk.DISABLED)
    next_button.config(state=tk.DISABLED)
    reload_button.config(state=tk.DISABLED)

# 13. Run mainloop
root.mainloop()
