"""
Functions for reanimating function executions from stored data.

This module provides functionality to load and replay function executions
that were previously monitored and stored by PyMonitor.
"""

import importlib
import os
import re
import sys
import types # Add types import
from typing import Any, Dict, List, Optional, Tuple, Union, cast, Callable
import datetime
import traceback
import logging # Add logging import

from . import init_db, FunctionCallTracker, ObjectManager
from .function_call import FunctionCallInfo
from . import models
from .monitoring import PyMonitoring

# Configure logging
logger = logging.getLogger(__name__)

def load_execution_data(function_execution_id: str, db_path: str) -> Tuple[List[Any], Dict[str, Any]]:
    """
    Load the function execution data for a given function execution ID.
    
    This function connects to the database, retrieves the function call data,
    and returns the arguments required to replay the function execution.
    
    Args:
        function_execution_id: The ID of the function execution to load
        db_path: Path to the database file containing the function execution data
        
    Returns:
        A tuple containing (args, kwargs) where:
        - args is a list of positional arguments
        - kwargs is a dictionary of keyword arguments
        
    Example:
        ```python
        import monitoringpy
        from my_module import my_function
        
        # Load the arguments for a specific function execution
        args, kwargs = monitoringpy.load_execution_data("123", "monitoring.db")
        
        # Replay the function with the same arguments
        result = my_function(*args, **kwargs)
        ```
    """
    # Initialize database connection
    Session = init_db(db_path)
    session = Session()
    
    try:
        # Create an ObjectManager to retrieve the stored objects
        obj_manager = ObjectManager(session)
        
        # Create a FunctionCallTracker
        call_tracker = FunctionCallTracker(session)
        
        # Get the function call details
        call_info = call_tracker.get_call(function_execution_id)
        
        # Rehydrate the locals dictionary
        locals_dict = obj_manager.rehydrate_dict(call_info['locals'])
        
        # We'll return all local variables as kwargs by default
        args = []
        kwargs = locals_dict
        
        # Try to get function code information to separate args from kwargs
        if call_info['code_definition_id'] is not None:
            code_content = call_info['code'].get('content', None) if call_info['code'] else None
            
            if code_content:
                # Try to identify function parameters
                # Look for def function_name(params): pattern
                match = re.search(r'def\s+([^(]+)\s*\(([^)]*)\)', code_content)
                if match:
                    param_str = match.group(2)
                    params = [p.strip() for p in param_str.split(',')]
                    
                    # Extract positional args based on parameter order
                    args = []
                    kwargs = {}
                    for param in params:
                        # Skip empty parameters
                        if not param:
                            continue
                            
                        # Handle default values
                        if '=' in param:
                            param_name = param.split('=')[0].strip()
                            if param_name in locals_dict:
                                kwargs[param_name] = locals_dict[param_name]
                        else:
                            # Remove any type annotations
                            if ':' in param:
                                param_name = param.split(':')[0].strip()
                            else:
                                param_name = param.strip()
                                
                            # Skip self/cls parameter for methods
                            if param_name in ('self', 'cls'):
                                continue
                                
                            if param_name in locals_dict:
                                args.append(locals_dict[param_name])
        
        return args, kwargs
        
    finally:
        # Close the session
        session.close()


