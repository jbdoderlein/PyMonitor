import inspect
import types
import sys
import jsonpickle
import dis
import json
import uuid
import threading
import datetime
import os

recording = {}
thread_local = threading.local()
monitor_config = None
monitor_functions = None
MONITOR_TOOL_ID = None

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

def monitor_callback_function_start(code: types.CodeType, offset):
    if monitor_config is None or monitor_functions is None:
        return
        
    exec_stack, executions = get_exec_data()
    filename = code.co_filename.split("/")[-1]
    
    current_frame = inspect.currentframe()
    if current_frame is None or current_frame.f_back is None:
        return

    frame = current_frame.f_back
    is_monitored = filename in monitor_functions and (code.co_name in monitor_functions[filename] or "*" in monitor_functions[filename])

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
    if monitor_config is None:
        return
        
    exec_stack, executions = get_exec_data()
    filename = code.co_filename.split("/")[-1]

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
    if trace_str and monitor_config is not None:
        output_file = monitor_config["output"]["file"]
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "a") as f:
            f.write(trace_str + "\n")

def init_monitoring(config_path='monitor_config.json', output_file=None):
    """Initialize the monitoring system with the given configuration file.
    
    Args:
        config_path (str): Path to the monitor_config.json file
        output_file (str, optional): Override the output file specified in config
    """
    global monitor_config, monitor_functions, MONITOR_TOOL_ID
    
    # Read configuration from the caller's directory
    caller_frame = inspect.currentframe().f_back # type: ignore
    caller_dir = os.path.dirname(os.path.abspath(caller_frame.f_code.co_filename)) # type: ignore
    config_full_path = os.path.join(caller_dir, config_path)
    
    try:
        with open(config_full_path, 'r') as f:
            monitor_config = json.loads(f.read())
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found at: {config_full_path}")
    
    # Override output file if specified
    if output_file:
        monitor_config["output"]["file"] = output_file
    
    # Make output path relative to the caller's directory if it's not absolute
    if not os.path.isabs(monitor_config["output"]["file"]):
        monitor_config["output"]["file"] = os.path.join(
            caller_dir, 
            monitor_config["output"]["file"]
        )

    # Set up monitoring
    monitor_functions = monitor_config["monitor"]
    MONITOR_TOOL_ID = int(monitor_config["tool_id"])

    # Register monitoring callbacks
    sys.monitoring.use_tool_id(MONITOR_TOOL_ID, monitor_config["tool_name"])
    
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
    
    print(f"Monitoring initialized with tool '{monitor_config['tool_name']}'")
    print(f"Output file: {monitor_config['output']['file']}")

