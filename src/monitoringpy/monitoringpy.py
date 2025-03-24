import inspect
import types
import sys
import dis
import uuid
import datetime
import logging
import os
import traceback
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
            self.call_tracker = FunctionCallTracker(self.session)
            
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

        # Capture the function call
        try:
            call_id = self.call_tracker.capture_call(
                code.co_name,
                function_locals,
                globals_used
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
            snapshot = self.call_tracker.create_stack_snapshot(
                current_call_id,
                line_number,
                function_locals,
                globals_used
            )
            
            # Log for debugging
            logger.debug(f"Created stack snapshot for line {line_number} in function {code.co_name}")
            
        except Exception as e:
            logger.error(f"Error in line monitoring callback: {e}")
            logger.error(traceback.format_exc())


def pymonitor(func):
    """
    Decorator to monitor the execution of a function.
    Args:
        line (bool): Whether to monitor line-by-line execution
    """

    if sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) is None:
        sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "py_monitoring")
    events = sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
    sys.monitoring.set_local_events(sys.monitoring.PROFILER_ID, func.__code__, events)
    return func

def pymonitor_line(func):
    """
    Decorator to monitor line-by-line execution of a function.
    Args:
        func (function): The function to monitor
    """
    if sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) is None:
        sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "py_monitoring")
    events = sys.monitoring.events.LINE | sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
    sys.monitoring.set_local_events(sys.monitoring.PROFILER_ID, func.__code__, events)
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
