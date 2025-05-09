import inspect
import types
import sys
import dis
import uuid
import datetime
import logging
import os
import traceback
import sqlite3
from sqlalchemy import text, inspect as sqlainspect
from sqlalchemy.orm.attributes import instance_state
from .models import init_db, FunctionCall, MonitoringSession
from .function_call import FunctionCallTracker
from typing import Optional
import time
import typing
from .representation import PickleConfig

# Configure logging - only show warnings and errors
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import pyRAPL
    import pyRAPL.outputs
except ImportError:
    pyRAPL = None
    pyRAPL_enabled = False


class PyMonitoring:
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'PyMonitoring | None':
        """Get the current PyMonitoring instance.
        
        Returns:
            The current PyMonitoring instance or None if not initialized
        """
        return cls._instance

    def __init__(self, db_path="monitoring.db", pyrapl_enabled=False, queue_size=1000, flush_interval=1.0, pickle_config=None):
        if hasattr(self, 'initialized') and self._instance is not None:
            return
        self.initialized = True
        self.db_path = db_path
        self.execution_stack = []
        self.call_id_stack = []  # Stack to keep track of function call IDs
        self.pyrapl_stack = []
        self.active_return_hooks = {} # Stores return_hooks per active call_id
        self.monitored_functions = {}
        self.MONITOR_TOOL_ID = sys.monitoring.PROFILER_ID
        
        # Custom pickle configuration
        self.pickle_config = pickle_config
        
        # Recording flag
        self.is_recording_enabled = True
        
        # Current session information
        self.current_session = None  # Current monitoring session
        self.session_function_calls = {}  # Dict mapping function names to lists of call IDs
        self._current_session_first_call_id = None # ID of the first call in the current session chain
        self._current_session_last_call_id = None  # ID of the last call in the current session chain
        self._parent_id_for_next_call: Optional[int] = None # Correct type hint
        
        # Initialize the database and managers
        try:
            # First, initialize the database and ensure tables are created
            Session = init_db(self.db_path)
            
            # Create a test session to verify database access
            test_session = Session()
            try:
                # Try a simple query to verify database access
                test_session.execute(text("SELECT 1"))
                test_session.commit()
            except Exception as e:
                logger.error(f"Database connection test failed: {e}")
                raise
            finally:
                test_session.close()
            
            # Initialize the function call tracker
            self.session = Session()
            self.call_tracker = FunctionCallTracker(self.session, monitor=self, pickle_config=self.pickle_config)
            
            logger.info(f"Database initialized successfully at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.error(traceback.format_exc())
            # Create a fallback in-memory database
            try:
                logger.warning("Attempting to create in-memory database as fallback")
                Session = init_db(":memory:")
                self.session = Session()
                self.call_tracker = FunctionCallTracker(self.session, pickle_config=self.pickle_config)
                logger.info("In-memory database initialized as fallback")
            except Exception as e2:
                logger.critical(f"Failed to initialize in-memory database: {e2}")
                logger.critical(traceback.format_exc())
                self.call_tracker = None
                return
        
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
        
        self.pyrapl_enabled = pyrapl_enabled and pyRAPL is not None
        if self.pyrapl_enabled:
            try:
                pyRAPL.setup() # type: ignore
            except Exception as e:
                logger.warning(f"PyRAPL error: {e}")
                self.pyrapl_enabled = False
        
        PyMonitoring._instance = self
        logger.info("Monitoring initialized successfully")

    def shutdown(self):
        """Gracefully shut down monitoring"""
        logger.info("Starting PyMonitoring shutdown")
        if hasattr(self, 'session'):
            try:
                logger.info("Committing final changes and closing session")
                self.session.commit()
                self.session.close()
                logger.info("Database session closed")
            except Exception as e:
                logger.error(f"Error during monitoring shutdown: {e}")
                logger.error(traceback.format_exc())
        logger.info("PyMonitoring shutdown completed")

    def export_db(self, target_file_path: str):
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
        logger.info(f"Attempting to export database to {target_file_path}")
        if not hasattr(self, 'session') or self.session is None:
            raise ValueError("Monitoring session is not initialized or available.")

        source_engine = self.session.get_bind()
        if source_engine is None:
            raise ValueError("Could not get database engine from session.")

        # Ensure any pending changes are committed to release potential locks
        try:
            logger.info("Committing session before export...")
            self.session.commit()
            logger.info("Session committed.")
        except Exception as e:
            logger.error(f"Error committing session before export: {e}. Attempting rollback.")
            try:
                self.session.rollback()
            except Exception as rb_e:
                logger.error(f"Rollback failed: {rb_e}")
            # Depending on the error, we might want to raise it or just log and proceed cautiously
            # For now, let's log and continue, the backup might still work or fail later.
            # raise ValueError(f"Failed to commit session before export: {e}") from e

        source_conn = None
        target_conn = None
        try:
            # Get the raw DBAPI connection from the engine
            dbapi_connection = source_engine.raw_connection() # type: ignore
            
            # Extract the actual sqlite3 connection object
            # This might be nested depending on SQLAlchemy version/setup
            if hasattr(dbapi_connection, 'connection'): # Standard DBAPI connection wrapper
                source_conn = dbapi_connection.connection # type: ignore
            else: # Might be the raw connection itself
                source_conn = dbapi_connection

            # Verify it's an SQLite connection
            if not isinstance(source_conn, sqlite3.Connection):
                 raise TypeError(f"Database connection is not a sqlite3 connection. Type is {type(source_conn)}")
            
            # Create a connection to the target file database
            logger.info(f"Creating target database connection: {target_file_path}")
            target_conn = sqlite3.connect(target_file_path)

            # Perform the backup
            logger.info("Starting database backup...")
            with target_conn: # 'with target_conn' handles commit/rollback on the target
                logger.debug(f"Attempting backup from {source_conn} to {target_conn}")
                source_conn.backup(target_conn)
                logger.debug("Backup call finished.")
            logger.info("Database backup completed successfully.")

        except sqlite3.Error as e:
            logger.error(f"SQLite error during database export: {e}")
            logger.error(traceback.format_exc())
            raise  # Re-raise the exception
        except Exception as e:
            logger.error(f"An unexpected error occurred during database export: {e}")
            logger.error(traceback.format_exc())
            raise # Re-raise the exception
        finally:
            # Ensure the target connection is closed
            if target_conn:
                target_conn.close()
                logger.info(f"Closed target database connection: {target_file_path}")
            # We don't close the source_conn as it's managed by SQLAlchemy engine
            # Release the raw connection obtained from the engine
            # dbapi_connection.close() # Let SQLAlchemy manage the lifecycle of the raw connection pool

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
                function_calls_map={},
                common_globals={},
                common_locals={}
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
        """End the current monitoring session and calculate common variables.
        
        Returns:
            The session ID (int) of the completed session or None if no session was active
        """
        if self.current_session is None:
            logger.warning("No active monitoring session to end.")
            return None
            
        session_id = self.current_session.id
        
        try:
            # Update the session with end time and function calls map
            # Use setattr to avoid linter errors with SQLAlchemy models
            setattr(self.current_session, 'end_time', datetime.datetime.now())
            setattr(self.current_session, 'function_calls_map', self.session_function_calls)
            
            # Calculate common variables for each function in the session
            self._calculate_common_variables()
            
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
    
    def _calculate_common_variables(self):
        """Calculate common globals and locals for each function in the current session."""
        if self.current_session is None:
            return
            
        common_globals = {}
        common_locals = {}
        
        # Process each function in the session
        for func_name, call_ids in self.session_function_calls.items():
            if not call_ids:
                continue
                
            # Get the first call to initialize the common variables
            first_call = self.session.get(FunctionCall, call_ids[0])
            if first_call is None:
                continue
                
            # Initialize with the globals and locals from the first call
            function_globals = set(first_call.globals_refs.keys())
            function_locals = set(first_call.locals_refs.keys())
            
            # Find intersection with all other calls
            for call_id in call_ids[1:]:
                call = self.session.get(FunctionCall, call_id)
                if call is None:
                    continue
                    
                # Update the intersections
                function_globals &= set(call.globals_refs.keys())
                function_locals &= set(call.locals_refs.keys())
            
            # Store the common variables
            common_globals[func_name] = list(function_globals)
            common_locals[func_name] = list(function_locals)
        
        # Update the session with common variables - using setattr to avoid linter errors
        setattr(self.current_session, 'common_globals', common_globals)
        setattr(self.current_session, 'common_locals', common_locals)
    
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
        func_obj = frame.f_globals.get(code.co_name)
        if func_obj and hasattr(func_obj, '_pymonitor_ignore'):
            ignored_variables = func_obj._pymonitor_ignore or [] # Ensure it's a list
            
        # Get hooks from the function object
        start_hooks = []
        return_hooks = []
        if func_obj:
            start_hooks = getattr(func_obj, '_pymonitor_start_hooks', []) or []
            return_hooks = getattr(func_obj, '_pymonitor_return_hooks', []) or []
            
        # Filter locals and globals based on the ignore list
        function_locals = {k: v for k, v in function_locals.items() if k not in ignored_variables}
        globals_used = {k: v for k, v in globals_used.items() if k not in ignored_variables}

        # Try to get the function's source code and create code version
        try:
            # Get the function object from the frame
            func_obj = frame.f_code.co_name
            if func_obj in frame.f_globals:
                func_obj = frame.f_globals[func_obj]
            
            # Get the source code if it's a function
            if inspect.isfunction(func_obj):
                # Get source code and the first line number
                source_code = inspect.getsource(func_obj)
                first_line_no = inspect.getsourcelines(func_obj)[1]  # This gets the starting line number
                module_path = func_obj.__module__ or 'unknown'
                
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
        
        # Capture the function call
        try:
            # Store the ID of the previous call to link it later
            prev_call_id_for_linking = self._current_session_last_call_id
            
            # Check if a parent ID was set for replay
            parent_id = self._parent_id_for_next_call
            if parent_id is not None:
                # Reset the flag immediately after reading it
                self._parent_id_for_next_call = None 
                logger.info(f"Replay detected: Setting parent_call_id to {parent_id} for next call.")
            
            # Capture the call, providing the previous call ID and potential parent ID
            call_id = self.call_tracker.capture_call(
                function_qualname,
                function_locals,
                globals_used,
                code_definition_id=code_def_id,
                file_name=file_name,
                line_number=line_number,
                initial_metadata=start_metadata, 
                previous_call_id=self._current_session_last_call_id, 
                parent_call_id=parent_id # Pass the determined parent_id
            )
            
            if call_id is None:
                # If capture_call failed, log and exit
                logger.error(f"Failed to capture function call for {function_qualname}. Aborting linking.")
                return

            self.call_id_stack.append(call_id)
            
            # --- Link the calls ---
            # If this is the first call in the session, store its ID as the entry point
            if self._current_session_first_call_id is None:
                self._current_session_first_call_id = call_id
                logger.debug(f"Set first call ID for session to {call_id}")

            # If there was a previous call, update its next_call_id
            if prev_call_id_for_linking is not None:
                try:
                    prev_call = self.session.get(FunctionCall, prev_call_id_for_linking)
                    if prev_call:
                        logger.debug(f"Linking previous call {prev_call_id_for_linking} to new call {call_id}")
                        prev_call.next_call_id = typing.cast(typing.Optional[int], call_id) # type: ignore
                        self.session.add(prev_call) # Add to session to ensure update is tracked
                        self.session.flush() # Flush to ensure the update is sent before potential commit later
                    else:
                        logger.warning(f"Could not find previous call with ID {prev_call_id_for_linking} to link.")
                except Exception as link_exc:
                    logger.error(f"Error linking call {prev_call_id_for_linking} to {call_id}: {link_exc}")
                    # Don't rollback here, allow the rest of the process to continue if possible

            # Update the last call ID to the current one for the next link
            self._current_session_last_call_id = call_id
            # --- End Linking ---

            # Store return hooks if any for later execution
            if return_hooks:
                self.active_return_hooks[call_id] = return_hooks
            
            if self.pyrapl_enabled:
                self.pyrapl_stack.append(pyRAPL.Measurement(code.co_name)) # type: ignore
                self.pyrapl_stack[-1].begin()

            # If we have an active session, add this function call to it
            if self.current_session is not None and call_id is not None:
                self.add_function_call_to_session(function_qualname, call_id)
        except Exception as e:
            logger.error(f"Error capturing function call: {e}")
            logger.error(traceback.format_exc())

    def monitor_callback_function_return(self, code: types.CodeType, offset, return_value):
        # Check if recording is enabled
        if not self.is_recording_enabled:
            return
            
        if self.call_tracker is None or not self.call_id_stack:
            return

        perf_result = None
        collected_return_metadata = {}
        if self.pyrapl_enabled and self.pyrapl_stack:
            self.pyrapl_stack[-1].end()
            measurement = self.pyrapl_stack.pop()
            # Store energy data separately first
            energy_data = {
                "package": measurement.result.pkg,
                "dram": measurement.result.dram,
                "function": measurement.result.label
            }
            # Add energy data to the metadata to be updated
            collected_return_metadata["energy_data"] = energy_data
            
        try:
            # Get the call ID for this function
            call_id = self.call_id_stack.pop()
            
            # Execute return hooks if any
            if call_id in self.active_return_hooks:
                hooks = self.active_return_hooks.pop(call_id) # Remove hooks after getting them
                for hook in hooks:
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
            
            # Capture the return value
            self.call_tracker.capture_return(call_id, return_value)
            
            # Update metadata with energy data and hook results (if any)
            if collected_return_metadata:
                # Update metadata - the method handles merging internally
                self.call_tracker.update_metadata(call_id, collected_return_metadata)
            
            # Commit the changes
            self.session.commit()
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
            if not self.call_id_stack:
                return
            current_call_id = self.call_id_stack[-1]
            
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
                snapshot = self.call_tracker.create_stack_snapshot(
                    current_call_id,
                    line_number,
                    function_locals,
                    globals_used
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


def pymonitor(ignore=None, start_hooks=None, return_hooks=None):
    """
    Decorator factory to monitor the execution of a function.
    Args:
        ignore (list[str], optional): A list of names to ignore during monitoring. Defaults to None.
        start_hooks (list[callable], optional): A list of functions to call on function start
            to generate initial metadata. Each function should accept (monitor, code, offset)
            and return a dictionary. Defaults to None.
        return_hooks (list[callable], optional): A list of functions to call on function return
            to generate additional metadata. Each function should accept (monitor, code, offset, return_value)
            and return a dictionary. Defaults to None.
    """
    if ignore is None:
        ignore = []
    if start_hooks is None:
        start_hooks = []
    if return_hooks is None:
        return_hooks = []

    def _decorator(func):
        if sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) is None:
            sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "py_monitoring")
        
        events = sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
        sys.monitoring.set_local_events(sys.monitoring.PROFILER_ID, func.__code__, events)
        
        # Store ignore list directly on the function object
        func._pymonitor_ignore = ignore
        # Store hook lists directly on the function object
        func._pymonitor_start_hooks = start_hooks
        func._pymonitor_return_hooks = return_hooks
        
        return func
    return _decorator

