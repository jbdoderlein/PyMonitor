import inspect
import types
import sys
import jsonpickle
import dis
import json
import uuid
import threading
import datetime

# open monitor_config.json
with open('monitor_config.json', 'r') as f:
    monitor_config = json.loads(f.read())

# get tool_id
tool_id : int = int(monitor_config["tool_id"])
tool_name : str = monitor_config["tool_name"]
monitor_functions : dict[str, list[str]] = monitor_config["monitor"]

sys.monitoring.use_tool_id(tool_id, tool_name)
# Register monitoring for function calls
MONITOR_TOOL_ID = tool_id  # Can be 0-5 (reserved IDs)

recording = {}

# Add thread-local storage for execution tracking
thread_local = threading.local()

def get_exec_data():
    if not hasattr(thread_local, 'exec_stack'):
        thread_local.exec_stack = []
    if not hasattr(thread_local, 'executions'):
        thread_local.executions = {}
    return thread_local.exec_stack, thread_local.executions

def get_used_globals(code, globals):
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

# Modified monitoring callback
def monitor_callback_function_start(code: types.CodeType, offset):
    exec_stack, executions = get_exec_data()
    filename = code.co_filename.split("/")[-1]
    
    current_frame = inspect.currentframe()
    if current_frame is None or current_frame.f_back is None:
        return

    frame = current_frame.f_back
    is_monitored = filename in monitor_functions and code.co_name in monitor_functions[filename]

    # Skip internal Python system files and private methods
    skip_files = {'threading.py', '<frozen importlib._bootstrap>'}
    full_path = code.co_filename
    if any(path in full_path for path in ['/usr/lib/', '<frozen']):
        return

    if is_monitored:
        # Generate new execution ID for monitored function
        execution_id = str(uuid.uuid4())
        parent_id = exec_stack[-1][0] if exec_stack else None
        exec_stack.append((execution_id, 0))  # (id, depth)
        
        # Capture start of monitored function
        args = inspect.getargvalues(frame)
        json_trace = {
            "event_type": "call",
            "execution_id": execution_id,
            "parent_id": parent_id,
            "file": code.co_filename,
            "function": code.co_name,
            "line": frame.f_lineno,
            "locals": dict(args.locals).copy(),
            "globals": get_used_globals(code, frame.f_globals),
            "timestamp": datetime.datetime.now().isoformat()
        }
        # Store execution info for return callback
        executions[id(frame)] = (execution_id, 0)
        log_trace(json_trace)
    elif exec_stack:
        # Add filtering for child functions
        parent_id, depth = exec_stack[-1]
        if depth == 0:
            # Skip private methods and internal callbacks
            if code.co_name.startswith('_') or any(f in full_path for f in skip_files):
                return
            
            # Get caller location from the parent frame
            caller_frame = frame.f_back
            caller_line = caller_frame.f_lineno # type: ignore

            execution_id = str(uuid.uuid4())
            # Store child execution with depth 1
            executions[id(frame)] = (execution_id, 1)
            json_trace = {
                "event_type": "call",
                "execution_id": execution_id,
                "parent_id": parent_id,
                "file": code.co_filename,
                "function": code.co_name,
                "line": frame.f_lineno,
                "caller_line": caller_line,
                "locals": dict(inspect.getargvalues(frame).locals).copy(),
                "globals": get_used_globals(code, frame.f_globals),
                "timestamp": datetime.datetime.now().isoformat()
            }
            log_trace(json_trace)

def monitor_callback_function_return(code: types.CodeType, offset, return_value):
    exec_stack, executions = get_exec_data()
    filename = code.co_filename.split("/")[-1]
    # Get the frame from the execution storage instead of current frame

    current_frame = inspect.currentframe()
    if current_frame is None or current_frame.f_back is None:
        return

    frame_id = id(current_frame.f_back)
    
    if frame_id is None or frame_id not in executions:
        return
    
    execution_id, depth = executions[frame_id]
    
    # Log return event
    json_trace = {
        "event_type": "return",
        "execution_id": execution_id,
        "return_value": jsonpickle.encode(return_value, fail_safe=(lambda e: None)),
        "timestamp": datetime.datetime.now().isoformat()
    }
    log_trace(json_trace)
    
    # Clean up
    if depth == 0 and exec_stack and exec_stack[-1][0] == execution_id:
        exec_stack.pop()
    
    del executions[frame_id]

def log_trace(data):
    trace_str = jsonpickle.encode(data, fail_safe=(lambda e: None))
    if trace_str:
        with open(monitor_config["output"]["file"], "a") as f:
            f.write(trace_str + "\n")

# Update event registration

sys.monitoring.register_callback(
    MONITOR_TOOL_ID,
    sys.monitoring.events.PY_START,
    monitor_callback_function_start
)

sys.monitoring.register_callback(
    MONITOR_TOOL_ID,
    sys.monitoring.events.PY_RETURN,
    monitor_callback_function_return
)

sys.monitoring.set_events(
    MONITOR_TOOL_ID, 
    sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
)