def reanimate_function(function_execution_id: str, db_path: str, 
                       import_path: Optional[str] = None, ignore_globals: Optional[List[str]] = None) -> Any:
    """
    Reanimate a function execution from its stored data.
    
    This function loads the function execution data, imports the target function,
    and executes it with the same arguments as the original execution.
    
    Args:
        function_execution_id: The ID of the function execution to reanimate
        db_path: Path to the database file containing the function execution data
        import_path: Optional path to add to sys.path before importing (useful for importing from specific directories)
        ignore_globals: Optional list of global variables to ignore (useful for ignoring built-in variables)
    Returns:
        The result of the function execution
        
    Example:
        ```python
        import monitoringpy
        
        # Reanimate a function execution
        result = monitoringpy.reanimate_function("123", "monitoring.db", "/path/to/module/directory")
        print(f"Result: {result}")
        ```
    """
    # Initialize database connection for reading
    Session = init_db(db_path)
    session = Session()
    
    # Get the monitor instance to temporarily disable recording
    monitor_instance = PyMonitoring.get_instance()
    original_recording_state = None
    
    try:
        # Disable recording if monitor exists
        if monitor_instance:
            original_recording_state = monitor_instance.is_recording_enabled
            monitor_instance.is_recording_enabled = False
            
        # Create a FunctionCallTracker for reading data
        call_tracker = FunctionCallTracker(session) # Use the read-only session
        obj_manager = ObjectManager(session) # Use the read-only session
        
        # Get the function call details
        call_info = call_tracker.get_call(function_execution_id)
        
        # Get function name
        function_name = call_info['function']
        
        # Get file path where the function is defined
        file_path = call_info['file']
        
        if not file_path:
            raise ValueError(f"Could not determine file path for function {function_name}")
        
        # Add the import path to sys.path if provided
        if import_path:
            if import_path not in sys.path:
                sys.path.insert(0, import_path)
        
        # Get the module path from the file path
        
        if file_path.endswith('.py'):
            # Convert file path to module path
            file_dir = os.path.dirname(file_path)
            module_name = os.path.basename(file_path)[:-3]  # Remove .py extension
            
            # Ensure the directory is in sys.path
            if file_dir and file_dir not in sys.path and os.path.exists(file_dir):
                sys.path.insert(0, file_dir)
                
            # Check if the module is already imported
            if module_name in sys.modules:

                #reload the module
                importlib.reload(sys.modules[module_name])
                module = sys.modules[module_name]
            else:
                module = importlib.import_module(module_name)
            
        else:
            # If we can't determine the module path, look for the module path in code info
            module_path = call_info['code'].get('module_path') if call_info['code'] else None
            
            if not module_path:
                raise ValueError(f"Could not determine module path for function {function_name}")
                
            # Import the module
            module = importlib.import_module(module_path)
        
        # --- Get Function Object --- 
        # 1. Get the function object from the currently loaded module
        try:
            function_from_disk = getattr(module, function_name)
            if not callable(function_from_disk):
                 raise AttributeError(f"Attribute '{function_name}' in module '{module.__name__}' is not callable.")
        except AttributeError:
             raise ValueError(f"Could not find function '{function_name}' in module '{module.__name__}'. Cannot proceed with reanimation.")

        # 2. Try to create a function using historical code from DB
        code_def_id = call_info.get('code_definition_id')
        reanimated_function = None # Initialize
        historical_code_obj = None

        if code_def_id:
            code_def = session.get(models.CodeDefinition, code_def_id)
            if code_def and code_def.code_content:
                try:
                    # Compile the stored code string
                    filename = cast(str, code_def.name) if (code_def and code_def.name) else '<string_from_db>'
                    # Compile in 'exec' mode initially as it contains the function def
                    historical_code_obj = compile(cast(str, code_def.code_content), filename, 'exec')
                    
                    # Find the actual function code object within the compiled code
                    # (Assuming the stored code is just the function definition)
                    func_code = None
                    for const in historical_code_obj.co_consts:
                        if isinstance(const, types.CodeType) and const.co_name == function_name:
                            func_code = const
                            break
                            
                    if func_code:
                        # --- Direct Modification Approach --- 
                        # Directly replace the code object of the function loaded from disk
                        function_from_disk.__code__ = func_code
                        logger.info(f"Successfully replaced code for function '{function_name}' with historical code from definition {code_def_id}")
                        # No need to create a new function object
                        # reanimated_function = None # Keep this None or remove
                    else:
                         logger.warning(f"Could not find function code object named '{function_name}' within compiled historical code {code_def_id}. Using disk version.")
                         # Fallback handled below

                except SyntaxError as compile_err:
                    logger.error(f"Syntax error compiling stored code for call {function_execution_id} (ID: {code_def_id}): {compile_err}")
                    # Fallback handled below
                except Exception as e:
                    logger.error(f"Error processing historical code {code_def_id} for call {function_execution_id}: {e}")
                    # Fallback handled below
            else:
                logger.warning(f"Could not find CodeDefinition or code_content for ID {code_def_id} associated with call {function_execution_id}.")

        # 3. Use the function from disk (potentially modified)
        function_to_execute = function_from_disk
        # --- End Get Function Object ---

        # Load the execution data (args, kwargs)
        args, kwargs = _load_execution_data_from_info(call_info, obj_manager)
        
        # Load globals (needed for injection)
        globals_dict = _load_globals_from_info(call_info, obj_manager, ignore_globals)
        
        # Inject globals into module (if loaded) and the EXECUTION function context
        # NOTE: We inject into function_to_execute.__globals__ which might 
        #       already be the same dict as function_from_disk.__globals__
        _inject_globals(module, function_to_execute, globals_dict)

        # Execute the chosen function (monitor is disabled)
        result = function_to_execute(*args, **kwargs)
        return result
        
    finally:
        # Restore original recording state if it was changed
        if monitor_instance and original_recording_state is not None:
            monitor_instance.is_recording_enabled = original_recording_state
            
        # Close the read-only session
        session.close() 

