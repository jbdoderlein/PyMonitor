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
from .db_operations import DatabaseManager
from .worker import LogWorker

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
            
            # Now initialize the database manager
            self.db_manager = DatabaseManager(Session)
            
            # Finally, start the worker thread
            print("Starting log worker thread")
            self.log_worker = LogWorker(self.db_manager, queue_size, flush_interval)
            self.log_worker.start()
            logger.info(f"Database initialized successfully at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.error(traceback.format_exc())
            print(f"ERROR: Failed to initialize monitoring database: {e}")
            # Create a fallback in-memory database
            try:
                logger.warning("Attempting to create in-memory database as fallback")
                Session = init_db(":memory:")
                self.db_manager = DatabaseManager(Session)
                self.log_worker = LogWorker(self.db_manager, queue_size, flush_interval)
                self.log_worker.start()
                logger.info("In-memory database initialized as fallback")
                print("WARNING: Using in-memory database as fallback. Data will not be persisted.")
            except Exception as e2:
                logger.critical(f"Failed to initialize in-memory database: {e2}")
                logger.critical(traceback.format_exc())
                print(f"CRITICAL ERROR: Failed to initialize monitoring. Monitoring will be disabled.")
                self.db_manager = None
                self.log_worker = None
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
        """Gracefully shut down the logging thread"""
        logger.info("Starting PyMonitoring shutdown")
        if hasattr(self, 'log_worker') and self.log_worker is not None:
            try:
                logger.info("Shutting down log worker")
                self.log_worker.shutdown()
                logger.info("Log worker shutdown completed")
            except Exception as e:
                logger.error(f"Error during monitoring shutdown: {e}")
                logger.error(traceback.format_exc())
        else:
            logger.warning("No log worker found during shutdown")
        logger.info("PyMonitoring shutdown completed")

    def monitor_callback_function_start(self, code: types.CodeType, offset):
        current_frame = inspect.currentframe()
        if current_frame is None or current_frame.f_back is None: return
        # The parent frame should be the actual function being called
        frame = current_frame.f_back
        
        # Capture function arguments
        # Get the function's parameter names from its code object
        arg_names = code.co_varnames[:code.co_argcount]
        
        # Get the values of the arguments from the frame's locals
        function_locals = {}
        for arg_name in arg_names:
            if arg_name in frame.f_locals:
                function_locals[arg_name] = frame.f_locals[arg_name]
        
        json_trace = {
            "event_type": "call",
            "file": code.co_filename,
            "function": code.co_name,
            "line": frame.f_lineno,
            "locals": function_locals,
            "globals": self.get_used_globals(code, frame.f_globals),
            "start_time": datetime.datetime.now().isoformat()
        }
        self.execution_stack.append(json_trace)
        
        if self.pyrapl_enabled:
            self.pyrapl_stack.append(pyRAPL.Measurement(code.co_name)) # type: ignore
            self.pyrapl_stack[-1].begin()

    def monitor_callback_function_return(self, code: types.CodeType, offset, return_value):
        perf_result = None
        if self.pyrapl_enabled:
            self.pyrapl_stack[-1].end()
            measurement = self.pyrapl_stack.pop()
            perf_result = {
                "label": measurement.result.label,
                "pkg": measurement.result.pkg,
                "dram": measurement.result.dram
            }
            
        # Make sure we have a trace to pop
        if not self.execution_stack: return
        json_trace = self.execution_stack.pop()
        
        json_trace["return_value"] = return_value
        json_trace["end_time"] = datetime.datetime.now().isoformat()
        if perf_result:
            json_trace["perf_result"] = perf_result

        self.log_trace(json_trace)

    def get_used_globals(self, code, globals):
        """Analyze function bytecode to find accessed global variables"""
        globals_used = set()
        
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

                globals_used.add(name)
        
        # Filter globals dict to only keep elements with keys in globals_used
        filtered_globals = {k: v for k, v in globals.items() if k in globals_used}
        return filtered_globals

    def log_trace(self, data):
        # Add to queue for processing by worker thread
        if self.log_worker is None:
            logger.warning("Log worker not available, skipping log")
            return
            
        try:
            if not self.log_worker.add_to_queue(data):
                # If queue is full, log warning and try to process directly
                logger.warning("Log queue full, processing directly")
                if self.db_manager is not None:
                    self.db_manager.save_to_database([data])
        except Exception as e:
            logger.error(f"Error logging trace: {e}")


def pymonitor(func):
    """
    Decorator to monitor the execution of a function.
    """
    if sys.monitoring.get_tool(sys.monitoring.PROFILER_ID) is None:
        sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "py_monitoring")
    sys.monitoring.set_local_events(sys.monitoring.PROFILER_ID, func.__code__, sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN)
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