def pymonitor_line(func):
    """
    Decorator to monitor line-by-line execution of a function.
    Args:
        func (function): The function to monitor
    """
    if sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) is None:
        sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "py_monitoring")
    
    # Enable all necessary events: LINE for line monitoring, PY_START and PY_RETURN for function context
    events = (sys.monitoring.events.LINE | 
             sys.monitoring.events.PY_START | 
             sys.monitoring.events.PY_RETURN)
    
    # Set events for this specific function
    sys.monitoring.set_local_events(sys.monitoring.PROFILER_ID, func.__code__, events)
    
    # Store the function code for argument name lookup
    monitor = PyMonitoring.get_instance()
    if monitor is not None:
        monitor.monitored_functions[func.__name__] = func.__code__
    
    return func


def init_monitoring(*args, **kwargs):
    """
    Initialize the monitoring system.
    
    Args:
        db_path (str, optional): Path to the database file. Defaults to "monitoring.db".
        pyrapl_enabled (bool, optional): Enable PyRAPL energy monitoring. Defaults to False.
        queue_size (int, optional): Size of the monitoring queue. Defaults to 1000.
        flush_interval (float, optional): Interval for flushing the queue. Defaults to 1.0.
        pickle_config (PickleConfig, optional): Custom pickle configuration for serializing objects.
            This can include custom reducers for specific types. Defaults to None.
            
    Returns:
        PyMonitoring: The monitoring instance
    """
    monitor = PyMonitoring(*args, **kwargs)
    return monitor

# Register an atexit handler to ensure logs are flushed on program exit
import atexit

def _cleanup_monitoring():
    if PyMonitoring._instance is not None:
        PyMonitoring._instance.shutdown()

atexit.register(_cleanup_monitoring)