def load_snapshot(snapshot_id: str, db_path: str) -> Dict[str, Any]:
    """
    Load the snapshot data for a given snapshot ID.
    
    This function connects to the database, retrieves the stack snapshot data,
    and returns the locals and globals dictionaries from that snapshot.
    
    Args:
        snapshot_id: The ID of the stack snapshot to load
        db_path: Path to the database file containing the snapshot data
        
    Returns:
        A dictionary containing the following keys:
        - 'locals': Dictionary of local variables
        - 'globals': Dictionary of global variables
        
    Example:
        ```python
        import monitoringpy
        
        # Load a specific snapshot
        snapshot_data = monitoringpy.load_snapshot("123", "monitoring.db")
        
        # Access the local and global variables
        local_vars = snapshot_data['locals']
        global_vars = snapshot_data['globals']
        ```
    """
    # Initialize database connection
    Session = init_db(db_path)
    session = Session()
    
    try:
        # Create an ObjectManager to retrieve the stored objects
        obj_manager = ObjectManager(session)
        
        # Query the StackSnapshot table for the given ID
        snapshot = session.query(models.StackSnapshot).filter_by(id=snapshot_id).first()
        
        if not snapshot:
            raise ValueError(f"Snapshot with ID {snapshot_id} not found")
        
        # Rehydrate the locals and globals dictionaries
        locals_dict = obj_manager.rehydrate_dict(snapshot.locals_refs)
        globals_dict = obj_manager.rehydrate_dict(snapshot.globals_refs)
        
        return {
            'locals': locals_dict,
            'globals': globals_dict
        }
        
    finally:
        # Close the session
        session.close()


def load_snapshot_in_frame(snapshot_id: str, db_path: str, frame=None) -> None:
    """
    Load a snapshot directly into the provided frame's locals and globals dictionaries.
    
    This function connects to the database, retrieves the stack snapshot data,
    and updates the provided frame's local and global variables with the values from the snapshot.
    
    Args:
        snapshot_id: The ID of the stack snapshot to load
        db_path: Path to the database file containing the snapshot data
        frame: The frame to update (defaults to the current frame if None)
        
    Returns:
        None
        
    Example:
        ```python
        import monitoringpy
        import inspect
        
        # Load a snapshot directly into the current execution frame
        monitoringpy.load_snapshot_in_frame("123", "monitoring.db", inspect.currentframe())
        
        # Now all local variables from the snapshot are available in the current scope
        ```
    """
    import inspect
    
    # Use current frame if none provided
    if frame is None:
        current_frame = inspect.currentframe()
        if current_frame is not None:
            frame = current_frame.f_back
    
    # Validate that we have a valid frame
    if frame is None:
        raise ValueError("No valid frame was provided or could be determined")
    
    # Get the frame's locals and globals dictionaries
    frame_locals = frame.f_locals
    frame_globals = frame.f_globals
    
    # Load the snapshot data
    snapshot_data = load_snapshot(snapshot_id, db_path)
    
    # Update the frame's locals with the snapshot's locals
    frame_locals.update(snapshot_data['locals'])
    
    # Update the frame's globals with the snapshot's globals
    # Only update globals that don't conflict with builtins or module-level constants
    for key, value in snapshot_data['globals'].items():
        # Skip updating certain globals that might cause issues
        if not (key.startswith('__') and key.endswith('__')):
            frame_globals[key] = value
    
    # Force update of the frame locals (needed in some Python implementations)
    # This uses ctypes to access CPython internals safely
    try:
        import ctypes
        ctypes.pythonapi.PyFrame_LocalsToFast(
            ctypes.py_object(frame),
            ctypes.c_int(0)
        )
    except (ImportError, AttributeError):
        # If ctypes is not available or PyFrame_LocalsToFast doesn't exist,
        # we've done our best with the frame.f_locals.update() above
        pass 

