#!/usr/bin/env python3
"""
Simple Flappy Bird Replay Script

A simple Tkinter-based tool to replay the flappy bird game execution
with multiple sliders for different branches and proper tracked function display.
"""

import tkinter as tk
from tkinter import ttk
import base64
import io
from PIL import Image, ImageTk
import os
import sys
from typing import List, Optional, Dict, Any

# Add the src directory to the path to import monitoringpy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from monitoringpy.core import init_db, FunctionCall, MonitoringSession, ObjectManager
from monitoringpy.core.reanimation import replay_session_sequence
import monitoringpy

class FlappyReplay:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.session = None
        self.object_manager = None
        self.sessions_data = {}  # Dict[session_id, Dict] containing session info and calls
        self.current_session_id = None
        self.current_call_index = 0
        
        # UI components
        self.root = None
        self.image_label = None
        self.sliders_frame = None
        self.info_label = None
        self.variables_tree = None
        self.globals_content = None
        self.tracked_content = None
        self.status_label = None
        
        # Checkbox variables for globals and tracked functions
        self.global_vars = {}  # Dict[str, tk.BooleanVar]
        self.tracked_vars = {}  # Dict[str, tk.BooleanVar]
        
        # Slider widgets for each session
        self.session_sliders = {}  # Dict[session_id, Dict] containing slider widgets
        
        # Tree state management
        self.expanded_items = set()  # Track which tree items are expanded
        
        # Branching and transparency overlay features
        self.session_relationships = {}  # Dict[session_id, Dict] containing parent/child relationships
        self.transparency_session_id = None  # Session ID to show with transparency
        self.transparency_var = None  # Will be created in _create_ui
        self.transparency_dropdown = None  # Reference to the dropdown widget
        
        # Initialize database
        self._init_database()
        
    def _analyze_session_relationships(self):
        """Analyze parent-child relationships between sessions based on parent_call_id"""
        for session_id, session_data in self.sessions_data.items():
            self.session_relationships[session_id] = {
                'parent_session_id': None,
                'branch_point_call_id': None,
                'branch_point_index': None,
                'child_sessions': []
            }
            
            # Check if any call in this session has a parent_call_id from another session
            for call in session_data['calls']:
                if call.parent_call_id and self.session:
                    # Find which session the parent call belongs to
                    parent_call = self.session.get(FunctionCall, call.parent_call_id)
                    if parent_call and parent_call.session_id != session_id:
                        # This session branches from another session
                        parent_session_id = parent_call.session_id
                        self.session_relationships[session_id]['parent_session_id'] = parent_session_id
                        self.session_relationships[session_id]['branch_point_call_id'] = call.parent_call_id
                        
                        # Find the index of the branch point in the parent session
                        if parent_session_id in self.sessions_data:
                            parent_calls = self.sessions_data[parent_session_id]['calls']
                            for i, parent_call_obj in enumerate(parent_calls):
                                if parent_call_obj.id == call.parent_call_id:
                                    self.session_relationships[session_id]['branch_point_index'] = i
                                    break
                        break  # Only need to find one parent relationship per session
        
        # Build child relationships
        for session_id, rel in self.session_relationships.items():
            if rel['parent_session_id']:
                parent_id = rel['parent_session_id']
                if parent_id in self.session_relationships:
                    self.session_relationships[parent_id]['child_sessions'].append(session_id)
        
    def _init_database(self):
        """Initialize database connection and load sessions with function calls"""
        if not os.path.exists(self.db_path):
            print(f"Error: Database file not found at {self.db_path}")
            sys.exit(1)
            
        # Initialize database session
        Session = init_db(self.db_path)
        self.session = Session()
        self.object_manager = ObjectManager(self.session)
        
        # Get all monitoring sessions
        sessions = self.session.query(MonitoringSession).order_by(MonitoringSession.start_time).all()
        
        if not sessions:
            print("Error: No monitoring sessions found in database")
            sys.exit(1)
            
        # Load display_game calls for each session
        for session in sessions:
            display_game_calls = self.session.query(FunctionCall).filter(
                FunctionCall.session_id == session.id,
                FunctionCall.function == 'display_game'
            ).order_by(FunctionCall.order_in_session).all()
            
            if display_game_calls:
                self.sessions_data[session.id] = {
                    'session': session,
                    'calls': display_game_calls,
                    'name': session.name or f"Session {session.id}",
                    'start_time': session.start_time
                }
                
        if not self.sessions_data:
            print("Error: No display_game function calls found in any session")
            sys.exit(1)
            
        # Set the first session as current
        self.current_session_id = list(self.sessions_data.keys())[0]
        
        # Analyze branching relationships
        self._analyze_session_relationships()
        
        print(f"Found {len(self.sessions_data)} sessions with display_game calls")
        for session_id, data in self.sessions_data.items():
            print(f"  Session {session_id}: {len(data['calls'])} calls - {data['name']}")
            if session_id in self.session_relationships:
                rel = self.session_relationships[session_id]
                if rel['parent_session_id']:
                    print(f"    -> Branches from session {rel['parent_session_id']} at call {rel['branch_point_call_id']}")
                if rel['child_sessions']:
                    print(f"    -> Has child branches: {rel['child_sessions']}")
        
    def _get_call_data(self, session_id: int, call_index: int) -> Dict[str, Any]:
        """Get data for a specific function call in a session"""
        if session_id not in self.sessions_data:
            return {}
            
        calls = self.sessions_data[session_id]['calls']
        if call_index < 0 or call_index >= len(calls):
            return {}
            
        call = calls[call_index]
        
        # Get the image from call metadata
        image_data = None
        if call.call_metadata and 'image' in call.call_metadata:
            image_data = call.call_metadata['image']
            
        # Get all variables from locals and globals
        variables = {'locals': {}, 'globals': {}}
        
        # Load locals
        if call.locals_refs and self.object_manager:
            for var_name, ref in call.locals_refs.items():
                try:
                    var_value = self.object_manager.rehydrate(ref)
                    variables['locals'][var_name] = var_value
                except Exception as e:
                    print(f"Error loading local variable {var_name}: {e}")
                    variables['locals'][var_name] = f"Error loading: {e}"
        
        # Load globals
        if call.globals_refs and self.object_manager:
            for var_name, ref in call.globals_refs.items():
                # Skip system variables
                if not var_name.startswith('__'):
                    try:
                        var_value = self.object_manager.rehydrate(ref)
                        variables['globals'][var_name] = var_value
                    except Exception as e:
                        print(f"Error loading global variable {var_name}: {e}")
                        variables['globals'][var_name] = f"Error loading: {e}"
                        
        return {
            'image_data': image_data,
            'variables': variables,
            'call_id': call.id,
            'timestamp': call.start_time,
            'session_id': session_id,
            'call_index': call_index
        }
        
    def _get_transparency_call_data(self, current_session_id: int, current_call_index: int) -> Optional[Dict[str, Any]]:
        """Get call data from transparency session that corresponds to the current position"""
        if not self.transparency_session_id or self.transparency_session_id not in self.sessions_data:
            return None
            
        # Check if transparency session is a child of current session
        transparency_rel = self.session_relationships.get(self.transparency_session_id, {})
        if transparency_rel.get('parent_session_id') == current_session_id:
            # Transparency session branches from current session
            branch_point_index = transparency_rel.get('branch_point_index')
            if branch_point_index is not None and current_call_index >= branch_point_index:
                # Current position is at or after the branch point
                # Map to corresponding position in transparency session
                offset_in_transparency = current_call_index - branch_point_index
                transparency_calls = self.sessions_data[self.transparency_session_id]['calls']
                if offset_in_transparency < len(transparency_calls):
                    return self._get_call_data(self.transparency_session_id, offset_in_transparency)
        
        # Check if current session is a child of transparency session
        current_rel = self.session_relationships.get(current_session_id, {})
        if current_rel.get('parent_session_id') == self.transparency_session_id:
            # Current session branches from transparency session
            branch_point_index = current_rel.get('branch_point_index')
            if branch_point_index is not None:
                # Map current position back to transparency session
                transparency_index = branch_point_index + current_call_index
                transparency_calls = self.sessions_data[self.transparency_session_id]['calls']
                if transparency_index < len(transparency_calls):
                    return self._get_call_data(self.transparency_session_id, transparency_index)
        
        return None
        
    def _decode_image(self, image_data: str, transparency_image_data: Optional[str] = None) -> Optional[ImageTk.PhotoImage]:
        """Decode base64 image data to PhotoImage, optionally blending with transparency overlay"""
        try:
            # Decode base64 data
            image_bytes = base64.b64decode(image_data)
            
            # Create PIL Image
            pil_image = Image.open(io.BytesIO(image_bytes))
            
            # Resize image to be smaller (scale down by 0.6)
            original_width, original_height = pil_image.size
            new_width = int(original_width * 0.6)
            new_height = int(original_height * 0.6)
            pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # If transparency overlay is provided, blend the images
            if transparency_image_data:
                try:
                    # Decode transparency image
                    transparency_bytes = base64.b64decode(transparency_image_data)
                    transparency_image = Image.open(io.BytesIO(transparency_bytes))
                    
                    # Resize transparency image to match main image
                    transparency_image = transparency_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Convert both images to RGBA for blending
                    if pil_image.mode != 'RGBA':
                        pil_image = pil_image.convert('RGBA')
                    if transparency_image.mode != 'RGBA':
                        transparency_image = transparency_image.convert('RGBA')
                    
                    # Use a lighter blending approach to avoid darkening
                    # Convert transparency image to have 30% opacity instead of 50%
                    transparency_overlay = transparency_image.copy()
                    
                    # Create a mask for blending - use screen blend mode effect
                    # This approach brightens instead of darkening
                    if pil_image.mode != 'RGB':
                        pil_image = pil_image.convert('RGB')
                    if transparency_overlay.mode != 'RGB':
                        transparency_overlay = transparency_overlay.convert('RGB')
                    
                    # Use PIL's blend with a lower alpha to reduce darkening
                    # 0.3 gives a subtle overlay without too much darkening
                    pil_image = Image.blend(pil_image, transparency_overlay, 0.3)
                    
                except Exception as e:
                    print(f"Error blending transparency image: {e}")
                    # Continue with just the main image
            
            # Convert to PhotoImage for Tkinter
            photo = ImageTk.PhotoImage(pil_image)
            return photo
        except Exception as e:
            print(f"Error decoding image: {e}")
            return None
            
    def _update_display(self, session_id: int, call_index: int):
        """Update the display with data from the specified call"""
        self.current_session_id = session_id
        self.current_call_index = call_index
        call_data = self._get_call_data(session_id, call_index)
        
        # Update image with optional transparency overlay
        if call_data.get('image_data') and self.image_label:
            transparency_image_data = None
            
            # Check if we should show transparency overlay
            if self.transparency_session_id and self.transparency_session_id != session_id:
                transparency_call_data = self._get_transparency_call_data(session_id, call_index)
                if transparency_call_data:
                    transparency_image_data = transparency_call_data.get('image_data')
            
            photo = self._decode_image(call_data['image_data'], transparency_image_data)
            if photo:
                self.image_label.configure(image=photo)  # type: ignore
                # Keep a reference to prevent garbage collection
                setattr(self.image_label, 'image', photo)
                
        # Update variable info
        self._update_variables_display(call_data)
        
        # Update status
        if self.status_label:
            session_name = self.sessions_data[session_id]['name']
            total_calls = len(self.sessions_data[session_id]['calls'])
            self.status_label.configure(
                text=f"Viewing {session_name} - Frame {call_index + 1}/{total_calls}", 
                foreground="blue"
            )
            
    def _on_slider_change(self, session_id: int, value: str):
        """Handle slider value change for a specific session"""
        try:
            index = int(float(value))
            self._update_display(session_id, index)
            
            # Synchronize parent session slider if this is a branch session
            self._sync_parent_slider(session_id, index)
            
            # Also synchronize child session sliders if this is a parent session
            self._sync_child_sliders(session_id, index)
            
        except (ValueError, IndexError) as e:
            print(f"Error updating display: {e}")
            
    def _on_transparency_selection_changed(self, event):
        """Handle transparency overlay selection change"""
        if not self.transparency_var:
            return
            
        selected_name = self.transparency_var.get()
        
        if selected_name == "None":
            self.transparency_session_id = None
        else:
            # Find session ID by name
            for session_id, session_data in self.sessions_data.items():
                if session_data['name'] == selected_name:
                    self.transparency_session_id = session_id
                    break
        
        # Refresh the current display to apply/remove transparency
        if self.current_session_id is not None:
            self._update_display(self.current_session_id, self.current_call_index)
            
    def _sync_parent_slider(self, session_id: int, current_index: int):
        """Synchronize parent session slider when exploring a branch session"""
        if session_id not in self.session_relationships:
            return
            
        rel = self.session_relationships[session_id]
        parent_session_id = rel.get('parent_session_id')
        branch_point_index = rel.get('branch_point_index')
        
        if parent_session_id and branch_point_index is not None:
            # Calculate the corresponding position in the parent session
            parent_index = branch_point_index + current_index
            
            # Update the parent session slider if it exists
            if parent_session_id in self.session_sliders:
                parent_slider = self.session_sliders[parent_session_id]['slider']
                if parent_slider:
                    # Check if the parent index is within bounds
                    parent_calls_count = len(self.sessions_data[parent_session_id]['calls'])
                    if parent_index < parent_calls_count:
                        # Temporarily disable the command to avoid recursion
                        old_command = parent_slider['command']
                        parent_slider.configure(command='')
                        parent_slider.set(parent_index)
                        parent_slider.configure(command=old_command)
                        
                        print(f"Synced parent session {parent_session_id} slider to position {parent_index}")
    
    def _sync_child_sliders(self, session_id: int, current_index: int):
        """Synchronize child session sliders when exploring a parent session"""
        if session_id not in self.session_relationships:
            return
            
        rel = self.session_relationships[session_id]
        child_sessions = rel.get('child_sessions', [])
        
        for child_session_id in child_sessions:
            if child_session_id in self.session_relationships:
                child_rel = self.session_relationships[child_session_id]
                branch_point_index = child_rel.get('branch_point_index')
                
                if branch_point_index is not None and current_index >= branch_point_index:
                    # Calculate the corresponding position in the child session
                    child_index = current_index - branch_point_index
                    
                    # Update the child session slider if it exists and the index is valid
                    if child_session_id in self.session_sliders:
                        child_slider = self.session_sliders[child_session_id]['slider']
                        if child_slider:
                            child_calls_count = len(self.sessions_data[child_session_id]['calls'])
                            if child_index < child_calls_count:
                                # Temporarily disable the command to avoid recursion
                                old_command = child_slider['command']
                                child_slider.configure(command='')
                                child_slider.set(child_index)
                                child_slider.configure(command=old_command)
                                
                                print(f"Synced child session {child_session_id} slider to position {child_index}")
    
    def _update_transparency_dropdown(self):
        """Update the transparency dropdown options after database refresh"""
        if not self.transparency_var or not self.transparency_dropdown:
            return
            
        try:
            # Get current selection
            current_selection = self.transparency_var.get()
            
            # Create new options list
            transparency_options = ["None"] + [self.sessions_data[sid]['name'] for sid in self.sessions_data.keys()]
            
            # Update the dropdown values
            self.transparency_dropdown.configure(values=transparency_options)
            
            # Check if current selection is still valid
            if current_selection != "None":
                valid_names = [self.sessions_data[sid]['name'] for sid in self.sessions_data.keys()]
                if current_selection not in valid_names:
                    self.transparency_var.set("None")
                    self.transparency_session_id = None
                    print(f"Reset transparency selection - '{current_selection}' no longer available")
                    
        except Exception as e:
            print(f"Error updating transparency dropdown: {e}")
            
    def _create_ui(self):
        """Create the Tkinter UI"""
        self.root = tk.Tk()
        self.root.title("Flappy Bird Replay - Multi-Branch")
        self.root.geometry("1400x900")
        
        # Create transparency variable now that root exists
        self.transparency_var = tk.StringVar(value="None")
        
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top frame for image and controls side by side
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Left side - Image frame (smaller)
        image_frame = ttk.LabelFrame(top_frame, text="Game Screen", padding=10)
        image_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Image label with fixed size
        self.image_label = ttk.Label(image_frame, text="Loading...")
        self.image_label.pack()
        
        # Right side - Controls and info
        right_frame = ttk.Frame(top_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Game State frame with scrollable tree
        info_frame = ttk.LabelFrame(right_frame, text="Variables (Locals & Globals)", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create treeview for variables
        tree_frame = ttk.Frame(info_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.variables_tree = ttk.Treeview(tree_frame, columns=('value',), show='tree headings')
        self.variables_tree.heading('#0', text='Variable')
        self.variables_tree.heading('value', text='Value')
        self.variables_tree.column('#0', width=200)
        self.variables_tree.column('value', width=300)
        
        # Scrollbars for the tree
        tree_v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.variables_tree.yview)
        tree_h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.variables_tree.xview)
        self.variables_tree.configure(yscrollcommand=tree_v_scrollbar.set, xscrollcommand=tree_h_scrollbar.set)
        
        self.variables_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree_h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind single-click to expand/collapse (more intuitive)
        self.variables_tree.bind('<Button-1>', self._on_tree_single_click)
        
        # Basic info label
        self.info_label = ttk.Label(
            info_frame, 
            text="Loading...", 
            font=("Courier", 9)
        )
        self.info_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Globals frame
        globals_frame = ttk.LabelFrame(right_frame, text="Global Variables", padding=10)
        globals_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Scrollable frame for globals
        globals_canvas = tk.Canvas(globals_frame, height=120)
        globals_scrollbar = ttk.Scrollbar(globals_frame, orient="vertical", command=globals_canvas.yview)
        self.globals_content = ttk.Frame(globals_canvas)
        
        self.globals_content.bind(
            "<Configure>",
            lambda e: globals_canvas.configure(scrollregion=globals_canvas.bbox("all"))
        )
        
        globals_canvas.create_window((0, 0), window=self.globals_content, anchor="nw")
        globals_canvas.configure(yscrollcommand=globals_scrollbar.set)
        
        globals_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        globals_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tracked Functions frame
        tracked_frame = ttk.LabelFrame(right_frame, text="Tracked Functions", padding=10)
        tracked_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Scrollable frame for tracked functions
        tracked_canvas = tk.Canvas(tracked_frame, height=80)
        tracked_scrollbar = ttk.Scrollbar(tracked_frame, orient="vertical", command=tracked_canvas.yview)
        self.tracked_content = ttk.Frame(tracked_canvas)
        
        self.tracked_content.bind(
            "<Configure>",
            lambda e: tracked_canvas.configure(scrollregion=tracked_canvas.bbox("all"))
        )
        
        tracked_canvas.create_window((0, 0), window=self.tracked_content, anchor="nw")
        tracked_canvas.configure(yscrollcommand=tracked_scrollbar.set)
        
        tracked_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tracked_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Sessions/Sliders frame (bottom)
        sessions_frame = ttk.LabelFrame(main_frame, text="Sessions & Branches", padding=10)
        sessions_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create scrollable frame for sliders
        sliders_canvas = tk.Canvas(sessions_frame, height=200)
        sliders_scrollbar = ttk.Scrollbar(sessions_frame, orient="vertical", command=sliders_canvas.yview)
        self.sliders_frame = ttk.Frame(sliders_canvas)
        
        self.sliders_frame.bind(
            "<Configure>",
            lambda e: sliders_canvas.configure(scrollregion=sliders_canvas.bbox("all"))
        )
        
        sliders_canvas.create_window((0, 0), window=self.sliders_frame, anchor="nw")
        sliders_canvas.configure(yscrollcommand=sliders_scrollbar.set)
        
        sliders_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sliders_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Controls frame (bottom)
        controls_frame = ttk.LabelFrame(main_frame, text="Controls", padding=10)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Buttons frame
        buttons_frame = ttk.Frame(controls_frame)
        buttons_frame.pack(fill=tk.X)
        
        # Replay buttons
        ttk.Button(buttons_frame, text="Replay All", command=self._replay_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Replay From Here", command=self._replay_from_here).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Refresh DB", command=self._refresh_database).pack(side=tk.LEFT, padx=(0, 5))
        
        # Transparency overlay controls
        transparency_frame = ttk.Frame(buttons_frame)
        transparency_frame.pack(side=tk.LEFT, padx=(20, 5))
        
        ttk.Label(transparency_frame, text="Transparency Overlay:").pack(side=tk.LEFT)
        
        # Create dropdown for transparency session selection
        transparency_options = ["None"] + [self.sessions_data[sid]['name'] for sid in self.sessions_data.keys()]
        self.transparency_dropdown = ttk.Combobox(
            transparency_frame, 
            textvariable=self.transparency_var,
            values=transparency_options,
            state="readonly",
            width=15
        )
        self.transparency_dropdown.pack(side=tk.LEFT, padx=(5, 0))
        self.transparency_dropdown.bind('<<ComboboxSelected>>', self._on_transparency_selection_changed)
        
        # Status label
        self.status_label = ttk.Label(buttons_frame, text="Ready", foreground="green")
        self.status_label.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Initialize sliders for all sessions
        self._create_session_sliders()
        
        # Initialize globals and tracked functions
        self._setup_globals_and_tracked()
        
        # Initialize display with first session's first frame
        if self.sessions_data:
            first_session_id = list(self.sessions_data.keys())[0]
            self._update_display(first_session_id, 0)
    
    def _create_session_sliders(self):
        """Create sliders for each session with branching visualization"""
        # Sort sessions to show parent sessions before child sessions
        sorted_sessions = self._get_sorted_sessions_for_display()
        
        for session_id in sorted_sessions:
            session_data = self.sessions_data[session_id]
            session_info = session_data['session']
            calls = session_data['calls']
            
            # Get relationship info
            rel = self.session_relationships.get(session_id, {})
            is_branch = rel.get('parent_session_id') is not None
            branch_point_index = rel.get('branch_point_index')
            
            # Create frame for this session with indentation for branches
            indent = 20 if is_branch else 0
            session_frame = ttk.LabelFrame(self.sliders_frame, text=f"{session_data['name']} ({len(calls)} frames)", padding=5)
            session_frame.pack(fill=tk.X, pady=2, padx=(indent, 0))
            
            # Session info with branch information
            info_text = f"Started: {session_info.start_time.strftime('%H:%M:%S')}"
            if session_info.description:
                info_text += f" - {session_info.description}"
            if is_branch:
                parent_id = rel['parent_session_id']
                parent_name = self.sessions_data[parent_id]['name'] if parent_id in self.sessions_data else f"Session {parent_id}"
                info_text += f" | Branches from {parent_name}"
                if branch_point_index is not None:
                    info_text += f" at frame {branch_point_index + 1}"
            
            info_label = ttk.Label(session_frame, text=info_text, font=("Arial", 9))
            info_label.pack(anchor=tk.W)
            
            # Slider container with proper alignment
            slider_container = ttk.Frame(session_frame)
            slider_container.pack(fill=tk.X, pady=(5, 0))
            
            # Calculate slider positioning for branching visualization
            if is_branch and branch_point_index is not None:
                # For branch sessions, create offset and reduced size slider
                parent_id = rel['parent_session_id']
                if parent_id in self.sessions_data:
                    parent_calls_count = len(self.sessions_data[parent_id]['calls'])
                    
                    # Calculate proportional offset and width
                    total_width = 400  # Base slider width
                    offset_ratio = branch_point_index / parent_calls_count if parent_calls_count > 0 else 0
                    width_ratio = len(calls) / parent_calls_count if parent_calls_count > 0 else 1
                    
                    offset_pixels = int(total_width * offset_ratio)
                    slider_width = int(total_width * width_ratio)
                    
                    # Add spacing frame for offset
                    if offset_pixels > 0:
                        spacing_frame = ttk.Frame(slider_container, width=offset_pixels)
                        spacing_frame.pack(side=tk.LEFT)
                        spacing_frame.pack_propagate(False)
                    
                    # Create slider frame
                    slider_frame = ttk.Frame(slider_container)
                    slider_frame.pack(side=tk.LEFT)
                    
                    ttk.Label(slider_frame, text="Frame:").pack(side=tk.LEFT)
                    
                    slider = tk.Scale(
                        slider_frame,
                        from_=0,
                        to=len(calls) - 1,
                        orient=tk.HORIZONTAL,
                        command=lambda value, sid=session_id: self._on_slider_change(sid, value),
                        length=max(slider_width, 100)  # Minimum width of 100
                    )
                    slider.pack(side=tk.LEFT, padx=(10, 0))
                else:
                    # Fallback to normal slider if parent not found
                    slider = self._create_normal_slider(slider_container, session_id, calls)
            else:
                # Normal full-width slider for main sessions
                slider = self._create_normal_slider(slider_container, session_id, calls)
            
            self.session_sliders[session_id] = {
                'frame': session_frame,
                'slider': slider,
                'info_label': info_label
            }
            
    def _get_sorted_sessions_for_display(self) -> List[int]:
        """Sort sessions to display parent sessions before child sessions"""
        sorted_sessions = []
        processed = set()
        
        # First add all main sessions (no parent)
        for session_id, rel in self.session_relationships.items():
            if not rel.get('parent_session_id'):
                sorted_sessions.append(session_id)
                processed.add(session_id)
        
        # Then add child sessions in order
        while len(processed) < len(self.sessions_data):
            added_in_iteration = False
            for session_id, rel in self.session_relationships.items():
                if session_id not in processed:
                    parent_id = rel.get('parent_session_id')
                    if parent_id is None or parent_id in processed:
                        sorted_sessions.append(session_id)
                        processed.add(session_id)
                        added_in_iteration = True
            
            if not added_in_iteration:
                # Add any remaining sessions to avoid infinite loop
                for session_id in self.sessions_data:
                    if session_id not in processed:
                        sorted_sessions.append(session_id)
                        processed.add(session_id)
                break
        
        return sorted_sessions
        
    def _create_normal_slider(self, parent_frame: ttk.Frame, session_id: int, calls: List[Any]):
        """Create a normal full-width slider"""
        slider_frame = ttk.Frame(parent_frame)
        slider_frame.pack(fill=tk.X)
        
        ttk.Label(slider_frame, text="Frame:").pack(side=tk.LEFT)
        
        slider = tk.Scale(
            slider_frame,
            from_=0,
            to=len(calls) - 1,
            orient=tk.HORIZONTAL,
            command=lambda value, sid=session_id: self._on_slider_change(sid, value),
            length=400
        )
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        return slider
    
    def _update_variables_display(self, call_data: Dict[str, Any]):
        """Update the variables tree display"""
        if not hasattr(self, 'variables_tree') or not self.variables_tree:
            return
            
        # Save expanded state before clearing
        self._save_tree_expanded_state()
            
        # Clear existing items
        for item in self.variables_tree.get_children():
            self.variables_tree.delete(item)
        
        variables = call_data.get('variables', {})
        session_id = call_data.get('session_id')
        call_index = call_data.get('call_index', 0)
        
        # Update basic info
        if self.info_label and session_id in self.sessions_data:
            session_name = self.sessions_data[session_id]['name']
            total_calls = len(self.sessions_data[session_id]['calls'])
            info_text = f"{session_name} | Frame {call_index + 1}/{total_calls} | "
            info_text += f"ID: {call_data.get('call_id', 'N/A')} | "
            timestamp = call_data.get('timestamp')
            if timestamp:
                info_text += f"Time: {timestamp.strftime('%H:%M:%S.%f')[:-3]}"
            self.info_label.configure(text=info_text)
        
        # Add locals section
        locals_vars = variables.get('locals', {})
        if locals_vars and self.variables_tree:
            locals_root = self.variables_tree.insert('', 'end', text='Locals', values=('',), open=True)
            for name, value in locals_vars.items():
                self._add_variable_to_tree(locals_root, name, value)
        
        # Add globals section
        globals_vars = variables.get('globals', {})
        if globals_vars and self.variables_tree:
            globals_root = self.variables_tree.insert('', 'end', text='Globals', values=('',), open=True)
            for name, value in globals_vars.items():
                self._add_variable_to_tree(globals_root, name, value)
        
        # Restore expanded state after rebuilding
        self._restore_tree_expanded_state()
    
    def _add_variable_to_tree(self, parent, name: str, value: Any, max_depth: int = 3, current_depth: int = 0):
        """Recursively add a variable and its sub-fields to the tree"""
        if not self.variables_tree:
            return
            
        if current_depth >= max_depth:
            self.variables_tree.insert(parent, 'end', text=name, values=(f'{type(value).__name__} (max depth reached)',))
            return
            
        # Format the value for display
        value_str = self._format_value_for_display(value)
        
        # Insert the main item
        item = self.variables_tree.insert(parent, 'end', text=name, values=(value_str,))
        
        # Add sub-fields if the value has interesting attributes
        if hasattr(value, '__dict__') and value.__dict__:
            for attr_name, attr_value in value.__dict__.items():
                if not attr_name.startswith('_'):  # Skip private attributes
                    self._add_variable_to_tree(item, attr_name, attr_value, max_depth, current_depth + 1)
        elif isinstance(value, dict) and len(value) < 20:  # Limit dict expansion
            for key, val in value.items():
                key_str = str(key)
                if len(key_str) < 50:  # Limit key length
                    self._add_variable_to_tree(item, f'[{key_str}]', val, max_depth, current_depth + 1)
        elif isinstance(value, (list, tuple)) and len(value) < 20:  # Limit list expansion
            for i, val in enumerate(value):
                self._add_variable_to_tree(item, f'[{i}]', val, max_depth, current_depth + 1)
    
    def _format_value_for_display(self, value: Any) -> str:
        """Format a value for display in the tree"""
        try:
            if value is None:
                return 'None'
            elif isinstance(value, str):
                # Truncate long strings
                if len(value) > 100:
                    return f'"{value[:97]}..."'
                return f'"{value}"'
            elif isinstance(value, (int, float, bool)):
                return str(value)
            elif isinstance(value, (list, tuple)):
                return f'{type(value).__name__}[{len(value)}]'
            elif isinstance(value, dict):
                return f'dict[{len(value)}]'
            elif hasattr(value, '__dict__'):
                # Custom object
                attrs = [k for k in value.__dict__.keys() if not k.startswith('_')]
                return f'{type(value).__name__}({len(attrs)} attrs)'
            else:
                return f'{type(value).__name__}: {str(value)[:50]}'
        except Exception:
            return f'{type(value).__name__} (display error)'
    
    def _save_tree_expanded_state(self):
        """Save the current expanded state of tree items"""
        if not self.variables_tree:
            return
        
        self.expanded_items.clear()
        tree = self.variables_tree  # Type hint helper
        
        def collect_expanded(item):
            # Get the path to this item (text of all parents + this item)
            path = []
            current = item
            while current:
                path.insert(0, tree.item(current, 'text'))  # type: ignore
                current = tree.parent(current)  # type: ignore
            
            item_path = ' > '.join(path)
            
            # If this item is expanded, save its path
            if tree.item(item, 'open'):  # type: ignore
                self.expanded_items.add(item_path)
            
            # Recursively check children
            for child in tree.get_children(item):  # type: ignore
                collect_expanded(child)
        
        # Start from root items
        for root_item in tree.get_children():  # type: ignore
            collect_expanded(root_item)
    
    def _restore_tree_expanded_state(self):
        """Restore the expanded state of tree items"""
        if not self.variables_tree or not self.expanded_items:
            return
        
        tree = self.variables_tree  # Type hint helper
        
        def restore_expanded(item):
            # Get the path to this item
            path = []
            current = item
            while current:
                path.insert(0, tree.item(current, 'text'))  # type: ignore
                current = tree.parent(current)  # type: ignore
            
            item_path = ' > '.join(path)
            
            # If this item should be expanded, expand it
            if item_path in self.expanded_items:
                tree.item(item, open=True)  # type: ignore
            
            # Recursively restore children
            for child in tree.get_children(item):  # type: ignore
                restore_expanded(child)
        
        # Start from root items
        for root_item in tree.get_children():  # type: ignore
            restore_expanded(root_item)
    
    def _on_tree_single_click(self, event):
        """Handle single-click on tree items to toggle expansion"""
        if not self.variables_tree:
            return
        
        # Get the item that was clicked
        item = self.variables_tree.identify('item', event.x, event.y)
        if item:
            # Toggle the item's open/closed state
            if self.variables_tree.item(item, 'open'):
                self.variables_tree.item(item, open=False)
            else:
                self.variables_tree.item(item, open=True)
    
    def _on_tree_double_click(self, event):
        """Handle double-click on tree items - do nothing to prevent interference"""
        # We handle expansion on single-click now, so double-click does nothing
        pass

    def _setup_globals_and_tracked(self):
        """Setup the globals and tracked functions sections"""
        if not self.sessions_data:
            return
            
        # Get all unique global variables from all calls across all sessions
        all_globals = set()
        all_tracked_functions = set()
        
        for session_data in self.sessions_data.values():
            for call in session_data['calls']:
                if call.globals_refs:
                    all_globals.update(call.globals_refs.keys())
        
        # Get tracked functions from the database using child calls
        # Tracked functions are stored as child function calls in the database
        for session_data in self.sessions_data.values():
            for call in session_data['calls']:
                # Get child calls (tracked functions) for each display_game call
                child_calls = call.get_child_calls(self.session)
                for child_call in child_calls:
                    all_tracked_functions.add(child_call.function)
            
        
        # Filter out system variables
        filtered_globals = [g for g in all_globals if not g.startswith('__')]
        
        # Setup globals checkboxes
        for i, global_var in enumerate(sorted(filtered_globals)):
            var = tk.BooleanVar(value=True)  # Default to checked (include in replay)
            self.global_vars[global_var] = var
            
            if self.globals_content:
                cb = ttk.Checkbutton(
                    self.globals_content, 
                    text=global_var, 
                    variable=var
                )
                cb.grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
        
        # Setup tracked functions checkboxes
        for i, func_name in enumerate(sorted(all_tracked_functions)):
            var = tk.BooleanVar(value=False)  # Default to unchecked (don't mock)
            self.tracked_vars[func_name] = var
            
            if self.tracked_content:
                cb = ttk.Checkbutton(
                    self.tracked_content, 
                    text=func_name, 
                    variable=var
                )
                cb.grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
    
    def _get_ignored_globals(self) -> List[str]:
        """Get list of global variables that should be ignored (unchecked)"""
        return [name for name, var in self.global_vars.items() if not var.get()]
    
    def _get_mocked_functions(self) -> List[str]:
        """Get list of functions that should be mocked (checked)"""
        return [name for name, var in self.tracked_vars.items() if var.get()]
    
    def _replay_all(self):
        """Replay from the beginning of the current session"""
        if self.current_session_id is None or self.current_session_id not in self.sessions_data:
            print("No current session to replay")
            return
            
        # Get the first call ID from current session
        calls = self.sessions_data[self.current_session_id]['calls']
        if not calls:
            print("No function calls to replay")
            return
            
        first_call = calls[0]
        first_call_id = first_call.id
        
        ignored_globals = self._get_ignored_globals()
        mocked_functions = self._get_mocked_functions()
        
        session_name = self.sessions_data[self.current_session_id]['name']
        print(f"Starting replay from beginning of {session_name} (Call ID: {first_call_id})")
        print(f"Ignored globals: {ignored_globals}")
        print(f"Mocked functions: {mocked_functions}")
        
        if self.status_label:
            self.status_label.configure(text=f"Replaying {session_name}...", foreground="orange")
            self.root.update() if self.root else None
        
        try:
            # Initialize monitoring for the replay
            monitor = monitoringpy.init_monitoring(db_path=self.db_path, custom_picklers=["pygame"])
            session_id = monitoringpy.start_session(f"Replay of {session_name}")
            
            if session_id:
                print(f"Started new monitoring session: {session_id}")
                
                # Perform the replay
                new_branch_id = replay_session_sequence(
                    first_call_id, 
                    self.db_path, 
                    ignore_globals=ignored_globals,
                    mock_functions=mocked_functions
                )
                
                if new_branch_id:
                    print(f"Replay successful! New branch created with ID: {new_branch_id}")
                    if self.status_label:
                        self.status_label.configure(text=f"Replay successful! Branch: {new_branch_id}", foreground="green")
                    # Close pygame screen after successful replay
                    try:
                        import pygame
                        pygame.quit()
                        print("Pygame screen closed after replay")
                    except Exception as pygame_err:
                        print(f"Warning: Could not close pygame screen: {pygame_err}")
                    # Refresh the database to see new calls
                    self._refresh_database()
                else:
                    print("Replay failed - no new branch created")
                    if self.status_label:
                        self.status_label.configure(text="Replay failed", foreground="red")
                    
                monitoringpy.end_session()
            else:
                print("Failed to start monitoring session for replay")
                if self.status_label:
                    self.status_label.configure(text="Failed to start session", foreground="red")
                
        except Exception as e:
            print(f"Error during replay: {e}")
            if self.status_label:
                self.status_label.configure(text=f"Error: {str(e)[:50]}", foreground="red")
            import traceback
            traceback.print_exc()
    
    def _replay_from_here(self):
        """Replay from the current frame in the current session"""
        if self.current_session_id is None or self.current_session_id not in self.sessions_data:
            print("No current session to replay from")
            return
            
        calls = self.sessions_data[self.current_session_id]['calls']
        if self.current_call_index >= len(calls):
            print("No valid function call to replay from")
            return
            
        # Get the current call ID
        current_call = calls[self.current_call_index]
        current_call_id = current_call.id
        
        ignored_globals = self._get_ignored_globals()
        mocked_functions = self._get_mocked_functions()
        
        session_name = self.sessions_data[self.current_session_id]['name']
        print(f"Starting replay from {session_name} frame {self.current_call_index + 1} (Call ID: {current_call_id})")
        print(f"Ignored globals: {ignored_globals}")
        print(f"Mocked functions: {mocked_functions}")
        
        if self.status_label:
            self.status_label.configure(text=f"Replaying from frame {self.current_call_index + 1}...", foreground="orange")
            self.root.update() if self.root else None
        
        try:
            # Initialize monitoring for the replay
            monitor = monitoringpy.init_monitoring(db_path=self.db_path, custom_picklers=["pygame"])
            session_id = monitoringpy.start_session(f"Replay from {session_name} Frame {self.current_call_index + 1}")
            
            if session_id:
                print(f"Started new monitoring session: {session_id}")
                
                # Perform the replay
                new_branch_id = replay_session_sequence(
                    current_call_id, 
                    self.db_path, 
                    ignore_globals=ignored_globals,
                    mock_functions=mocked_functions
                )
                
                if new_branch_id:
                    print(f"Replay successful! New branch created with ID: {new_branch_id}")
                    if self.status_label:
                        self.status_label.configure(text=f"Replay successful! Branch: {new_branch_id}", foreground="green")
                    # Close pygame screen after successful replay
                    try:
                        import pygame
                        pygame.quit()
                        print("Pygame screen closed after replay")
                    except Exception as pygame_err:
                        print(f"Warning: Could not close pygame screen: {pygame_err}")
                    # Refresh the database to see new calls
                    self._refresh_database()
                else:
                    print("Replay failed - no new branch created")
                    if self.status_label:
                        self.status_label.configure(text="Replay failed", foreground="red")
                    
                monitoringpy.end_session()
            else:
                print("Failed to start monitoring session for replay")
                if self.status_label:
                    self.status_label.configure(text="Failed to start session", foreground="red")
                
        except Exception as e:
            print(f"Error during replay: {e}")
            if self.status_label:
                self.status_label.configure(text=f"Error: {str(e)[:50]}", foreground="red")
            import traceback
            traceback.print_exc()
    
    def _refresh_database(self):
        """Refresh the database connection to see new data"""
        try:
            # Close current session
            if self.session:
                self.session.close()
            
            # Store current state
            old_session_count = len(self.sessions_data)
            
            # Reinitialize database connection
            Session = init_db(self.db_path)
            self.session = Session()
            self.object_manager = ObjectManager(self.session)
            
            # Clear existing session sliders
            for session_id in list(self.session_sliders.keys()):
                self.session_sliders[session_id]['frame'].destroy()
                del self.session_sliders[session_id]
            
            # Reload all sessions
            self.sessions_data.clear()
            sessions = self.session.query(MonitoringSession).order_by(MonitoringSession.start_time).all()
            
            for session in sessions:
                display_game_calls = self.session.query(FunctionCall).filter(
                    FunctionCall.session_id == session.id,
                    FunctionCall.function == 'display_game'
                ).order_by(FunctionCall.order_in_session).all()
                
                if display_game_calls:
                    self.sessions_data[session.id] = {
                        'session': session,
                        'calls': display_game_calls,
                        'name': session.name or f"Session {session.id}",
                        'start_time': session.start_time
                    }
            
            new_session_count = len(self.sessions_data)
            print(f"Database refreshed: {old_session_count} -> {new_session_count} sessions")
            
            # Recreate session sliders
            self._create_session_sliders()
            
            # Refresh globals and tracked functions
            self._refresh_globals_and_tracked()
            
            # Re-analyze session relationships
            self._analyze_session_relationships()
            
            # Update transparency dropdown options
            self._update_transparency_dropdown()
            
            if self.status_label:
                self.status_label.configure(text=f"Refreshed - {new_session_count} sessions loaded", foreground="green")
                
        except Exception as e:
            print(f"Error refreshing database: {e}")
            if self.status_label:
                self.status_label.configure(text=f"Refresh error: {str(e)[:30]}", foreground="red")
            import traceback
            traceback.print_exc()
    
    def _refresh_globals_and_tracked(self):
        """Refresh the globals and tracked functions sections"""
        try:
            # Clear existing checkboxes
            if self.globals_content:
                for widget in self.globals_content.winfo_children():
                    widget.destroy()
            if self.tracked_content:
                for widget in self.tracked_content.winfo_children():
                    widget.destroy()
            
            # Reset variables
            self.global_vars.clear()
            self.tracked_vars.clear()
            
            # Recreate the sections
            self._setup_globals_and_tracked()
            
        except Exception as e:
            print(f"Error refreshing globals and tracked: {e}")
            
    def run(self):
        """Run the replay interface"""
        self._create_ui()
        if self.root:
            self.root.mainloop()
        
        # Clean up
        if self.session:
            self.session.close()

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple Flappy Bird Replay - Multi-Branch")
    parser.add_argument("db_path", help="Path to the flappy.db database file")
    args = parser.parse_args()
    
    # Create and run the replay interface
    replay = FlappyReplay(args.db_path)
    replay.run()

if __name__ == "__main__":
    main() 