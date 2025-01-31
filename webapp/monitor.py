import inspect
import types
import sys
import jsonpickle
import dis
import json
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


# Monitoring part
# Monitoring setup
def monitor_callback_function_start(code : types.CodeType, offset):
    # on if from this file
    filename = code.co_filename.split("/")[-1]
    if filename in monitor_functions and code.co_name in monitor_functions[filename]: # if the function is monitored
        #Extract arguments from the function call
        current_frame = inspect.currentframe()
        if current_frame is None:
            return  
        if current_frame.f_back is None:
            return
        args = inspect.getargvalues(current_frame.f_back)
        json_trace = {
            "file": code.co_filename,
            "function": code.co_name,
            "locals": dict(args.locals).copy(),
            "globals": get_used_globals(code, current_frame.f_back.f_globals)
        }
        if "request" in json_trace["globals"]:
            print("request in monitor", json_trace["globals"]["request"])
            #print(jsonpickle.encode(json_trace["globals"]["request"]))
        trace_str = jsonpickle.encode(json_trace,fail_safe=(lambda e: None))
        if trace_str is not None:
            with open(monitor_config["output"]["file"], "a") as f:
                f.write(trace_str)
                f.write("\n")
    
        


sys.monitoring.register_callback(
    MONITOR_TOOL_ID,
    sys.monitoring.events.PY_START,
    monitor_callback_function_start
)
sys.monitoring.set_events(
    MONITOR_TOOL_ID, 
    sys.monitoring.events.PY_START
)