def run_with_state(function_execution_id: str, db_path: str, 
                  module_name: Optional[str] = None,
                  ignore_globals: Optional[List[str]] = None) -> Any:
    """
    Load global state from a specific function execution and run the script 
    where that function was defined with the loaded state.
    
    This function loads the global variables from a tracked function execution,
    locates the script where the function was originally defined,
    imports that script as a module, applies the loaded globals,
    and executes the module.
    
    Args:
        function_execution_id: The ID of the function execution to load state from
        db_path: Path to the database file containing execution data
        module_name: Optional name to use for the imported module
        ignore_globals: Optional list of global variables to ignore
        
    Returns:
        The loaded module after execution
        
    Example:
        ```python
        import monitoringpy
        
        # After modifying the script where the original function lives
        modified_module = monitoringpy.run_with_state(
            "specific_execution_id", 
            "monitoring.db"
        )
        ```
    """
    # Initialize database connection
    Session = init_db(db_path)
    session = Session()
    
    try:
        # Create required trackers and managers
        call_tracker = FunctionCallTracker(session)
        obj_manager = ObjectManager(session)
        
        # Get function call details
        call_info = call_tracker.get_call(function_execution_id)
        
        # Get file path where the function is defined
        script_path = call_info['file']
        if not script_path or not os.path.exists(script_path):
             # Try to get from code info if file path not directly available or invalid
            code_definition_id = call_info.get('code_definition_id')
            if code_definition_id:
                 code_def = session.query(models.CodeDefinition).get(code_definition_id)
                 if code_def and code_def.file and os.path.exists(code_def.file):
                     script_path = code_def.file
                 else:
                     raise ValueError(f"Could not determine a valid script path from code definition for function execution {function_execution_id}")
            else:
                raise ValueError(f"Could not determine a valid script path for function execution {function_execution_id}")


        # Load global state
        if ignore_globals:
            globals_dict = obj_manager.rehydrate_dict(
                {k: v for k, v in call_info['globals'].items() if k not in ignore_globals}
            )
        else:
            globals_dict = obj_manager.rehydrate_dict(call_info['globals'])
        
        # Import the script as a module with the loaded globals
        import importlib.util
        
        print(f"Importing script from {script_path}")
        
        # Determine module name if not provided
        if not module_name:
            # Try to get module path from call info first
            code_info = call_info.get('code')
            module_path_from_info = code_info.get('module_path') if code_info else None
            if module_path_from_info:
                 module_name = module_path_from_info
            else:
                 # Fallback to deriving from script path
                 basename = os.path.basename(script_path)
                 if basename.endswith('.py'):
                      module_name = basename[:-3] # Remove .py extension
                 else:
                      module_name = basename # Use basename as is if no .py extension
        
        # Ensure module_name is a valid string
        if not module_name:
             raise ValueError(f"Could not determine a valid module name for script {script_path}")

        # Add script directory to path if necessary to allow relative imports within the script
        script_dir = os.path.dirname(script_path)
        if script_dir and script_dir not in sys.path:
             sys.path.insert(0, script_dir)

        # Create spec and module
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load script from {script_path}")
            
        module = importlib.util.module_from_spec(spec)
        
        # Add the module to sys.modules to handle imports correctly
        sys.modules[module_name] = module
        
        # Apply globals to the module
        # Filter out builtins potentially captured in globals to avoid overriding them
        filtered_globals = {k: v for k, v in globals_dict.items() if not (k.startswith('__') and k.endswith('__'))}
        module.__dict__.update(filtered_globals)
        
        # Execute the module with loaded globals
        spec.loader.exec_module(module)
        
        return module
    finally:
        # Close the session
        session.close() 

