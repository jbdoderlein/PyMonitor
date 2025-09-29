import atexit
import datetime
import dis
import inspect
import linecache
import logging
import os
import sys
import traceback
import types
from typing import Any

from .function_call import FunctionCallRepository
from .models import FunctionCall, MonitoringSession, StackSnapshot, export_db, init_db
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

    def __init__(self, db_path="monitoring.db", pickle_config: PickleConfig | None = None, in_memory=True):
        if hasattr(self, 'initialized') and self._instance is not None:
            return
        self.initialized = True
        self.db_path = db_path
        self.call_stack : list[FunctionCall] = []  # Stack to keep track of FunctionCall objects instead of just IDs
        self.MONITOR_TOOL_ID = MONITOR_TOOL_ID
        self.in_memory = in_memory
        # Custom pickle configuration
        self.pickle_config = pickle_config

        # Recording flag
        self.is_recording_enabled = True

        # Current session information
        self.current_session : MonitoringSession | None = None  # Current monitoring session
        self.session_function_calls = {}  # Dict mapping function names to lists of call IDs
        self._current_session_first_call_id = None # ID of the first call in the current session chain
        self._current_session_last_call_id = None  # ID of the last call in the current session chain
        self._parent_id_for_next_call: int | None = None

        # Performance optimization: In-memory counters to avoid database queries
        self._current_session_call_count = 0  # Counter for order_in_session
        self._parent_call_child_counts = {}  # Dict[parent_id, child_count] for order_in_parent
        self._function_snapshot_counts = {}  # Dict[function_call_id, snapshot_count] for order_in_call

        # Performance optimization: Multi-layered caching for get_used_globals
        self._bytecode_cache = {}  # Cache for static bytecode analysis (code -> set of accessed names)
        self._type_cache = {}  # Cache for type checking results (id(obj) -> type_info)
        self._type_cache_max_size = 10000  # Prevent memory leaks
        self._globals_result_cache = {}  # Cache for final results (code_id + globals_hash -> result)

        # Performance optimization: Cache for code definitions to avoid expensive inspect operations
        self._code_definition_cache = {}  # Cache for code definition results (func_obj -> {code_def_id, mtime, module_path})

        # Initialize the database and managers
        try:
            # First, initialize the database and ensure tables are created
            Session = init_db(self.db_path, in_memory)

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
            if sys.monitoring.get_tool(self.MONITOR_TOOL_ID) is None:
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
                if self.in_memory:
                    self.export_db()
                    self.session.commit()
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

    def clear_caches(self):
        """Clear all performance caches. Useful for memory management."""
        self._bytecode_cache.clear()
        self._type_cache.clear()
        self._globals_result_cache.clear()
        self._function_snapshot_counts.clear()
        self._code_definition_cache.clear()
        logger.info("Cleared all performance caches")

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

            # Reset performance counters
            self._current_session_call_count = 0
            self._parent_call_child_counts = {}
            self._function_snapshot_counts = {}
            # Note: Don't reset bytecode cache or code definition cache as they're static
            # Only clear type cache for new session (objects may change)
            self._type_cache = {}

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

            # Reset performance counters
            self._current_session_call_count = 0
            self._parent_call_child_counts = {}
            self._function_snapshot_counts = {}
            # Note: Don't reset bytecode cache or code definition cache as they're static
            # Only clear type cache for new session (objects may change)
            self._type_cache = {}

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

    def _store_variables(self, variables: dict[str, Any]) -> dict[str, str]:
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
                logger.info(f"Could not store variable {name}: {e}")
        return refs

    def _get_cached_code_definition(self, func_obj, code_name: str) -> str | None:
        """Get cached code definition ID for a function object (performance optimization)

        Checks file modification time to ensure cache validity when source files change.

        Args:
            func_obj: The function object to get code definition for
            code_name: Name of the code object (for fallback)

        Returns:
            Code definition ID or None if not available
        """
        # Check if call_tracker is available
        if self.call_tracker is None:
            return None

        # Get the module path first to check modification time
        module_path = None
        try:
            if inspect.isfunction(func_obj):
                module = inspect.getmodule(func_obj)
                module_path = module.__file__ if module and hasattr(module, '__file__') else None
        except Exception:
            pass

        # If no module path, we can't cache effectively
        if not module_path:
            return self._compute_code_definition(func_obj, code_name, None)

        # Check cache and file modification time
        cache_entry = self._code_definition_cache.get(func_obj)
        if cache_entry is not None:
            cached_mtime = cache_entry.get('mtime')
            cached_path = cache_entry.get('module_path')

            # Only use cache if the file path matches and hasn't been modified
            if cached_path == module_path and cached_mtime is not None:
                try:
                    current_mtime = os.path.getmtime(module_path)
                    if current_mtime <= cached_mtime:
                        # File hasn't changed, use cached result
                        return cache_entry.get('code_def_id')
                except OSError:
                    # File doesn't exist or can't be accessed, invalidate cache
                    pass

        # Cache miss or file changed, compute new result
        return self._compute_code_definition(func_obj, code_name, module_path)

    def _compute_code_definition(self, func_obj, code_name: str, module_path: str | None) -> str | None:
        """Compute and cache code definition ID for a function object"""
        code_def_id = None
        current_mtime = None

        # Check if call_tracker is available
        if self.call_tracker is None:
            return None

        try:
            # Do expensive inspect operations
            if inspect.isfunction(func_obj):
                source_code = inspect.getsource(func_obj)
                first_line_no = inspect.getsourcelines(func_obj)[1]  # This gets the starting line number

                # Get module path if not provided
                if module_path is None:
                    module = inspect.getmodule(func_obj)
                    module_path = module.__file__ if module and hasattr(module, '__file__') else None

                # Get file modification time for caching
                if module_path:
                    try:
                        current_mtime = os.path.getmtime(module_path)
                    except OSError:
                        current_mtime = None

                # Only store code definition if we have all required info
                if module_path:
                    # Get code definition ID by storing/retrieving
                    code_def_id = self.call_tracker.object_manager.store_code_definition(
                        name=code_name,
                        type='function',
                        module_path=module_path,
                        code_content=source_code,
                        first_line_no=first_line_no
                    )
        except Exception as e:
            logger.warning(f"Failed to capture function code for {code_name}: {e}")

        # Cache the result with modification time
        self._code_definition_cache[func_obj] = {
            'code_def_id': code_def_id,
            'mtime': current_mtime,
            'module_path': module_path
        }

        return code_def_id

    def create_stack_snapshot(self, call_id: int, line_number: int, locals_dict: dict[str, str], globals_dict: dict[str, str], order_in_call: int | None = None) -> StackSnapshot | None:
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
        logger.info(f"Monitoring function start: {code.co_name}")
        if not self.is_recording_enabled:
            return
        if self.call_tracker is None:
            return

        current_frame = inspect.currentframe()
        if current_frame is None or current_frame.f_back is None:
            return

        frame = current_frame.f_back
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
            if not self.call_stack:
                return

            for call in self.call_stack:
                if call.function == tracking_function_name:
                    is_tracked_function = True
                    break

            if not is_tracked_function:
                return


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

        # Get cached code definition (performance optimization)
        code_def_id = self._get_cached_code_definition(func_obj, code.co_name) if func_obj else None

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

            # Calculate order in session using in-memory counter (performance optimization)
            order_in_session = None
            if self.current_session is not None:
                order_in_session = self._current_session_call_count

            # Calculate order within parent function using in-memory counter (performance optimization)
            order_in_parent = None
            if parent_id is not None:
                order_in_parent = self._parent_call_child_counts.get(parent_id, 0)

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

            # Increment counters after successful call creation (performance optimization)
            if self.current_session is not None:
                self._current_session_call_count += 1

            if parent_id is not None:
                self._parent_call_child_counts[parent_id] = self._parent_call_child_counts.get(parent_id, 0) + 1

            # Initialize snapshot counter for this function call
            self._function_snapshot_counts[call.id] = 0

        except Exception as e:
            logger.error(f"Error capturing function call: {e}")
            logger.error(traceback.format_exc())
            self.session.rollback()


    def monitor_callback_function_return(self, code: types.CodeType, offset, return_value):
        # Check if recording is enabled
        logger.info(f"Monitoring function return: {code.co_name}")
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

                # Clean up snapshot counter (performance optimization)
                if call.id in self._function_snapshot_counts:
                    del self._function_snapshot_counts[call.id]

                # Commit the changes
                self.session.commit()

            except Exception as e:
                logger.warning(f"Could not store return value: {e}")
                self.session.rollback()

        except Exception as e:
            logger.error(f"Error capturing function return: {e}")
            logger.error(traceback.format_exc())
            self.session.rollback()

    def _get_accessed_global_names(self, code: types.CodeType, processed_functions=None):
        """Extract global names accessed by bytecode (static analysis, cached)"""
        if code in self._bytecode_cache:
            return self._bytecode_cache[code]

        if processed_functions is None:
            processed_functions = set()

        accessed_names = set()

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
                # Skip if it's a default function(like print, len, etc)
                if name in __builtins__:
                    continue

                accessed_names.add(name)

        # Cache the result (this never changes for a given code object)
        self._bytecode_cache[code] = accessed_names
        return accessed_names

    def _get_object_type_info(self, obj):
        """Get cached type information for an object"""
        obj_id = id(obj)

        # Check if we already have type info for this object
        if obj_id in self._type_cache:
            return self._type_cache[obj_id]

        # Prevent memory leaks by limiting cache size
        if len(self._type_cache) >= self._type_cache_max_size:
            # Clear half the cache (simple LRU approximation)
            items_to_remove = len(self._type_cache) // 2
            for _ in range(items_to_remove):
                self._type_cache.popitem()

        # Determine type info once and cache it
        type_info = {
            'is_module': isinstance(obj, types.ModuleType),
            'is_function': isinstance(obj, types.FunctionType),
            'should_include': True  # Default to include unless explicitly excluded
        }

        # If it's a module, don't include it
        if type_info['is_module']:
            type_info['should_include'] = False

        self._type_cache[obj_id] = type_info
        return type_info

    def get_used_globals(self, code: types.CodeType, globals: dict, processed_functions=None):
        """Analyze function bytecode to find accessed global variables (optimized version)

        Args:
            code: The code object to analyze
            globals: The globals dictionary
            processed_functions: Set of function names already processed to avoid infinite recursion

        Returns:
            Dictionary of global variables used by the function and its called functions
        """
        if processed_functions is None:
            processed_functions = set()

        # Step 1: Get the static list of accessed global names (cached)
        accessed_names = self._get_accessed_global_names(code, processed_functions)

        # Step 2: For each accessed name, get its current value with type caching
        globals_used = {}

        for name in accessed_names:
            if name not in globals:
                continue

            value = globals[name]
            type_info = self._get_object_type_info(value)

            # Skip modules
            if type_info['is_module']:
                continue

            # Handle functions recursively
            if type_info['is_function']:
                # Store the function itself if needed
                # globals_used[name] = value

                # Recursively process function if not already processed
                if name not in processed_functions:
                    processed_functions.add(name)
                    try:
                        func_code = value.__code__
                        func_globals = value.__globals__
                        nested_globals = self.get_used_globals(func_code, func_globals, processed_functions)
                        globals_used.update(nested_globals)
                    except AttributeError:
                        # Handle edge cases where function doesn't have __code__ or __globals__
                        pass
                continue

            # Include regular variables
            if type_info['should_include']:
                globals_used[name] = value

        return globals_used

    def monitor_callback_line(self, code: types.CodeType, line_number):
        """Callback function for line events"""
        # Check if recording is enabled
        logger.info(f"Monitoring line: {code.co_name} at line {line_number}")
        if not self.is_recording_enabled:
            return

        if self.call_tracker is None:
            return

        current_frame = inspect.currentframe()
        if current_frame is None or current_frame.f_back is None:
            return

        if (
            code.co_name in PyMonitoring._monitored_functions and
            "lines" in PyMonitoring._monitored_functions[code.co_name] and
            PyMonitoring._monitored_functions[code.co_name]["lines"] is not None and
            line_number not in PyMonitoring._monitored_functions[code.co_name]["lines"]
        ):
            return

        if (
            code.co_name in PyMonitoring._monitored_functions and
            "use_tag_line" in PyMonitoring._monitored_functions[code.co_name] and
            PyMonitoring._monitored_functions[code.co_name]["use_tag_line"] and
            "#tag" not in linecache.getline(code.co_filename, line_number)
        ):
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
                # Get the current snapshot count using in-memory counter (performance optimization)
                snapshots_count = self._function_snapshot_counts.get(current_call.id, 0)

                self.create_stack_snapshot(
                    current_call.id,
                    line_number,
                    function_locals,
                    globals_used,
                    order_in_call=snapshots_count
                )

                # Increment the snapshot counter for this function call
                self._function_snapshot_counts[current_call.id] = snapshots_count + 1

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


def pymonitor(mode="function", ignore=None, start_hooks=None, return_hooks=None, track=None, lines=None, use_tag_line=False):
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
        lines (list[int], optional): Specific line numbers to monitor within the function if mode is "line". Defaults to None (monitor all lines).
        use_tag_line (bool, optional): If True and mode is "line", only monitor lines containing the comment "#tag". Defaults to False.

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
            "tracked_functions": track,
            "lines": lines,  # Specific lines to monitor if in line mode
            "use_tag_line": use_tag_line  # Whether to only monitor lines with #tag
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


    return PyMonitoring(*args, **kwargs)



def _cleanup_monitoring():
    if PyMonitoring._instance is not None:
        PyMonitoring._instance.shutdown()

atexit.register(_cleanup_monitoring)

