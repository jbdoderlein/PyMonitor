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
from sqlalchemy import text
from .models import init_db
from .function_call import FunctionCallTracker

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

    def __init__(self, db_path="monitoring.db", pyrapl_enabled=False, queue_size=1000, flush_interval=1.0):
        if hasattr(self, 'initialized') and self._instance is not None:
            print("PyMonitoring already initialized")
            return
        self.initialized = True
        self.db_path = db_path
        self.execution_stack = []
        self.call_id_stack = []  # Stack to keep track of function call IDs
        self.pyrapl_stack = []
        self.monitored_functions = {}
        self.MONITOR_TOOL_ID = sys.monitoring.PROFILER_ID
        
        # Initialize the database and managers
        try:
            # First, initialize the database and ensure tables are created
            print(f"Initializing database at {self.db_path}")
            Session = init_db(self.db_path)
            
            # Create a test session to verify database access
            test_session = Session()
            try:
                # Try a simple query to verify database access
                test_session.execute(text("SELECT 1"))
                test_session.commit()
                print("Database connection test successful")
            except Exception as e:
                logger.error(f"Database connection test failed: {e}")
                raise
            finally:
                test_session.close()
            
            # Initialize the function call tracker
            self.session = Session()
            self.call_tracker = FunctionCallTracker(self.session, monitor=self)
            
            logger.info(f"Database initialized successfully at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.error(traceback.format_exc())
            print(f"ERROR: Failed to initialize monitoring database: {e}")
            # Create a fallback in-memory database
            try:
                logger.warning("Attempting to create in-memory database as fallback")
                Session = init_db(":memory:")
                self.session = Session()
                self.call_tracker = FunctionCallTracker(self.session)
                logger.info("In-memory database initialized as fallback")
                print("WARNING: Using in-memory database as fallback. Data will not be persisted.")
            except Exception as e2:
                logger.critical(f"Failed to initialize in-memory database: {e2}")
                logger.critical(traceback.format_exc())
                print(f"CRITICAL ERROR: Failed to initialize monitoring. Monitoring will be disabled.")
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
            print("Registered callbacks")
        except Exception as e:
            logger.error(f"Failed to register monitoring callbacks: {e}")
            print(f"ERROR: Failed to register monitoring callbacks: {e}")
        
        self.pyrapl_enabled = pyrapl_enabled and pyRAPL is not None
        print(f"PyRAPL enabled: {self.pyrapl_enabled}")
        if self.pyrapl_enabled:
            try:
                pyRAPL.setup() # type: ignore
                print("PyRAPL initialized successfully")
            except Exception as e:
                logger.warning(f"PyRAPL error: {e}")
                self.pyrapl_enabled = False
                print(f"WARNING: Failed to initialize PyRAPL: {e}")
        
        PyMonitoring._instance = self
        logger.info("Monitoring initialized successfully")
        print("Monitoring initialized")

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

    def monitor_callback_function_start(self, code: types.CodeType, offset):
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
                
                # Create code definition and version with line offset info
                code_def_id = self.call_tracker.object_manager.store_code_definition(
                    name=code.co_name,
                    type='function',
                    module_path=module_path,
                    code_content=source_code,
                    first_line_no=first_line_no  # Store the first line number
                )
                
                # Create a new version
                code_version_id = self.call_tracker.object_manager.create_code_version(code_def_id)
            else:
                code_def_id = None
                code_version_id = None
        except Exception as e:
            logger.warning(f"Failed to capture function code: {e}")
            code_def_id = None
            code_version_id = None

        # Get the actual file and line number from the code object
        file_name = code.co_filename
        line_number = code.co_firstlineno

        # Capture the function call
        try:
            call_id = self.call_tracker.capture_call(
                code.co_name,
                function_locals,
                globals_used,
                code_definition_id=code_def_id,
                code_version_id=code_version_id,
                file_name=file_name,
                line_number=line_number
            )
            self.call_id_stack.append(call_id)
            
            if self.pyrapl_enabled:
                self.pyrapl_stack.append(pyRAPL.Measurement(code.co_name)) # type: ignore
                self.pyrapl_stack[-1].begin()
        except Exception as e:
            logger.error(f"Error capturing function call: {e}")
            logger.error(traceback.format_exc())

    def monitor_callback_function_return(self, code: types.CodeType, offset, return_value):
        if self.call_tracker is None or not self.call_id_stack:
            return

        perf_result = None
        if self.pyrapl_enabled and self.pyrapl_stack:
            self.pyrapl_stack[-1].end()
            measurement = self.pyrapl_stack.pop()
            perf_result = {
                "label": measurement.result.label,
                "pkg": measurement.result.pkg,
                "dram": measurement.result.dram
            }
            
        try:
            # Get the call ID for this function
            call_id = self.call_id_stack.pop()
            
            # Capture the return value
            self.call_tracker.capture_return(call_id, return_value)
            
            # Store PyRAPL results in metadata if available
            if perf_result:
                self.call_tracker.update_metadata(call_id, {
                    "energy_data": {
                        "package": perf_result["pkg"],
                        "dram": perf_result["dram"],
                        "function": perf_result["label"]
                    }
                })
            
            # Commit the changes
            self.session.commit()
        except Exception as e:
            logger.error(f"Error capturing function return: {e}")
            logger.error(traceback.format_exc())
            self.session.rollback()

    def get_used_globals(self, code, globals):
        """Analyze function bytecode to find accessed global variables"""
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
                # Skip if it s a function
                if name in globals and isinstance(globals[name], types.FunctionType):
                    continue
                # Skip if it s a default function(like print, len, etc)
                if name in __builtins__:
                    continue

                if name in globals:
                    globals_used[name] = globals[name]
        
        return globals_used

    def monitor_callback_line(self, code: types.CodeType, line_number):
        """Callback function for line events"""
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

    class FunctionTracker:
        """Context manager for tracking function execution."""
        
        def __init__(self, monitor: 'PyMonitoring', func_name: str, args: tuple, kwargs: dict):
            self.monitor = monitor
            self.func_name = func_name
            self.args = args
            self.kwargs = kwargs
            self.return_value = None
            self.exception = None
            self.stack_trace = None
            self.start_time = None
            self.end_time = None
            
        def __enter__(self):
            self.start_time = datetime.datetime.now()
            # Get current stack trace
            self.stack_trace = ''.join(traceback.format_stack())
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.end_time = datetime.datetime.now()
            if exc_type is not None:
                self.exception = exc_val
                self.stack_trace = ''.join(traceback.format_exception(exc_type, exc_val, exc_tb))
            
            # Store the function call with all collected information
            if self.monitor.call_tracker is not None:
                self.monitor.call_tracker.store_function_call(
                    function=self.func_name,
                    start_time=self.start_time,
                    end_time=self.end_time,
                    args=self.args,
                    kwargs=self.kwargs,
                    return_value=self.return_value,
                    exception=str(self.exception) if self.exception else None,
                    stack_trace=self.stack_trace
                )

    def track_function(self, func_name: str, args: tuple, kwargs: dict) -> 'FunctionTracker':
        """Create a context manager for tracking a function's execution.
        
        Args:
            func_name: Name of the function to track
            args: Positional arguments passed to the function
            kwargs: Keyword arguments passed to the function
            
        Returns:
            A context manager for tracking the function
        """
        return self.FunctionTracker(self, func_name, args, kwargs)


def pymonitor(ignore=None):
    """
    Decorator factory to monitor the execution of a function.
    Args:
        ignore (list[str], optional): A list of names to ignore during monitoring. Defaults to None.
    """
    if ignore is None:
        ignore = []

    def _decorator(func):
        if sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) is None:
            sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "py_monitoring")
        
        events = sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
        sys.monitoring.set_local_events(sys.monitoring.PROFILER_ID, func.__code__, events)
        
        # Store ignore list directly on the function object
        func._pymonitor_ignore = ignore
        
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
    print("Initializing monitoring")
    monitor = PyMonitoring(*args, **kwargs)
    return monitor

# Register an atexit handler to ensure logs are flushed on program exit
import atexit

def _cleanup_monitoring():
    if PyMonitoring._instance is not None:
        PyMonitoring._instance.shutdown()

atexit.register(_cleanup_monitoring)