# Helper function (can be moved elsewhere if preferred)
def _load_or_reload_function_and_module(call_info: FunctionCallInfo, 
                                         loaded_modules_cache: Dict[str, Any], 
                                         reload_module: bool = True) -> Tuple[Callable, Any]:
    """Loads/reloads module and gets function object based on call_info."""
    function_name = call_info['function']
    file_path = call_info['file']
    # Safely get module_path, handling if 'code' key exists but is None
    code_info = call_info.get('code') # Get 'code' dict or None
    module_path_from_info = code_info.get('module_path') if code_info else None
    module = None
    module_key = None # Use file_path or module_path as key

    # Prioritize file_path if it exists
    if file_path and file_path.endswith('.py') and os.path.exists(file_path):
        module_key = file_path
        if module_key in loaded_modules_cache:
            module = loaded_modules_cache[module_key]
        else:
            file_dir = os.path.dirname(file_path)
            module_name_from_path = os.path.basename(file_path)[:-3]
            if file_dir and file_dir not in sys.path:
                sys.path.insert(0, file_dir)

            # Check if already imported, reload if requested
            if module_name_from_path in sys.modules and reload_module:
                module = importlib.reload(sys.modules[module_name_from_path])
            elif module_name_from_path in sys.modules:
                 module = sys.modules[module_name_from_path]
            else:
                module = importlib.import_module(module_name_from_path)
            
            if module:
                 loaded_modules_cache[module_key] = module

    # Fallback to module_path from code info
    elif module_path_from_info:
        module_key = module_path_from_info
        if module_key in loaded_modules_cache:
            module = loaded_modules_cache[module_key]
        else:
            if module_path_from_info in sys.modules and reload_module:
                module = importlib.reload(sys.modules[module_path_from_info])
            elif module_path_from_info in sys.modules:
                 module = sys.modules[module_path_from_info]
            else:
                module = importlib.import_module(module_path_from_info)
            
            if module:
                 loaded_modules_cache[module_key] = module

        if not module:
            raise ValueError(f"Could not load module for function '{function_name}'. Checked file '{file_path}' and module path '{module_path_from_info}'.")

    # Handle qualified names (e.g., Class.method)
    func_parts = function_name.split('.')
    obj = module
    try:
        for part in func_parts:
            obj = getattr(obj, part)
        function = obj
    except AttributeError:
         # Check if module exists before accessing __name__
         module_name_str = module.__name__ if module else "<unknown module>"
         raise ValueError(f"Could not find function/method '{function_name}' in module '{module_name_str}'.")
         
    if not callable(function):
         raise ValueError(f"Attribute '{function_name}' found but is not callable.")

    return function, module

# Helper function
def _load_execution_data_from_info(call_info: FunctionCallInfo, obj_manager: ObjectManager) -> Tuple[List[Any], Dict[str, Any]]:
    """Rehydrates args and kwargs from call_info locals."""
    locals_dict = obj_manager.rehydrate_dict(call_info.get('locals', {}))
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}
    
    # Basic reconstruction (improve later if needed based on function signature)
    # For now, assume all non-arg-looking keys are kwargs, others are args.
    # This is a simplification and might need refinement based on actual function def.
    
    # A more robust way would parse the signature from call_info['code']['content']
    # but let's start simple.
    
    # Simple approach: return all as kwargs for now
    kwargs = locals_dict
    args = [] 
    
    # Example refinement (requires parsing signature): 
    # param_names = parse_signature(call_info.get('code', {}).get('content')) 
    # for name in param_names:
    #     if name in locals_dict:
    #          args.append(locals_dict.pop(name))
    # kwargs = locals_dict # Remaining are kwargs

    return args, kwargs

