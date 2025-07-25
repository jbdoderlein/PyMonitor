#!/usr/bin/env python3
"""
Game Explorer - Multi-Branch Replay Tool

A Tkinter-based tool to replay pygame game execution with multiple sliders
for different branches and proper tracked function display.
"""
import base64
import datetime
import io
import os
import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, TypedDict

from PIL import Image, ImageTk

from monitoringpy.core import FunctionCall, MonitoringSession, ObjectManager, init_db
from monitoringpy.core.monitoring import init_monitoring
from monitoringpy.core.reanimation import replay_session_sequence
from monitoringpy.core.session import end_session, start_session

# Import chlorophyll for code editor
try:
    from chlorophyll import CodeView
    CHLOROPHYLL_AVAILABLE = True
except ImportError:
    CHLOROPHYLL_AVAILABLE = False
    print("Warning: chlorophyll not available. Code editor will be disabled.")

import pygame

HIDDEN_PYGAME = False

# Since we're now inside the monitoringpy module, we can import directly

class SessionData(TypedDict):
    session: MonitoringSession
    calls: list[FunctionCall]
    name: str
    start_time: datetime.datetime

class GameExplorer:
    def __init__(self, db_path: str, tracked_function: str = 'display_game',
                 image_metadata_key: str = 'image', window_title: str = "Game Explorer - Multi-Branch",
                 window_geometry: str = "1400x1200", image_scale: float = 0.8):
        self.db_path = db_path
        self.tracked_function = tracked_function
        self.image_metadata_key = image_metadata_key
        self.window_title = window_title
        self.window_geometry = window_geometry
        self.image_scale = image_scale

        # Initialize pygame for image regeneration
        pygame.init()

        # Default screen size (can be inferred from drawing calls)
        self.screen_width = 500
        self.screen_height = 700

        self.session = None
        self.object_manager = None
        self.sessions_data: dict[int, SessionData] = {}  # Dict[session_id, SessionData] containing session info and calls
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

        # Code editor
        self.code_editor = None
        self.code_editor_frame = None
        self.current_source_file = None
        self.current_highlighted_line = None
        self.file_modified = False
        self.save_button = None

        # Checkbox variables for globals and tracked functions
        self.global_vars = {}  # Dict[str, tk.BooleanVar]
        self.tracked_vars = {}  # Dict[str, tk.BooleanVar]

        # Slider widgets for each session
        self.session_sliders = {}  # Dict[session_id, Dict] containing slider widgets

        # Tree state management
        self.expanded_items = set()  # Track which tree items are expanded

        # Branching and comparison overlay features
        self.session_relationships = {}  # Dict[session_id, Dict] containing parent/child relationships
        self.comparison_session_id = None  # Session ID to compare with (for previous variables)
        self.comparison_checkboxes = {}  # Dict[session_id, tk.BooleanVar] for comparison checkboxes

        # Stroboscopic effect features
        self.stroboscopic_session_id = None  # Session ID for stroboscopic phantom effect
        self.stroboscopic_checkboxes = {}  # Dict[session_id, tk.BooleanVar] for stroboscopic checkboxes
        self.stroboscopic_control_panels = {}  # Dict[session_id, LabelFrame] for stroboscopic control panels

        # Stroboscopic settings
        self.stroboscopic_ghost_count = {}  # Dict[session_id, tk.IntVar] - number of ghost frames
        self.stroboscopic_offset = {}  # Dict[session_id, tk.IntVar] - offset between ghost frames
        self.stroboscopic_x_offset = {}  # Dict[session_id, tk.IntVar] - x offset for drawing frames
        self.stroboscopic_y_offset = {}  # Dict[session_id, tk.IntVar] - y offset for drawing frames

        self.in_memory_db = True

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

        # Load tracked function calls for each session
        for session in sessions:
            tracked_calls = self.session.query(FunctionCall).filter(
                FunctionCall.session_id == session.id,
                FunctionCall.function == self.tracked_function
            ).order_by(FunctionCall.order_in_session).all()

            if tracked_calls:
                self.sessions_data[session.id] = {
                    'session': session,
                    'calls': tracked_calls,
                    'name': session.name or f"Session {session.id}",
                    'start_time': session.start_time
                }

        if not self.sessions_data:
            print(f"Error: No {self.tracked_function} function calls found in any session")
            sys.exit(1)

        # Set the first session as current
        self.current_session_id = list(self.sessions_data.keys())[0]

        # Analyze branching relationships
        self._analyze_session_relationships()

        print(f"Found {len(self.sessions_data)} sessions with {self.tracked_function} calls")
        for session_id, data in self.sessions_data.items():
            print(f"  Session {session_id}: {len(data['calls'])} calls - {data['name']}")
            if session_id in self.session_relationships:
                rel = self.session_relationships[session_id]
                if rel['parent_session_id']:
                    print(f"    -> Branches from session {rel['parent_session_id']} at call {rel['branch_point_call_id']}")
                if rel['child_sessions']:
                    print(f"    -> Has child branches: {rel['child_sessions']}")

    def _regenerate_image_from_drawing_calls(self, session_id: int, call_index: int) -> str | None:
        """Regenerate image by replaying drawing function calls using pygame"""
        if session_id not in self.sessions_data or self.session is None:
            return None

        calls = self.sessions_data[session_id]['calls']
        if call_index < 0 or call_index >= len(calls):
            return None

        call = calls[call_index]

        # Get child calls (drawing operations)
        child_calls = call.get_child_calls(self.session)
        if not child_calls:
            return None

        # Create a pygame surface
        surface = pygame.Surface((self.screen_width, self.screen_height))

        # Map of function names to their handlers
        drawing_handlers = {
            'fill': self._handle_fill,
            'blit': self._handle_blit,
            'draw_rect': self._handle_draw_rect,
            'pygame.draw.rect': self._handle_pygame_draw_rect,
        }

        # Replay drawing operations in order
        for child_call in child_calls:
            func_name = child_call.function
            if func_name in drawing_handlers:
                try:
                    # Get the function arguments from the call
                    args_dict = self._extract_function_args(child_call)
                    # Call the appropriate handler
                    drawing_handlers[func_name](surface, args_dict)
                except Exception as e:
                    print(f"Error replaying drawing call {func_name}: {e}")
                    continue

        # Convert pygame surface to base64 image
        return self._surface_to_base64(surface)

    def _extract_function_args(self, child_call: FunctionCall) -> dict[str, Any]:
        """Extract function arguments from a child call as a dictionary of parameter name -> value"""
        args_dict = {}

        # Get arguments from locals_refs - they are stored by parameter name
        if child_call.locals_refs and self.object_manager:
            for var_name, ref in child_call.locals_refs.items():
                try:
                    value = self.object_manager.rehydrate(ref)
                    args_dict[var_name] = value
                except Exception as e:
                    print(f"Error extracting argument {var_name}: {e}")

        return args_dict

    def _handle_fill(self, surface: pygame.Surface, args_dict: dict[str, Any]):
        """Handle fill() drawing operation"""
        # fill() expects a color argument
        if 'args' in args_dict and args_dict['args']:
            color = args_dict['args'][0]
            surface.fill(color)
        elif len(args_dict) >= 1:
            # Try to get color from first non-self argument
            for key, value in args_dict.items():
                if key != 'self' and key != 'kwargs':
                    color = value
                    surface.fill(color)
                    break

    def _handle_blit(self, surface: pygame.Surface, args_dict: dict[str, Any]):
        """Handle blit() drawing operation"""
        # blit() expects (source_surface, dest)
        if 'args' in args_dict and args_dict['args'] and len(args_dict['args']) >= 2:
            source_surface = args_dict['args'][0]
            dest = args_dict['args'][1]
            if isinstance(source_surface, pygame.Surface):
                surface.blit(source_surface, dest)

    def _handle_draw_rect(self, surface: pygame.Surface, args_dict: dict[str, Any]):
        """Handle draw_rect() drawing operation"""
        # draw_rect() expects (surface, color, rect, **kwargs)
        #target_surface = args_dict.get('surface')
        color = args_dict.get('color')
        rect = args_dict.get('rect')

        if color and rect:
            # Extract additional parameters
            width = args_dict.get('width', 0)
            border_radius = args_dict.get('border_radius', 0)

            # Draw the rectangle
            pygame.draw.rect(surface, color, rect, width=width, border_radius=border_radius)

    def _handle_pygame_draw_rect(self, surface: pygame.Surface, args_dict: dict[str, Any]):
        """Handle pygame.draw.rect() drawing operation"""
        # Same as draw_rect but with potentially different argument structure
        self._handle_draw_rect(surface, args_dict)

    def _surface_to_base64(self, surface: pygame.Surface) -> str | None:
        """Convert pygame surface to base64 encoded image"""
        try:
            # Save surface to BytesIO buffer
            buffer = io.BytesIO()
            pygame.image.save(surface, buffer, "PNG")
            buffer.seek(0)

            # Encode as base64
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"Error converting surface to base64: {e}")
            return None

    def _get_call_data(self, session_id: int, call_index: int) -> dict[str, Any]:
        """Get data for a specific function call in a session"""
        if session_id not in self.sessions_data:
            return {}

        calls = self.sessions_data[session_id]['calls']
        if call_index < 0 or call_index >= len(calls):
            return {}

        call = calls[call_index]

        # Try to get the image from call metadata first (backward compatibility)
        image_data = None
        if call.call_metadata and self.image_metadata_key in call.call_metadata:
            image_data = call.call_metadata[self.image_metadata_key]
        else:
            # Regenerate image from drawing calls
            image_data = self._regenerate_image_from_drawing_calls(session_id, call_index)

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

    def _get_comparison_call_data(self, current_session_id: int, current_call_index: int) -> dict[str, Any] | None:
        """Get call data from comparison session that corresponds to the current position"""
        if not self.comparison_session_id or self.comparison_session_id not in self.sessions_data:
            return None

        # Check if transparency session is a child of current session
        transparency_rel = self.session_relationships.get(self.comparison_session_id, {})
        if transparency_rel.get('parent_session_id') == current_session_id:
            # Transparency session branches from current session
            branch_point_index = transparency_rel.get('branch_point_index')
            if branch_point_index is not None and current_call_index >= branch_point_index:
                # Current position is at or after the branch point
                # Map to corresponding position in transparency session
                offset_in_transparency = current_call_index - branch_point_index
                transparency_calls = self.sessions_data[self.comparison_session_id]['calls']
                if offset_in_transparency < len(transparency_calls):
                    return self._get_call_data(self.comparison_session_id, offset_in_transparency)

        # Check if current session is a child of transparency session
        current_rel = self.session_relationships.get(current_session_id, {})
        if current_rel.get('parent_session_id') == self.comparison_session_id:
            # Current session branches from transparency session
            branch_point_index = current_rel.get('branch_point_index')
            if branch_point_index is not None:
                # Map current position back to transparency session
                transparency_index = branch_point_index + current_call_index
                transparency_calls = self.sessions_data[self.comparison_session_id]['calls']
                if transparency_index < len(transparency_calls):
                    return self._get_call_data(self.comparison_session_id, transparency_index)

        return None

    def _get_stroboscopic_frames(self, session_id: int, current_call_index: int) -> list[str]:
        """Get image data for stroboscopic phantom effect (multiple frames for overlay)"""
        if session_id not in self.sessions_data:
            return []

        calls = self.sessions_data[session_id]['calls']
        stroboscopic_frames = []

        # Get stroboscopic settings for this session
        ghost_count = self.stroboscopic_ghost_count.get(session_id, tk.IntVar(value=4)).get()
        offset = self.stroboscopic_offset.get(session_id, tk.IntVar(value=2)).get()

        # Only show future frames (removing start_pos option)
        start_index = current_call_index + 1
        end_index = min(len(calls), current_call_index + (ghost_count * offset) + 1)

        # Collect frames with the specified offset
        frame_indices = []
        for i in range(start_index, end_index, offset):
            frame_indices.append(i)

        # Limit to the specified number of ghost frames
        frame_indices = frame_indices[:ghost_count]

        # Get the image data for selected frames
        for i in frame_indices:
            if 0 <= i < len(calls):
                frame_data = self._get_call_data(session_id, i)
                if frame_data.get('image_data'):
                    stroboscopic_frames.append(frame_data['image_data'])

        return stroboscopic_frames

    def _decode_image(self, image_data: str, transparency_image_data: str | None = None, stroboscopic_image_data_list: list[str] | None = None) -> ImageTk.PhotoImage | None:
        """Decode base64 image data to PhotoImage, optionally blending with transparency overlay and stroboscopic phantom effect"""
        try:
            # Decode base64 data
            image_bytes = base64.b64decode(image_data)

            # Create PIL Image
            pil_image = Image.open(io.BytesIO(image_bytes))

            # Resize image based on scale factor
            original_width, original_height = pil_image.size
            new_width = int(original_width * self.image_scale)
            new_height = int(original_height * self.image_scale)
            pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert to RGB for blending operations
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')

            # If stroboscopic phantom effect is enabled, blend multiple frames with offsets
            if stroboscopic_image_data_list:
                try:
                    # Get the current session and stroboscopic settings
                    current_session = self.current_session_id
                    if current_session and current_session in self.stroboscopic_x_offset:
                        x_offset = self.stroboscopic_x_offset[current_session].get()
                        y_offset = self.stroboscopic_y_offset[current_session].get()
                    else:
                        x_offset = 5
                        y_offset = 5

                    # Create a larger canvas to accommodate offsets
                    max_offset_x = abs(x_offset * len(stroboscopic_image_data_list))
                    max_offset_y = abs(y_offset * len(stroboscopic_image_data_list))
                    canvas_width = new_width + max_offset_x
                    canvas_height = new_height + max_offset_y

                    # Create a new canvas image
                    canvas = Image.new('RGB', (canvas_width, canvas_height), (0, 0, 0))

                    # Paste the main image at the center
                    main_x = max_offset_x // 2
                    main_y = max_offset_y // 2
                    canvas.paste(pil_image, (main_x, main_y))

                    # Add phantom frames with progressive offsets
                    base_opacity = 0.3  # Higher opacity for better visibility

                    for i, phantom_data in enumerate(stroboscopic_image_data_list):
                        try:
                            # Decode phantom frame
                            phantom_bytes = base64.b64decode(phantom_data)
                            phantom_image = Image.open(io.BytesIO(phantom_bytes))

                            # Resize to match main image
                            phantom_image = phantom_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                            # Convert to RGB
                            if phantom_image.mode != 'RGB':
                                phantom_image = phantom_image.convert('RGB')

                            # Calculate position with progressive offset
                            offset_x = main_x + (i + 1) * x_offset
                            offset_y = main_y + (i + 1) * y_offset

                            # Ensure we don't go out of bounds
                            if 0 <= offset_x <= canvas_width - new_width and 0 <= offset_y <= canvas_height - new_height:
                                # Calculate opacity - farther frames are more transparent
                                opacity = base_opacity * (1.0 - (i / len(stroboscopic_image_data_list)) * 0.5)

                                # Create a temporary canvas for blending
                                temp_canvas = canvas.copy()
                                temp_canvas.paste(phantom_image, (offset_x, offset_y))

                                # Blend with the main canvas
                                canvas = Image.blend(canvas, temp_canvas, opacity)

                        except Exception as e:
                            print(f"Error blending phantom frame {i}: {e}")
                            continue

                    # Crop back to original size centered on the main image
                    crop_x = main_x
                    crop_y = main_y
                    pil_image = canvas.crop((crop_x, crop_y, crop_x + new_width, crop_y + new_height))

                except Exception as e:
                    print(f"Error processing stroboscopic frames: {e}")
                    # Continue with just the main image

            # If transparency overlay is provided, blend the images
            if transparency_image_data:
                try:
                    # Decode transparency image
                    transparency_bytes = base64.b64decode(transparency_image_data)
                    transparency_image = Image.open(io.BytesIO(transparency_bytes))

                    # Resize transparency image to match main image
                    transparency_image = transparency_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    # Convert to RGB
                    if transparency_image.mode != 'RGB':
                        transparency_image = transparency_image.convert('RGB')

                    # Use PIL's blend with a lower alpha to reduce darkening
                    # 0.3 gives a subtle overlay without too much darkening
                    pil_image = Image.blend(pil_image, transparency_image, 0.3)

                except Exception as e:
                    print(f"Error blending transparency image: {e}")
                    # Continue with just the main image

            # Convert to PhotoImage for Tkinter
            return ImageTk.PhotoImage(pil_image)
        except Exception as e:
            print(f"Error decoding image: {e}")
            return None

    def _load_source_code(self, file_path: str, highlight_line: int | None = None):
        """Load source code from file into the code editor and optionally highlight a line"""
        if not self.code_editor:
            return

        try:
            # Clear previous content
            self.code_editor.delete('1.0', tk.END)

            # Clear previous highlighting
            if hasattr(self.code_editor, 'tag_delete'):
                self.code_editor.tag_delete('highlight_line')

            if file_path and os.path.exists(file_path):
                with open(file_path, encoding='utf-8') as f:
                    content = f.read()

                # Insert the content
                self.code_editor.insert('1.0', content)

                # Highlight the current line if specified
                if highlight_line is not None:
                    self._highlight_line(highlight_line)

                # Update the current file reference
                self.current_source_file = file_path

                # Reset modification status
                self.file_modified = False
                self._update_save_button_state()
                self._update_code_editor_title()
            else:
                # File not found, show a message
                self.code_editor.insert('1.0', f"Source file not found: {file_path or 'Unknown'}")
                self.current_source_file = None
                self.file_modified = False
                self._update_save_button_state()
                self._update_code_editor_title()

        except Exception as e:
            print(f"Error loading source code from {file_path}: {e}")
            self.code_editor.insert('1.0', f"Error loading source code: {e}")
            self.current_source_file = None
            self.file_modified = False
            self._update_save_button_state()
            self._update_code_editor_title()

    def _highlight_line(self, line_number: int):
        """Highlight a specific line in the code editor"""
        if not self.code_editor:
            return

        try:
            # Remove previous highlighting
            if hasattr(self.code_editor, 'tag_delete'):
                self.code_editor.tag_delete('highlight_line')

            # Create highlight tag if it doesn't exist
            if hasattr(self.code_editor, 'tag_config'):
                self.code_editor.tag_config('highlight_line', background='#ffff88', relief='raised')

            # Calculate the start and end indices for the line
            start_index = f"{line_number}.0"
            end_index = f"{line_number}.end"

            # Add the highlight tag to the line
            if hasattr(self.code_editor, 'tag_add'):
                self.code_editor.tag_add('highlight_line', start_index, end_index)

            # Scroll to make the highlighted line visible
            if hasattr(self.code_editor, 'see'):
                self.code_editor.see(start_index)

            # Update the current highlighted line reference
            self.current_highlighted_line = line_number

        except Exception as e:
            print(f"Error highlighting line {line_number}: {e}")

    def _update_code_editor(self, call_data: dict[str, Any]):
        """Update the code editor with source code from the current function call"""
        if not call_data:
            return

        session_id = call_data.get('session_id')
        call_index = call_data.get('call_index', 0)

        if session_id is None or session_id not in self.sessions_data:
            return

        # Ensure call_index is an integer
        if call_index is None:
            call_index = 0
        try:
            call_index = int(call_index)
        except (ValueError, TypeError):
            call_index = 0

        calls = self.sessions_data[session_id]['calls']
        if call_index >= len(calls):
            return

        call = calls[call_index]

        # Try to get source file path and line number
        file_path = call.file
        line_number = call.line

        # If we don't have a direct file path, try to get it from code definition
        if not file_path and call.code_definition_id and self.session:
            try:
                from monitoringpy.core.models import CodeDefinition
                code_def = self.session.query(CodeDefinition).filter(
                    CodeDefinition.id == call.code_definition_id
                ).first()

                if code_def:
                    # Use the module path as file path (may need conversion)
                    module_path = code_def.module_path
                    if module_path and not module_path.endswith('.py'):
                        # Try to find the actual file
                        possible_paths = [
                            module_path + '.py',
                            module_path.replace('.', '/') + '.py',
                            module_path.replace('.', os.sep) + '.py'
                        ]
                        for path in possible_paths:
                            if os.path.exists(path):
                                file_path = path
                                break
                    else:
                        file_path = module_path

                    # Use the first line number from code definition if available
                    if code_def.first_line_no:
                        line_number = code_def.first_line_no

            except Exception as e:
                print(f"Error getting code definition: {e}")

        # Load and display the source code (only if we have a valid file path)
        if file_path and file_path != self.current_source_file:
            self._load_source_code(file_path, line_number)
        elif file_path and line_number and line_number != self.current_highlighted_line:
            # Same file, just highlight different line
            self._highlight_line(line_number)
        elif not file_path and self.code_editor:
            self.code_editor.delete('1.0', tk.END)
            self.code_editor.insert('1.0', "No source code available for this function call")
            self.current_source_file = None

    def _on_code_modified(self, event=None):
        """Handle code editor modifications"""
        if not self.file_modified and self.current_source_file:
            self.file_modified = True
            self._update_save_button_state()
            self._update_code_editor_title()

    def _update_save_button_state(self):
        """Update the save button state based on file modification status"""
        if self.save_button:
            if self.file_modified and self.current_source_file:
                self.save_button.configure(state='normal')
            else:
                self.save_button.configure(state='disabled')

    def _update_code_editor_title(self):
        """Update the code editor frame title to show modification status"""
        if hasattr(self, 'code_editor_frame') and self.code_editor_frame:
            if self.current_source_file:
                filename = os.path.basename(self.current_source_file)
                if self.file_modified:
                    title = f"Code Editor - {filename} *"
                else:
                    title = f"Code Editor - {filename}"
            else:
                title = "Code Editor"
            self.code_editor_frame.configure(text=title)

    def _save_current_file(self):
        """Save the current file content from the code editor"""
        if not self.current_source_file or not self.code_editor:
            return False

        try:
            # Get the content from the code editor
            content = self.code_editor.get('1.0', tk.END + '-1c')  # Exclude the final newline that tkinter adds

            # Create a backup of the original file
            backup_path = self.current_source_file + '.backup'
            if os.path.exists(self.current_source_file):
                import shutil
                shutil.copy2(self.current_source_file, backup_path)

            # Write the new content
            with open(self.current_source_file, 'w', encoding='utf-8') as f:
                f.write(content)

            # Mark as not modified
            self.file_modified = False
            self._update_save_button_state()
            self._update_code_editor_title()

            # Show success message in status
            if self.status_label:
                self.status_label.configure(text=f"Saved: {os.path.basename(self.current_source_file)}", foreground="green")
                # Reset status after 3 seconds
                if self.root:
                    self.root.after(3000, lambda: self.status_label.configure(text="Ready", foreground="green") if self.status_label else None)

            print(f"File saved successfully: {self.current_source_file}")
            return True

        except Exception as e:
            print(f"Error saving file {self.current_source_file}: {e}")
            if self.status_label:
                self.status_label.configure(text=f"Save error: {str(e)[:30]}", foreground="red")
                # Reset status after 5 seconds
                if self.root:
                    self.root.after(5000, lambda: self.status_label.configure(text="Ready", foreground="green") if self.status_label else None)
            return False

    def _on_ctrl_s(self, event=None):
        """Handle Ctrl+S keyboard shortcut"""
        if self.file_modified and self.current_source_file:
            self._save_current_file()
        return "break"  # Prevent default behavior

    def _update_display(self, session_id: int, call_index: int):
        """Update the display with data from the specified call"""
        self.current_session_id = session_id
        self.current_call_index = call_index
        call_data = self._get_call_data(session_id, call_index)

        # Update image with optional transparency overlay and stroboscopic effect
        if call_data.get('image_data') and self.image_label:
            transparency_image_data = None
            stroboscopic_image_data_list = []

            # Check if we should show transparency overlay
            if self.comparison_session_id and self.comparison_session_id != session_id:
                transparency_call_data = self._get_comparison_call_data(session_id, call_index)
                if transparency_call_data:
                    transparency_image_data = transparency_call_data.get('image_data')

            # Check if we should show stroboscopic phantom effect
            if self.stroboscopic_session_id and self.stroboscopic_session_id == session_id:
                stroboscopic_image_data_list = self._get_stroboscopic_frames(session_id, call_index)

            photo = self._decode_image(call_data['image_data'], transparency_image_data, stroboscopic_image_data_list)
            if photo:
                self.image_label.configure(image=photo)  # type: ignore
                # Keep a reference to prevent garbage collection
                setattr(self.image_label, 'image', photo)

        # Update variable info
        self._update_variables_display(call_data)

        # Update code editor
        self._update_code_editor(call_data)

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

    def _on_comparison_selection_changed(self, session_id: int):
        """Handle comparison overlay selection change"""
        # First, uncheck all other checkboxes (only one can be selected at a time)
        for sid, var in self.comparison_checkboxes.items():
            if sid != session_id:
                var.set(False)

        # Set the comparison session based on checkbox state
        if self.comparison_checkboxes[session_id].get():
            self.comparison_session_id = session_id
        else:
            self.comparison_session_id = None

        # Refresh the current display to apply/remove comparison
        if self.current_session_id is not None:
            self._update_display(self.current_session_id, self.current_call_index)

    def _on_stroboscopic_selection_changed(self, session_id: int):
        """Handle stroboscopic phantom effect selection change"""
        # First, uncheck all other checkboxes (only one can be selected at a time)
        for sid, var in self.stroboscopic_checkboxes.items():
            if sid != session_id:
                var.set(False)

        # Hide all other control panels
        for sid, panel in self.stroboscopic_control_panels.items():
            if sid != session_id:
                panel.pack_forget()

        # Set the stroboscopic session based on checkbox state
        if self.stroboscopic_checkboxes[session_id].get():
            self.stroboscopic_session_id = session_id
            # Show control panel for this session
            if session_id in self.stroboscopic_control_panels:
                self.stroboscopic_control_panels[session_id].pack(fill=tk.X, pady=(5, 0))
        else:
            self.stroboscopic_session_id = None
            # Hide control panel for this session
            if session_id in self.stroboscopic_control_panels:
                self.stroboscopic_control_panels[session_id].pack_forget()

        # Refresh the current display to apply/remove stroboscopic effect
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

                        #print(f"Synced parent session {parent_session_id} slider to position {parent_index}")

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

                                #print(f"Synced child session {child_session_id} slider to position {child_index}")

    def _update_comparison_checkboxes(self):
        """Update the comparison checkboxes after database refresh"""
        # This method will be called after database refresh to update checkboxes
        # For now, we'll recreate them in the UI creation
        pass

    def _create_ui(self):
        """Create the Tkinter UI"""
        self.root = tk.Tk()
        self.root.title(self.window_title)
        self.root.geometry(self.window_geometry)

        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Main vertical PanedWindow - separates top area from bottom controls/sessions
        main_paned = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # Top horizontal PanedWindow - separates image from variable info
        top_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(top_paned, weight=3)  # Give more weight to top section

        # Left side - Image frame
        image_frame = ttk.LabelFrame(top_paned, text="Game Screen", padding=10)
        top_paned.add(image_frame, weight=1)

        # Image label with fixed size
        self.image_label = ttk.Label(image_frame, text="Loading...")
        self.image_label.pack()

        # Right side - Variables and info (vertical PanedWindow)
        right_paned = ttk.PanedWindow(top_paned, orient=tk.VERTICAL)
        top_paned.add(right_paned, weight=2)  # Give more space to right side

        # Game State frame with scrollable tree
        info_frame = ttk.LabelFrame(right_paned, text="Variables (Locals & Globals)", padding=10)
        right_paned.add(info_frame, weight=2)  # Largest section

        # Create treeview for variables with fixed height
        tree_frame = ttk.Frame(info_frame, height=300)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.variables_tree = ttk.Treeview(tree_frame, columns=('value', 'previous_value'), show='tree headings')
        self.variables_tree.heading('#0', text='Variable')
        self.variables_tree.heading('value', text='Current Value')
        self.variables_tree.heading('previous_value', text='Previous Value')
        self.variables_tree.column('#0', width=200)
        self.variables_tree.column('value', width=250)
        self.variables_tree.column('previous_value', width=250)

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
        globals_frame = ttk.LabelFrame(right_paned, text="Global Variables", padding=10)
        right_paned.add(globals_frame, weight=1)

        # Scrollable frame for globals
        globals_canvas = tk.Canvas(globals_frame, height=100)
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
        tracked_frame = ttk.LabelFrame(right_paned, text="Tracked Functions", padding=10)
        right_paned.add(tracked_frame, weight=1)

        # Scrollable frame for tracked functions
        tracked_canvas = tk.Canvas(tracked_frame, height=60)
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

        # Code Editor frame
        code_editor_frame = ttk.LabelFrame(right_paned, text="Code Editor", padding=10)
        right_paned.add(code_editor_frame, weight=1)

        # Store reference to the frame
        self.code_editor_frame = code_editor_frame

        # Create a frame for the save button
        editor_controls_frame = ttk.Frame(code_editor_frame)
        editor_controls_frame.pack(fill=tk.X, pady=(0, 5))

        # Add save button
        self.save_button = ttk.Button(
            editor_controls_frame,
            text="Save (Ctrl+S)",
            command=self._save_current_file,
            state='disabled'
        )
        self.save_button.pack(side=tk.LEFT)

        # Initialize CodeView
        if CHLOROPHYLL_AVAILABLE:
            try:
                # Import pygments for syntax highlighting
                import pygments.lexers
                self.code_editor = CodeView(
                    code_editor_frame,
                    lexer=pygments.lexers.PythonLexer,
                    color_scheme="ayu-light"
                )
                self.code_editor.pack(fill=tk.BOTH, expand=True)

                # Bind modification events - CodeView inherits from Text widget
                self.code_editor.bind('<KeyPress>', self._on_code_modified)
                self.code_editor.bind('<Button-1>', self._on_code_modified)
                self.code_editor.bind('<Control-s>', self._on_ctrl_s)

            except Exception as e:
                print(f"Error creating CodeView: {e}")
                # Fall back to a regular Text widget
                self.code_editor = tk.Text(code_editor_frame)
                self.code_editor.pack(fill=tk.BOTH, expand=True)

                # Bind modification events
                self.code_editor.bind('<KeyPress>', self._on_code_modified)
                self.code_editor.bind('<Button-1>', self._on_code_modified)
                self.code_editor.bind('<Control-s>', self._on_ctrl_s)
        else:
            # Use regular Text widget as fallback
            self.code_editor = tk.Text(code_editor_frame)
            self.code_editor.pack(fill=tk.BOTH, expand=True)

            # Bind modification events
            self.code_editor.bind('<KeyPress>', self._on_code_modified)
            self.code_editor.bind('<Button-1>', self._on_code_modified)
            self.code_editor.bind('<Control-s>', self._on_ctrl_s)

            ttk.Label(code_editor_frame, text="Code editor: install chlorophyll for syntax highlighting").pack(pady=5)

        # Bottom section - another vertical PanedWindow for sessions and controls
        bottom_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(bottom_paned, weight=1)  # Less weight for bottom section

        # Sessions/Sliders frame
        sessions_frame = ttk.LabelFrame(bottom_paned, text="Sessions & Branches", padding=10)
        bottom_paned.add(sessions_frame, weight=2)  # More space for sessions

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

        # Controls frame
        controls_frame = ttk.LabelFrame(bottom_paned, text="Controls", padding=10)
        bottom_paned.add(controls_frame, weight=1)  # Less space for controls

        # Buttons frame
        buttons_frame = ttk.Frame(controls_frame)
        buttons_frame.pack(fill=tk.X)

        # Replay buttons
        ttk.Button(buttons_frame, text="Replay All", command=self._replay_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Replay From Here", command=self._replay_from_here).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Refresh DB", command=self._refresh_database).pack(side=tk.LEFT, padx=(0, 5))

        # Hidden pygame checkbox
        self.hidden_pygame_var = tk.BooleanVar(value=HIDDEN_PYGAME)
        hidden_pygame_cb = ttk.Checkbutton(
            buttons_frame,
            text="Hidden Pygame",
            variable=self.hidden_pygame_var,
            command=self._on_hidden_pygame_changed
        )
        hidden_pygame_cb.pack(side=tk.LEFT, padx=(20, 5))

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

            # Add comparison and stroboscopic checkboxes next to slider
            checkbox_frame = ttk.Frame(slider_container)
            checkbox_frame.pack(side=tk.LEFT, padx=(0, 10))

            # Create comparison checkbox variable if not exists
            if session_id not in self.comparison_checkboxes:
                self.comparison_checkboxes[session_id] = tk.BooleanVar(value=False)

            comparison_cb = ttk.Checkbutton(
                checkbox_frame,
                text="Compare",
                variable=self.comparison_checkboxes[session_id],
                command=lambda sid=session_id: self._on_comparison_selection_changed(sid)
            )
            comparison_cb.pack(side=tk.LEFT, padx=(0, 5))

            # Create stroboscopic checkbox variable if not exists
            if session_id not in self.stroboscopic_checkboxes:
                self.stroboscopic_checkboxes[session_id] = tk.BooleanVar(value=False)

            stroboscopic_cb = ttk.Checkbutton(
                checkbox_frame,
                text="Stroboscopic",
                variable=self.stroboscopic_checkboxes[session_id],
                command=lambda sid=session_id: self._on_stroboscopic_selection_changed(sid)
            )
            stroboscopic_cb.pack(side=tk.LEFT)

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

            # Create stroboscopic control panel (initially hidden)
            control_panel = self._create_stroboscopic_control_panel(session_frame, session_id)
            self.stroboscopic_control_panels[session_id] = control_panel

            self.session_sliders[session_id] = {
                'frame': session_frame,
                'slider': slider,
                'info_label': info_label,
                'comparison_checkbox': comparison_cb,
                'stroboscopic_checkbox': stroboscopic_cb,
                'control_panel': control_panel
            }

    def _get_sorted_sessions_for_display(self) -> list[int]:
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

    def _create_normal_slider(self, parent_frame: ttk.Frame, session_id: int, calls: list[Any]):
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

    def _create_stroboscopic_control_panel(self, parent_frame: ttk.LabelFrame, session_id: int) -> ttk.LabelFrame:
        """Create the stroboscopic control panel with three sliders"""
        # Create the main control panel frame
        control_panel = ttk.LabelFrame(parent_frame, text="Stroboscopic Controls", padding=5)

        # Initialize the control variables if they don't exist
        if session_id not in self.stroboscopic_ghost_count:
            self.stroboscopic_ghost_count[session_id] = tk.IntVar(value=4)
        if session_id not in self.stroboscopic_offset:
            self.stroboscopic_offset[session_id] = tk.IntVar(value=2)
        if session_id not in self.stroboscopic_x_offset:
            self.stroboscopic_x_offset[session_id] = tk.IntVar(value=5)
        if session_id not in self.stroboscopic_y_offset:
            self.stroboscopic_y_offset[session_id] = tk.IntVar(value=5)

        # Create a frame for the sliders in a grid layout
        sliders_frame = ttk.Frame(control_panel)
        sliders_frame.pack(fill=tk.X, pady=5)

        # Ghost Count Slider (1-10)
        ttk.Label(sliders_frame, text="Ghosts:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ghost_count_slider = tk.Scale(
            sliders_frame,
            from_=1,
            to=10,
            orient=tk.HORIZONTAL,
            variable=self.stroboscopic_ghost_count[session_id],
            command=lambda value, sid=session_id: self._on_stroboscopic_setting_changed(sid),
            length=100
        )
        ghost_count_slider.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))

        # Offset Slider (1-10)
        ttk.Label(sliders_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        offset_slider = tk.Scale(
            sliders_frame,
            from_=1,
            to=10,
            orient=tk.HORIZONTAL,
            variable=self.stroboscopic_offset[session_id],
            command=lambda value, sid=session_id: self._on_stroboscopic_setting_changed(sid),
            length=100
        )
        offset_slider.grid(row=0, column=3, sticky=tk.W, padx=(0, 10))

        # X Offset Slider (-20 to 20)
        ttk.Label(sliders_frame, text="X Offset:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        x_offset_slider = tk.Scale(
            sliders_frame,
            from_=-20,
            to=20,
            orient=tk.HORIZONTAL,
            variable=self.stroboscopic_x_offset[session_id],
            command=lambda value, sid=session_id: self._on_stroboscopic_setting_changed(sid),
            length=100
        )
        x_offset_slider.grid(row=0, column=5, sticky=tk.W)

        # Y Offset Slider (-20 to 20)
        ttk.Label(sliders_frame, text="Y Offset:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        y_offset_slider = tk.Scale(
            sliders_frame,
            from_=-20,
            to=20,
            orient=tk.HORIZONTAL,
            variable=self.stroboscopic_y_offset[session_id],
            command=lambda value, sid=session_id: self._on_stroboscopic_setting_changed(sid),
            length=100
        )
        y_offset_slider.grid(row=1, column=1, sticky=tk.W)

        # Add labels to explain the controls
        help_frame = ttk.Frame(control_panel)
        help_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(help_frame, text="Ghosts: Number of phantom frames",
                 font=("Arial", 8), foreground="gray").pack(side=tk.LEFT)
        ttk.Label(help_frame, text="Offset: Frame step size",
                 font=("Arial", 8), foreground="gray").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Label(help_frame, text="X/Y Offset: Position offset between frames",
                 font=("Arial", 8), foreground="gray").pack(side=tk.LEFT, padx=(20, 0))

        return control_panel

    def _on_stroboscopic_setting_changed(self, session_id: int):
        """Handle changes to stroboscopic settings"""
        # Only refresh if this is the currently active stroboscopic session
        if (self.stroboscopic_session_id == session_id and
            self.current_session_id is not None):
            self._update_display(self.current_session_id, self.current_call_index)

    def _on_hidden_pygame_changed(self):
        """Handle changes to the hidden pygame checkbox"""
        global HIDDEN_PYGAME
        HIDDEN_PYGAME = self.hidden_pygame_var.get()
        print(f"Hidden pygame mode: {'ON' if HIDDEN_PYGAME else 'OFF'}")

    def _update_variables_display(self, call_data: dict[str, Any]):
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

        # Get comparison data if a comparison session is selected
        comparison_variables = {}
        if self.comparison_session_id and self.comparison_session_id != session_id and session_id is not None:
            comparison_call_data = self._get_comparison_call_data(session_id, call_index)
            if comparison_call_data:
                comparison_variables = comparison_call_data.get('variables', {})

        # Update basic info
        if self.info_label and session_id in self.sessions_data:
            session_name = self.sessions_data[session_id]['name'] # type: ignore
            total_calls = len(self.sessions_data[session_id]['calls']) # type: ignore
            info_text = f"{session_name} | Frame {call_index + 1}/{total_calls} | "
            info_text += f"ID: {call_data.get('call_id', 'N/A')} | "
            timestamp = call_data.get('timestamp')
            if timestamp:
                info_text += f"Time: {timestamp.strftime('%H:%M:%S.%f')[:-3]}"
            if self.comparison_session_id and self.comparison_session_id in self.sessions_data:
                comparison_name = self.sessions_data[self.comparison_session_id]['name']
                info_text += f" | Comparing with: {comparison_name}"
            self.info_label.configure(text=info_text)

        # Add locals section
        locals_vars = variables.get('locals', {})
        comparison_locals = comparison_variables.get('locals', {})
        if locals_vars and self.variables_tree:
            locals_root = self.variables_tree.insert('', 'end', text='Locals', values=('', ''), open=True)
            for name, value in locals_vars.items():
                comparison_value = comparison_locals.get(name, None)
                self._add_variable_to_tree(locals_root, name, value, comparison_value)

        # Add globals section
        globals_vars = variables.get('globals', {})
        comparison_globals = comparison_variables.get('globals', {})
        if globals_vars and self.variables_tree:
            globals_root = self.variables_tree.insert('', 'end', text='Globals', values=('', ''), open=True)
            for name, value in globals_vars.items():
                comparison_value = comparison_globals.get(name, None)
                self._add_variable_to_tree(globals_root, name, value, comparison_value)

        # Restore expanded state after rebuilding
        self._restore_tree_expanded_state()

    def _add_variable_to_tree(self, parent, name: str, value: Any, comparison_value: Any = None):
        """Recursively add a variable and its sub-fields to the tree"""
        if not self.variables_tree:
            return

        # Format the value for display
        value_str = self._format_value_for_display(value)
        comparison_str = self._format_value_for_display(comparison_value) if comparison_value is not None else ""

        # Check if values are different for color coding
        values_different = False
        if comparison_value is not None:
            try:
                # Compare the actual values, not just their string representations
                values_different = value != comparison_value
            except Exception:
                # If comparison fails (e.g., different types), consider them different
                values_different = True

        # Insert the main item
        item = self.variables_tree.insert(parent, 'end', text=name, values=(value_str, comparison_str))

        # Apply green color if values are different
        if values_different:
            self.variables_tree.set(item, 'value', value_str)
            # Configure tag for green text
            self.variables_tree.tag_configure('different', foreground='green')
            self.variables_tree.item(item, tags=('different',))

        # Add sub-fields if the value has interesting attributes
        if hasattr(value, '__dict__') and value.__dict__:
            for attr_name, attr_value in value.__dict__.items():
                if not attr_name.startswith('_'):  # Skip private attributes
                    comp_attr_value = None
                    if comparison_value is not None and hasattr(comparison_value, '__dict__'):
                        comp_attr_value = getattr(comparison_value, attr_name, None)
                    self._add_variable_to_tree(item, attr_name, attr_value, comp_attr_value)
        elif isinstance(value, dict) and len(value) < 20:  # Limit dict expansion
            for key, val in value.items():
                key_str = str(key)
                if len(key_str) < 50:  # Limit key length
                    comp_val = None
                    if isinstance(comparison_value, dict):
                        comp_val = comparison_value.get(key, None)
                    self._add_variable_to_tree(item, f'[{key_str}]', val, comp_val)
        elif isinstance(value, list | tuple) and len(value) < 20:  # Limit list expansion
            for i, val in enumerate(value):
                comp_val = None
                if isinstance(comparison_value, list | tuple) and i < len(comparison_value):
                    comp_val = comparison_value[i]
                self._add_variable_to_tree(item, f'[{i}]', val, comp_val)

    def _format_value_for_display(self, value: Any) -> str:
        """Format a value for display in the tree"""
        try:
            if value is None:
                return 'None'
            if isinstance(value, str):
                # Truncate long strings
                if len(value) > 100:
                    return f'"{value[:97]}..."'
                return f'"{value}"'
            if isinstance(value, int | float | bool):
                return str(value)
            if isinstance(value, list | tuple):
                return f'{type(value).__name__}[{len(value)}]'
            if isinstance(value, dict):
                return f'dict[{len(value)}]'
            if hasattr(value, '__dict__'):
                # Custom object
                attrs = [k for k in value.__dict__ if not k.startswith('_')]
                return f'{type(value).__name__}({len(attrs)} attrs)'
            return f'{type(value).__name__} (display error)'
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
        if not self.sessions_data or self.session is None:
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
                # Get child calls (tracked functions) for each main function call
                child_calls = call.get_child_calls(self.session)
                for child_call in child_calls:
                    if child_call.function != self.tracked_function:
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

    def _get_ignored_globals(self) -> list[str]:
        """Get list of global variables that should be ignored (unchecked)"""
        return [name for name, var in self.global_vars.items() if not var.get()]

    def _get_mocked_functions(self) -> list[str]:
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
            init_monitoring(db_path=self.db_path, custom_picklers=["pygame"])
            session_id = start_session(f"Replay of {session_name}")

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
                        # check if pygame is already imported
                        if 'pygame' in sys.modules:
                            print("Pygame is already imported")
                        else:
                            print("Pygame is not imported")
                        print("importing pygame here")
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

                end_session()
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
            init_monitoring(db_path=self.db_path, custom_picklers=["pygame"])
            session_id = start_session(f"Replay from {session_name} Frame {self.current_call_index + 1}")

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
                        # check if pygame is already imported
                        if 'pygame' in sys.modules:
                            print("Pygame is already imported")
                        else:
                            print("Pygame is not imported")
                        print("importing pygame here")
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

                end_session()
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
                tracked_calls = self.session.query(FunctionCall).filter(
                    FunctionCall.session_id == session.id,
                    FunctionCall.function == self.tracked_function
                ).order_by(FunctionCall.order_in_session).all()

                if tracked_calls:
                    self.sessions_data[session.id] = {
                        'session': session,
                        'calls': tracked_calls,
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

    parser = argparse.ArgumentParser(description="Game Explorer - Multi-Branch Replay Tool")
    parser.add_argument("db_path", help="Path to the game database file")
    parser.add_argument("--function", "-f", default="display_game",
                       help="Name of the function to track for replay (default: display_game)")
    parser.add_argument("--image-key", "-i", default="image",
                       help="Metadata key for image data (default: image)")
    parser.add_argument("--title", "-t", default="Game Explorer - Multi-Branch",
                       help="Window title (default: Game Explorer - Multi-Branch)")
    parser.add_argument("--geometry", "-g", default="1400x1200",
                       help="Window geometry (default: 1400x1200)")
    parser.add_argument("--scale", "-s", type=float, default=0.8,
                       help="Image scale factor (default: 0.8)")
    args = parser.parse_args()

    # Create and run the game explorer
    explorer = GameExplorer(
        db_path=args.db_path,
        tracked_function=args.function,
        image_metadata_key=args.image_key,
        window_title=args.title,
        window_geometry=args.geometry,
        image_scale=args.scale
    )
    explorer.run()

if __name__ == "__main__":
    main()
