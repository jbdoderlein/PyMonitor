import inspect
import atexit
import types
import sys
import dis
import datetime
import logging
import traceback
import sqlite3
from .models import export_db, init_db, FunctionCall, MonitoringSession, StackSnapshot
from .function_call import FunctionCallRepository
from typing import Optional, Dict, Any
from .representation import ObjectManager, PickleConfig

# Configure logging - only show warnings and errors
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MONITOR_TOOL_ID = sys.monitoring.PROFILER_ID

class PyMonitoring:
    _instance = None

    _monitored_functions = {}
    _tracked_functions = {}
    
    @classmethod
    def get_instance(cls) -> 'PyMonitoring | None':
        """Get the current PyMonitoring instance.
        
        Returns:
            The current PyMonitoring instance or None if not initialized
        """
        return cls._instance

    def __init__(self, db_path="monitoring.db", pickle_config: Optional[PickleConfig] = None):
        if hasattr(self, 'initialized') and self._instance is not None:
            return
        self.initialized = True
        self.db_path = db_path
        self.call_stack : list[FunctionCall] = []  # Stack to keep track of FunctionCall objects instead of just IDs
        self.MONITOR_TOOL_ID = MONITOR_TOOL_ID
        
        # Custom pickle configuration
        self.pickle_config = pickle_config
        
        # Recording flag
        self.is_recording_enabled = True
        
        # Current session information
        self.current_session : Optional[MonitoringSession] = None  # Current monitoring session
        self.session_function_calls = {}  # Dict mapping function names to lists of call IDs
        self._current_session_first_call_id = None # ID of the first call in the current session chain
        self._current_session_last_call_id = None  # ID of the last call in the current session chain
        self._parent_id_for_next_call: Optional[int] = None
        
        # Initialize the database and managers
        try:
            # First, initialize the database and ensure tables are created
            Session = init_db(self.db_path)
            
            # Initialize the function call tracker
            self.session = Session()
            
            self.call_tracker = FunctionCallRepository(self.session, pickle_config=self.pickle_config)
            self.object_manager = ObjectManager(self.session, pickle_config=self.pickle_config)
            
            logger.info(f"Database initialized successfully at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.error(traceback.format_exc())
            self.call_tracker = None
        
        try:
            if sys.monitoring.get_tool(2) is None:
                sys.monitoring.use_tool_id(self.MONITOR_TOOL_ID, "py_monitoring")

            sys.monitoring.register_callback(
                self.MONITOR_TOOL_ID,
                sys.monitoring.events.PY_START,
                self.monitor_callback_function_start
            )

            sys.monitoring.register_callback(
                self.MONITOR_TOOL_ID,
                sys.monitoring.events.PY_RETURN,
                self.monitor_callback_function_return
            )

            sys.monitoring.register_callback(
                self.MONITOR_TOOL_ID,
                sys.monitoring.events.LINE,
                self.monitor_callback_line
            )
            
            logger.info("Registered monitoring callbacks")
        except Exception as e:
            logger.error(f"Failed to register monitoring callbacks: {e}")
        
        PyMonitoring._instance = self
        logger.info("Monitoring initialized successfully")

    def shutdown(self):
        """Gracefully shut down monitoring"""
        logger.info("Starting PyMonitoring shutdown")
        if hasattr(self, 'session'):
            try:
                logger.info("Committing final changes and closing session")
                self.session.commit()
                self.export_db()
                self.session.close()
                logger.info("Database session closed")
            except Exception as e:
                logger.error(f"Error during monitoring shutdown: {e}")
                logger.error(traceback.format_exc())
        logger.info("PyMonitoring shutdown completed")

    def disable_recording(self):
        """Temporarily disable recording of function calls and line execution.
        
        This can be useful when you want to run code without monitoring overhead
        or when you want to exclude certain parts of your program from monitoring.
        """
        logger.info("Disabling monitoring recording")
        self.is_recording_enabled = False
        
    def enable_recording(self):
        """Re-enable recording of function calls and line execution.
        
        Call this after disable_recording() to resume monitoring.
        """
        logger.info("Enabling monitoring recording")
        self.is_recording_enabled = True

    def export_db(self):
        """Exports the current monitoring database to a specified file.

        This is particularly useful when using an in-memory database (":memory:")
        to persist the collected data before the application exits.

        Args:
            target_file_path: The path to the file where the database should be saved.

        Raises:
            ValueError: If the monitoring session is not available or the database
                        connection cannot be established.
            Exception: Any exceptions raised during the database backup process.
        """
        export_db(self.session, self.db_path)

    def start_session(self, name=None, description=None, metadata=None):
        """Start a new monitoring session to group function calls.
        
        Args:
            name: Optional name for the session
            description: Optional description for the session
            metadata: Optional metadata dictionary for additional information
            
        Returns:
            The session ID (int) of the new session or None if session creation failed
        """
        if self.call_tracker is None:
            logger.warning("Call tracker is not initialized. Session will not be created.")
            return None
            
        # Commit any pending changes to ensure data consistency
        try:
            self.session.commit()
        except Exception as e:
            logger.error(f"Error committing session before starting new monitoring session: {e}")
            self.session.rollback()
        
        # Create a new session
        try:
            new_session = MonitoringSession(
                name=name,
                description=description,
                start_time=datetime.datetime.now(),
                session_metadata=metadata or {},
            )
            
            self.session.add(new_session)
            self.session.commit()
            
            self.current_session = new_session
            self.session_function_calls = {}  # Reset the function calls map
            # Reset linked list trackers for the new session
            self._current_session_first_call_id = None
            self._current_session_last_call_id = None
            
            logger.info(f"Started new monitoring session {new_session.id}: {name}")
            return new_session.id
            
        except Exception as e:
            logger.error(f"Error creating new monitoring session: {e}")
            logger.error(traceback.format_exc())
            self.session.rollback()
            return None
    
    def end_session(self):
        """End the current monitoring session.
        
        Returns:
            The session ID (int) of the completed session or None if no session was active
        """
        if self.current_session is None:
            logger.warning("No active monitoring session to end.")
            return None
            
        session_id = self.current_session.id
        
        try:
            # Update the session with end time
            setattr(self.current_session, 'end_time', datetime.datetime.now())
            
            # Set the entry point for the session's call chain
            if self._current_session_first_call_id is not None:
                logger.info(f"Setting entry point for session {session_id} to call {self._current_session_first_call_id}")
                setattr(self.current_session, 'entry_point_call_id', self._current_session_first_call_id)
            else:
                logger.warning(f"No first function call recorded for session {session_id}. Entry point not set.")
                
            # Commit the changes including the entry point
            self.session.commit()
            
            logger.info(f"Ended monitoring session {session_id}")
            
            # Reset current session and linked list trackers
            self.current_session = None
            self.session_function_calls = {}
            self._current_session_first_call_id = None
            self._current_session_last_call_id = None
            
            return session_id
            
        except Exception as e:
            logger.error(f"Error ending monitoring session: {e}")
            logger.error(traceback.format_exc())
            self.session.rollback()
            return None

    def add_function_call_to_session(self, function_name, call_id):
        """Add a function call to the current session.
        
        Args:
            function_name: Name of the function
            call_id: ID of the function call
        """
        if self.current_session is None or call_id is None:
            return
            
        # Initialize the list for this function if it doesn't exist
        if function_name not in self.session_function_calls:
            self.session_function_calls[function_name] = []
            
        # Add the call ID to the list
        self.session_function_calls[function_name].append(call_id)

    def _store_variables(self, variables: Dict[str, Any]) -> Dict[str, str]:
        """Store variables and return a dictionary of variable names to object references"""
        refs = {}
        for name, value in variables.items():
            # Skip special variables and functions
            if name.startswith('__') or callable(value):
                continue
            try:
                # Store the value and get its reference
                ref = self.object_manager.store(value)
                # Always store the reference, not the value
                refs[name] = ref
            except Exception as e:
                # Log warning but continue if we can't store a variable
                logger.warning(f"Could not store variable {name}: {e}")
        return refs

    def create_stack_snapshot(self, call_id: int, line_number: int, locals_dict: Dict[str, str], globals_dict: Dict[str, str], order_in_call: Optional[int] = None) -> Optional[StackSnapshot]:
        """
        Create a stack snapshot for a function call.
        
        Args:
            call_id: The ID of the function call
            line_number: The line number where the snapshot was taken
            locals_dict: Dictionary of local variable references
            globals_dict: Dictionary of global variable references
            order_in_call: Position in the execution sequence (optional)
            
        Returns:
            The created StackSnapshot object or None if creation fails
        """
        if self.call_tracker is None:
            return None
            
        try:
            # Get the function call
            call = self.session.get(FunctionCall, call_id)
            if not call:
                logger.error(f"Function call {call_id} not found during stack snapshot creation")
                return None
            
            # Find the previous snapshot if any
            prev_snapshot = None
            if order_in_call is not None and order_in_call > 0:
                prev_snapshot = self.session.query(StackSnapshot).filter(
                    StackSnapshot.function_call_id == call_id,
                    StackSnapshot.order_in_call == order_in_call - 1
                ).first()
            
            # Create the new snapshot
            snapshot = StackSnapshot(
                function_call_id=call_id,
                line_number=line_number,
                locals_refs=locals_dict,
                globals_refs=globals_dict,
                order_in_call=order_in_call
            )
            
            # Set bidirectional link if previous snapshot exists
            if prev_snapshot:
                prev_snapshot.next_snapshot_id = snapshot.id
            
            self.session.add(snapshot)
            
            # If this is the first snapshot for this call, update the call record
            if order_in_call == 0 or not call.first_snapshot_id:
                call.first_snapshot_id = snapshot.id
            
            self.session.flush()  # Flush to get the ID
            
            return snapshot
        except Exception as e:
            logger.error(f"Error creating stack snapshot for call {call_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    def monitor_callback_function_start(self, code: types.CodeType, offset):
        # Check if recording is enabled
        if not self.is_recording_enabled:
            return
        
        if self.call_tracker is None:
            return
        current_frame = inspect.currentframe()
        if current_frame is None or current_frame.f_back is None: 
            return
            
        # The parent frame should be the actual function being called
        frame = current_frame.f_back
        
        # Get the function object from the frame
        func_name = code.co_name
        
        func_obj = frame.f_globals.get(func_name)
        
        # Check if this is a tracked function and if so, 
        # verify that its tracking function is in our call stack
        is_tracked_function = False
        tracking_function_name = None
        
        # Check direct attribute on function object
        if func_obj and func_name in PyMonitoring._tracked_functions:
            tracking_function_name = PyMonitoring._tracked_functions[func_name]["parent_tracking_function"]
        
        # If we found tracking information, verify it's in our call stack
        if tracking_function_name:
            # Only track this function if we're inside its tracking function
            if not self.call_stack:
                # We're not inside any monitored function, so don't track
                return
            
            # We're inside some monitoring context, let's check if it matches
            # If this function was tracked by a specific function, verify it's in our stack
            for call in self.call_stack:
                if call.function == tracking_function_name:
                    is_tracked_function = True
                    break
                    
            if not is_tracked_function:
                # The tracking function isn't in our stack, don't monitor this call
                return
                
            logger.info(f"Tracking function {func_name} called within {tracking_function_name}")
        
        # Get the function's parameter names from its code object
        arg_names = code.co_varnames[:code.co_argcount]
        
        # Get the values of the arguments from the frame's locals
        function_locals = {}
        for arg_name in arg_names:
            if arg_name in frame.f_locals:
                function_locals[arg_name] = frame.f_locals[arg_name]
        
        # Get used globals
        globals_used = self.get_used_globals(code, frame.f_globals)
        
        # Get ignored variables from the function object itself
        ignored_variables = []
        if func_obj and func_name in PyMonitoring._monitored_functions:
            ignored_variables = PyMonitoring._monitored_functions[func_name]["ignore"] or [] # Ensure it's a list
            
        # Get hooks from the function object
        start_hooks = []
        if func_obj:
            # Safely get start_hooks, handling case where function isn't registered
            if func_name in PyMonitoring._monitored_functions:
                start_hooks = PyMonitoring._monitored_functions[func_name]["start_hooks"] or []
            else:
                # Function not explicitly registered for monitoring, use empty hooks
                logger.debug(f"Function '{func_name}' not found in _monitored_functions, using empty start_hooks")
                start_hooks = []
            
        # Filter locals and globals based on the ignore list
        function_locals = {k: v for k, v in function_locals.items() if k not in ignored_variables}
        globals_used = {k: v for k, v in globals_used.items() if k not in ignored_variables}

        # Try to get the function's source code and create code version
        try:
            # Get source code and the first line number
            if inspect.isfunction(func_obj):
                source_code = inspect.getsource(func_obj)
                first_line_no = inspect.getsourcelines(func_obj)[1]  # This gets the starting line number
                
                # Safely get the module path
                module = inspect.getmodule(func_obj)
                module_path = module.__file__ if module and hasattr(module, '__file__') else None
                
                # Only store code definition if we have all required info
                if module_path:
                    # Get code definition ID by storing/retrieving
                    code_def_id = self.call_tracker.object_manager.store_code_definition(
                        name=code.co_name, 
                        type='function',
                        module_path=module_path,
                        code_content=source_code, 
                        first_line_no=first_line_no
                    )
                else:
                    code_def_id = None
            else:
                code_def_id = None
        except Exception as e:
            logger.warning(f"Failed to capture function code: {e}")
            code_def_id = None

        # Execute start hooks and collect initial metadata
        start_metadata = {}
        for hook in start_hooks:
            try:
                hook_metadata = hook(self, code, offset)
                if isinstance(hook_metadata, dict):
                    start_metadata.update(hook_metadata)
                else:
                    logger.warning(f"Start hook {hook.__name__} for {code.co_name} did not return a dict.")
            except Exception as hook_exc:
                logger.error(f"Error executing start hook {hook.__name__} for {code.co_name}: {hook_exc}")
                logger.error(traceback.format_exc())

        # Get the actual file and line number from the code object
        file_name = code.co_filename
        line_number = code.co_firstlineno

        # Get function qualname for better tracking
        function_qualname = code.co_name
        try:
            if 'self' in frame.f_locals and hasattr(frame.f_locals['self'], '__class__'):
                function_qualname = f"{frame.f_locals['self'].__class__.__name__}.{code.co_name}"
        except Exception:
            pass  # Use simple name if extraction fails
        
        # Create the function call directly (inlined capture_call)
        try:
            # Store local and global variables
            locals_refs = self._store_variables(function_locals)
            globals_refs = self._store_variables(globals_used)

            # Check if a parent ID was set for replay
            parent_id = self._parent_id_for_next_call
            if parent_id is not None:
                # Reset the flag immediately after reading it
                self._parent_id_for_next_call = None 
                logger.info(f"Replay detected: Setting parent_call_id to {parent_id} for next call.")
            
            # If we're inside another monitored function (stack isn't empty), get the parent ID
            if not parent_id and len(self.call_stack) > 0:
                parent_id = self.call_stack[-1].id
                
            # Calculate order in session using existing calls count
            order_in_session = None
            if self.current_session is not None:
                # Count existing calls in session
                count = self.session.query(FunctionCall).filter(
                    FunctionCall.session_id == self.current_session.id
                ).count()
                order_in_session = count
                
            # Calculate order within parent function using existing child calls count
            order_in_parent = None
            if parent_id is not None:
                # Count existing child calls of this parent
                count = self.session.query(FunctionCall).filter(
                    FunctionCall.parent_call_id == parent_id
                ).count()
                order_in_parent = count

            # Get the current session ID from the monitor instance, if available
            current_session_id = None
            if self.current_session:
                current_session_id = self.current_session.id

            # Create function call record directly
            call = FunctionCall(
                function=function_qualname,
                file=file_name,
                line=line_number,
                start_time=datetime.datetime.now(),
                locals_refs=locals_refs,
                globals_refs=globals_refs,
                code_definition_id=code_def_id,
                call_metadata=start_metadata,
                parent_call_id=parent_id,
                session_id=current_session_id,
                order_in_session=order_in_session,
                order_in_parent=order_in_parent
            )
            
            self.session.add(call)
            self.session.flush()  # Flush to get the ID
            
            if call.id is None:
                logger.error(f"Failed to obtain ID for new FunctionCall for {function_qualname}")
                self.session.rollback()
                return
            
            # Add the FunctionCall object to the stack instead of just the ID
            self.call_stack.append(call)
            
            # Track the first call in the session as the entry point
            if self._current_session_first_call_id is None:
                self._current_session_first_call_id = call.id
                logger.debug(f"Set first call ID for session to {call.id}")

            # Update the last call ID to the current one
            self._current_session_last_call_id = call.id
            
            # If we have an active session, add this function call to it
            if self.current_session is not None and call.id is not None:
                self.add_function_call_to_session(function_qualname, call.id)
                
        except Exception as e:
            logger.error(f"Error capturing function call: {e}")
            logger.error(traceback.format_exc())
            self.session.rollback()

    def monitor_callback_function_return(self, code: types.CodeType, offset, return_value):
        # Check if recording is enabled
        if not self.is_recording_enabled:
            return
            
        if self.call_tracker is None or not self.call_stack:
            return

        collected_return_metadata = {}
        try:
            # Get the FunctionCall object for this function
            call = self.call_stack.pop()
            
            # Get the function object from the frame
            frame = inspect.currentframe()
            if frame is None or frame.f_back is None:
                return
            func_obj = frame.f_back.f_globals.get(code.co_name)
            return_hooks = []
            if func_obj:
                # Safely get return_hooks, handling case where function isn't registered
                if code.co_name in PyMonitoring._monitored_functions:
                    return_hooks = PyMonitoring._monitored_functions[code.co_name]["return_hooks"] or []
                else:
                    # Function not explicitly registered for monitoring, use empty hooks
                    logger.debug(f"Function '{code.co_name}' not found in _monitored_functions, using empty return_hooks")
                    return_hooks = []
            
            # Execute return hooks if any
            for hook in return_hooks:
                try:
                    # Pass monitor instance, code object, offset, and return value
                    hook_metadata = hook(self, code, offset, return_value)
                    if isinstance(hook_metadata, dict):
                        # Merge hook metadata, preferring hook's values on conflict
                        collected_return_metadata.update(hook_metadata)
                    else:
                        logger.warning(f"Return hook {hook.__name__} for {code.co_name} did not return a dict.")
                except Exception as hook_exc:
                    logger.error(f"Error executing return hook {hook.__name__} for {code.co_name}: {hook_exc}")
                    logger.error(traceback.format_exc())
            
            # Inline capture_return functionality - store return value and update call
            try:
                return_ref = self.call_tracker.object_manager.store(return_value)
                call.return_ref = return_ref
                call.end_time = datetime.datetime.now()
                
                # Update metadata with hook results (if any)
                if collected_return_metadata:
                    # If there's existing metadata, merge it with the new data
                    if call.call_metadata:
                        # Create a new dict to avoid modifying the original
                        updated_metadata = dict(call.call_metadata)
                        updated_metadata.update(collected_return_metadata)
                        call.call_metadata = updated_metadata
                    else:
                        call.call_metadata = collected_return_metadata
                
                # Commit the changes
                self.session.commit()
                
            except Exception as e:
                logger.warning(f"Could not store return value: {e}")
                self.session.rollback()
            
        except Exception as e:
            logger.error(f"Error capturing function return: {e}")
            logger.error(traceback.format_exc())
            self.session.rollback()

    def get_used_globals(self, code, globals, processed_functions=None):
        """Analyze function bytecode to find accessed global variables
        
        Args:
            code: The code object to analyze
            globals: The globals dictionary
            processed_functions: Set of function names already processed to avoid infinite recursion
            
        Returns:
            Dictionary of global variables used by the function and its called functions
        """
        if processed_functions is None:
            processed_functions = set()
            
        globals_used = {}
        
        # Scan bytecode for LOAD_GLOBAL operations
        for instr in dis.get_instructions(code):
            if instr.opname == "LOAD_GLOBAL":
                name = instr.argval
                # Skip special dunder methods
                if (name.startswith('__') and name.endswith('__')):
                    continue
                # Skip built-in variables
                if name in sys.builtin_module_names:
                    continue
                # Skip if it's a module
                if name in globals and isinstance(globals[name], types.ModuleType):
                    continue
                # Process user-defined functions recursively
                if name in globals and isinstance(globals[name], types.FunctionType):
                    # Store the function itself if needed
                    # globals_used[name] = globals[name]
                    
                    # Recursively process function if not already processed
                    if name not in processed_functions:
                        processed_functions.add(name)
                        func_code = globals[name].__code__
                        func_globals = globals[name].__globals__
                        nested_globals = self.get_used_globals(func_code, func_globals, processed_functions)
                        globals_used.update(nested_globals)
                    continue
                # Skip if it's a default function(like print, len, etc)
                if name in __builtins__:
                    continue

                if name in globals:
                    globals_used[name] = globals[name]
        
        return globals_used

    def monitor_callback_line(self, code: types.CodeType, line_number):
        """Callback function for line events"""
        # Check if recording is enabled
        if not self.is_recording_enabled:
            return
            
        if self.call_tracker is None:
            return

        current_frame = inspect.currentframe()
        if current_frame is None or current_frame.f_back is None:
            return
            
        # The parent frame should be the actual function being executed
        frame = current_frame.f_back
        
        try:
            # Get the current function call from the stack
            if not self.call_stack:
                return
            current_call = self.call_stack[-1]
            
            # Get function's locals and globals
            function_locals = {}
            globals_used = {}
            
            # Capture locals
            for name, value in frame.f_locals.items():
                try:
                    # Skip special variables and functions
                    if name.startswith('__') or callable(value):
                        continue
                    ref = self.call_tracker.object_manager.store(value)
                    function_locals[name] = ref
                except Exception as e:
                    logger.warning(f"Failed to store local variable {name}: {e}")
            
            # Capture used globals
            for name, value in self.get_used_globals(code, frame.f_globals).items():
                try:
                    ref = self.call_tracker.object_manager.store(value)
                    globals_used[name] = ref
                except Exception as e:
                    logger.warning(f"Failed to store global variable {name}: {e}")
            
            # Create a new stack snapshot
            try:
                # Get the current snapshot count to use as order_in_call
                snapshots_count = self.session.query(StackSnapshot).filter(
                    StackSnapshot.function_call_id == current_call.id
                ).count()
                
                self.create_stack_snapshot(
                    current_call.id,
                    line_number,
                    function_locals,
                    globals_used,
                    order_in_call=snapshots_count  # Add this parameter
                )
                
                # Log for debugging
                logger.debug(f"Created stack snapshot for line {line_number} in function {code.co_name}")
                
                # Commit to ensure the snapshot is saved
                self.session.commit()
                
            except Exception as e:
                logger.error(f"Error creating stack snapshot: {e}")
                logger.error(traceback.format_exc())
                self.session.rollback()
            
        except Exception as e:
            logger.error(f"Error in line monitoring callback: {e}")
            logger.error(traceback.format_exc())


def pymonitor(mode="function", ignore=None, start_hooks=None, return_hooks=None, track=None):
    """
    Unified decorator for monitoring Python function execution.
    
    Args:
        mode (str): Monitoring mode - "function" or "line". Defaults to "function".
            - "function": Records only function entry and exit
            - "line": Records state at each line of execution
        ignore (list[str], optional): Variable names to ignore during monitoring. Defaults to None.
        start_hooks (list[callable], optional): Functions called at function start to generate metadata.
            Each function should accept (monitor, code, offset) and return a dictionary. Defaults to None.
        return_hooks (list[callable], optional): Functions called at function return to generate metadata.
            Each function should accept (monitor, code, offset, return_value) and return a dictionary. Defaults to None.
        track (list[callable], optional): Additional functions to track only when they are called within
            this monitored function context. These functions won't be tracked when called directly
            outside a monitored context. Defaults to None.
    
    Returns:
        The decorated function with monitoring enabled
    
    Example:
        @pymonitor(mode="line", ignore=["large_data"], track=[helper_function])
        def my_function(x, y):
            result = helper_function(x)  # helper_function will be tracked here
            return result
            
        helper_function(10)  # Not tracked when called directly
    """
    # Initialize default parameter values
    if ignore is None:
        ignore = []
    if start_hooks is None:
        start_hooks = []
    if return_hooks is None:
        return_hooks = []
    if track is None:
        track = []
    
    # Validate mode parameter
    if mode not in ["function", "line"]:
        raise ValueError(f"Invalid monitoring mode: {mode}. Must be 'function' or 'line'")
    
    def _decorator(func):
        # Add logging to see which function is being decorated
        logger.info(f"Applying pymonitor decorator to function: {func.__name__}")
        
        # Ensure monitoring tool is initialized
        if sys.monitoring.get_tool(MONITOR_TOOL_ID) is None:
            sys.monitoring.use_tool_id(MONITOR_TOOL_ID, "py_monitoring")
        
        # Set events based on mode
        if mode == "line":
            events = (sys.monitoring.events.LINE | 
                     sys.monitoring.events.PY_START | 
                     sys.monitoring.events.PY_RETURN)
        else:  # mode == "function"
            events = sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
        
        # Enable monitoring for this function
        sys.monitoring.set_local_events(MONITOR_TOOL_ID, func.__code__, events)
        
        # Store metadata on the function object
        PyMonitoring._monitored_functions[func.__name__] = {
            "ignore": ignore,
            "start_hooks": start_hooks,
            "return_hooks": return_hooks,
            "tracked_functions": track
        }
        
        # Also enable monitoring for tracked functions
        for tracked_func in track:
            if callable(tracked_func):
                # Mark the tracked function with the parent that's tracking it
                
                PyMonitoring._tracked_functions[tracked_func.__name__] = {
                    "parent_tracking_function": func.__name__
                }

                if tracked_func.__name__ not in PyMonitoring._monitored_functions:
                    PyMonitoring._monitored_functions[tracked_func.__name__] = {
                        "ignore": [],
                        "start_hooks": [],
                        "return_hooks": [],
                        "tracked_functions": []
                    }
                logger.info(f"Enabling monitoring for tracked function: {tracked_func.__name__} (tracked by {func.__name__})")
                
                # Use function mode for tracked functions to avoid overhead
                tracked_events = sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
                if not hasattr(tracked_func, '__code__'):
                    logger.warning(f"Tracked function {tracked_func.__name__} has no __code__ attribute, skipping monitoring")
                    continue
                else:
                    sys.monitoring.set_local_events(MONITOR_TOOL_ID, tracked_func.__code__, tracked_events)

        return func
    
    # Handle usage as a direct decorator (no arguments)
    if callable(mode) and not isinstance(mode, str):
        func = mode
        mode = "function"  # Default to function mode
        return _decorator(func)
    
    return _decorator


def init_monitoring(*args, **kwargs):
    """
    Initialize the monitoring system.
    
    Args:
        db_path (str, optional): Path to the database file. Defaults to "monitoring.db".
        queue_size (int, optional): Size of the monitoring queue. Defaults to 1000.
        flush_interval (float, optional): Interval for flushing the queue. Defaults to 1.0.
        pickle_config (PickleConfig, optional): Custom pickle configuration for serializing objects.
            This can include custom reducers for specific types. Defaults to None.
        custom_picklers (list, optional): List of module names to load custom picklers from.
            These will be loaded from the monitoringpy/picklers directory. Defaults to None.
            
    Returns:
        PyMonitoring: The monitoring instance
    """
    # Add debug logging
    logger.info("Initializing PyMonitoring system")
    
    # If custom_picklers is specified but pickle_config is not,
    # create a new pickle_config with the custom picklers
    if 'custom_picklers' in kwargs and 'pickle_config' not in kwargs:
        kwargs['pickle_config'] = PickleConfig(custom_picklers=kwargs.pop('custom_picklers'))
    # If both are specified, update the existing pickle_config
    elif 'custom_picklers' in kwargs and 'pickle_config' in kwargs:
        custom_picklers = kwargs.pop('custom_picklers')
        kwargs['pickle_config'].load_custom_picklers(custom_picklers)
    
        
    monitor = PyMonitoring(*args, **kwargs)
    return monitor



def _cleanup_monitoring():
    if PyMonitoring._instance is not None:
        PyMonitoring._instance.shutdown()

atexit.register(_cleanup_monitoring)