# Helper function
def _load_globals_from_info(call_info: FunctionCallInfo, obj_manager: ObjectManager, 
                            ignore_globals: Optional[List[str]]) -> Dict[str, Any]:
    """Rehydrates and filters globals from call_info."""
    globals_dict = obj_manager.rehydrate_dict(call_info.get('globals', {}))
    filtered_globals = {
        k: v for k, v in globals_dict.items()
        if not (k.startswith('__') and k.endswith('__')) and \
            not (ignore_globals and k in ignore_globals)
    }
    return filtered_globals

# Helper function
def _inject_globals(module: Any, function: Callable, globals_dict: Dict[str, Any]):
    """Injects globals into module and function context."""
    if module:
        module.__dict__.update(globals_dict)
    
    if function:
        try:
            # Update the function's own __globals__ dict as well
            function.__globals__.update(globals_dict)
        except (AttributeError, TypeError) as e:
             print(f"Warning: Could not update __globals__ for function {getattr(function, '__name__', '<unknown>')}: {e}")

def replay_session_from(
    starting_function_id: int, 
    db_path: str,
    ignore_globals: Optional[List[str]] = None
) -> Optional[int]:
    """
    Replays a monitoring session sequence starting from a specific function call,
    recording the new execution path linked to the original.

    Loads the state (code, globals) once at the start, then executes the 
    original function call sequence, loading only locals for each subsequent call.
    The new execution is recorded by the active PyMonitoring instance.

    Args:
        starting_function_id: The integer ID of the function execution within the
                               original session to start the replay from.
        db_path: Path to the database file.
        ignore_globals: Optional list of global variable names to ignore when
                        loading the initial state.

    Returns:
        The integer ID of the first function call recorded in the new replay 
        sequence, or None if replay fails.

    Raises:
        ValueError: If IDs not found, function/module fails to load, etc.
        RuntimeError: If PyMonitoring instance is not available.
    """
    monitor_instance = PyMonitoring.get_instance()
    if not monitor_instance or not monitor_instance.session:
        raise RuntimeError("PyMonitoring is not initialized or has no active session. Cannot replay session.")

    # Use a separate session for reading original data to avoid conflicts
    ReadSession = init_db(db_path)
    read_session = ReadSession()
    
    # Cache for loaded modules during replay
    loaded_modules_cache: Dict[str, Any] = {}
    first_replayed_call_id: Optional[int] = None
    # We need ObjectManager associated with the read session
    read_obj_manager = ObjectManager(read_session) 
    # We need CallTracker associated with the read session
    read_call_tracker = FunctionCallTracker(read_session)

    # Backup monitor state (optional, but good practice)
    original_parent_id_for_next_call = monitor_instance._parent_id_for_next_call

    try:
        # 1. Load Starting State (using read_session)
        print(f"Loading starting function call info: {starting_function_id}")
        start_call_info = read_call_tracker.get_call(str(starting_function_id))
        if not start_call_info:
            raise ValueError(f"Function execution ID {starting_function_id} not found in db: {db_path}")

        # 2. Load Starting Function Object (load/reload module ONCE)
        print("Loading starting function and module...")
        start_function, start_module = _load_or_reload_function_and_module(
            start_call_info, loaded_modules_cache, reload_module=True
        )
        print(f"Loaded starting function: {start_function.__name__} from module {start_module.__name__}")

        # 3. Load Starting Args & Globals
        print("Loading starting arguments and globals...")
        start_args, start_kwargs = _load_execution_data_from_info(start_call_info, read_obj_manager)
        current_globals = _load_globals_from_info(start_call_info, read_obj_manager, ignore_globals)
        print(f"Loaded {len(start_args)} args, {len(start_kwargs)} kwargs, {len(current_globals)} globals.")

        # 4. Inject Initial Globals
        _inject_globals(start_module, start_function, current_globals)

        # --- Start Replay Execution --- 
        
        # 5. Execute First Call (monitor will record)
        print(f"Setting parent ID for next call to: {starting_function_id}")
        monitor_instance._parent_id_for_next_call = starting_function_id 
        
        print(f"Executing first replay call: {start_function.__name__}...")
        start_function(*start_args, **start_kwargs) # Execution happens here
        
        # Check if the call was actually recorded by the monitor
        first_replayed_call_id = monitor_instance._current_session_last_call_id
        if monitor_instance._parent_id_for_next_call is not None: 
             # This means the flag wasn't reset by monitor_callback_function_start, 
             # likely because the function wasn't monitored or capture_call failed.
             monitor_instance._parent_id_for_next_call = None # Reset anyway
             raise RuntimeError(f"First function call '{start_function.__name__}' was executed but not recorded by the monitor. Aborting replay.")
        
        print(f"First replayed call recorded with ID: {first_replayed_call_id}")
        
        # 6. Loop through subsequent original calls
        original_current_call_id: Optional[int] = starting_function_id
        while original_current_call_id is not None:
            # Get the *next* call ID from the *original* sequence (using read_session)
            original_call = read_session.get(models.FunctionCall, original_current_call_id)
            if not original_call:
                 print(f"Warning: Could not find original call {original_current_call_id} in read session.")
                 break 
            
            original_next_call_id = original_call.next_call_id
            if not original_next_call_id:
                 print("Reached end of original sequence.")
                 break # End of original chain

            print(f"Processing next original call ID: {original_next_call_id}")

            # Fetch details of the next original call
            next_call_info = read_call_tracker.get_call(str(original_next_call_id))
            if not next_call_info:
                 print(f"Warning: Could not get call info for original call {original_next_call_id}")
                 original_current_call_id = original_next_call_id # Skip to next potential
                 continue

            # Load function object (DO NOT reload module)
            try:
                 next_function, next_module = _load_or_reload_function_and_module(
                     next_call_info, loaded_modules_cache, reload_module=False
                 )
            except Exception as load_exc:
                 print(f"Error loading function/module for call {original_next_call_id}: {load_exc}. Skipping call.")
                 original_current_call_id = original_next_call_id
                 continue

            # Load LOCALS ONLY for this call
            try:
                 next_args, next_kwargs = _load_execution_data_from_info(next_call_info, read_obj_manager)
            except Exception as locals_exc:
                 print(f"Error loading locals for call {original_next_call_id}: {locals_exc}. Skipping call.")
                 original_current_call_id = original_next_call_id
                 continue

            # Execute the next function (monitor records it, linking automatically)
            print(f"Executing next replay call: {next_function.__name__}...")
            try:
                 next_function(*next_args, **next_kwargs)
                 print(f"Call {original_next_call_id} replayed successfully.")
            except Exception as exec_exc:
                 print(f"Error executing replayed call for original ID {original_next_call_id} ('{next_function.__name__}'): {exec_exc}")
                 print("Stopping replay sequence due to execution error.")
                 # Log the error in the *last recorded* function call maybe?
                 # For now, just break the loop.
                 break 

            # Move to the next call in the original sequence for the next iteration
            original_current_call_id = original_next_call_id

        # --- End Replay Loop ---

        # 7. Commit monitor session to save all recorded calls from the replay
        print(f"Committing monitor session to save replayed calls (starting from {first_replayed_call_id}).")
        monitor_instance.session.commit()
        print("Replay sequence committed.")

        return first_replayed_call_id # Return ID of the start of the new branch

    except Exception as e:
        print(f"Error during session replay: {e}")
        traceback.print_exc() # Print full traceback for debugging
        # Rollback the *main* monitor session to undo potential partial recordings
        try:
            monitor_instance.session.rollback()
            print("Rolled back main monitoring session due to error.")
        except Exception as rb_err:
             print(f"Error rolling back main monitoring session: {rb_err}")
        return None # Indicate failure
    finally:
        # Restore monitor state if backed up
        monitor_instance._parent_id_for_next_call = original_parent_id_for_next_call
        # Close the separate read session
        read_session.close()
        print("Replay function finished.") 