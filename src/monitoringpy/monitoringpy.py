import inspect
import types
import sys
import jsonpickle
import dis
import uuid
import datetime
import logging

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
    def __init__(self, output_file="monitoring.jsonl", pyrapl_enabled=True):
        self.output_file = output_file
        self.execution_stack = []
        self.pyrapl_stack = []
        self.monitored_functions = {}
        
        if sys.monitoring.get_tool(2) is not None:
            print("Monitoring already initialized")
            return
        
        self.MONITOR_TOOL_ID = 2
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

        sys.monitoring.set_events(
            self.MONITOR_TOOL_ID, 
            sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
        )
        self.pyrapl_enabled = pyrapl_enabled and pyRAPL is not None
        if self.pyrapl_enabled and pyRAPL is not None:
            pyRAPL.setup()

    def is_monitored(self, name: str):
        return name in self.monitored_functions

    def monitor_callback_function_start(self, code: types.CodeType, offset):
        # check if function needs to be monitored
        if not self.is_monitored(code.co_name):
            return

        current_frame = inspect.currentframe()
        if current_frame is None or current_frame.f_back is None:
            return

        # The parent frame should be the actual function being called
        frame = current_frame.f_back
        
        full_path = code.co_filename
        
        if any(path in full_path for path in ['/usr/lib/', '<frozen']):
            return

        execution_id = str(uuid.uuid4())
        
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
            "execution_id": execution_id,
            "file": code.co_filename,
            "function": code.co_name,
            "line": frame.f_lineno,
            "locals": function_locals,
            "globals": self.get_used_globals(code, frame.f_globals),
            "start_time": datetime.datetime.now().isoformat()
        }
        self.execution_stack.append(json_trace)
        
        if self.pyrapl_enabled and pyRAPL is not None:
            self.pyrapl_stack.append(pyRAPL.Measurement(code.co_name))
            self.pyrapl_stack[-1].begin()

    def monitor_callback_function_return(self, code: types.CodeType, offset, return_value):
        if not self.is_monitored(code.co_name):
            return
            
        if self.pyrapl_enabled and pyRAPL is not None:
            self.pyrapl_stack[-1].end()
            measurement = self.pyrapl_stack.pop()
            perf_result = {
                "label": measurement.result.label,
                "pkg": measurement.result.pkg,
                "dram": measurement.result.dram
            }
            
        # Make sure we have a trace to pop
        if not self.execution_stack:
            return
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
        trace_str = jsonpickle.encode(data, fail_safe=(lambda e: None))
        if trace_str:
            with open(self.output_file, "a") as f:
                f.write(trace_str + "\n")


# Global instance of the monitoring system
_py_monitoring = None

def init_monitoring(output_file="monitoring.jsonl"):
    """Initialize the monitoring system with the given configuration file.
    
    Args:
        output_file (str, optional): Override the output file specified in config
    """
    global _py_monitoring
    _py_monitoring = PyMonitoring(output_file)


def pymonitor(func):
    """
    Decorator to monitor the execution of a function.
    """
    if _py_monitoring is not None and func.__name__ not in _py_monitoring.monitored_functions:
        _py_monitoring.monitored_functions[func.__name__] = True
    return func

