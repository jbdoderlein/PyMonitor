"""
Functions for reanimating function executions from stored data.

This module provides functionality to load and replay function executions
that were previously monitored and stored by PyMonitor.
"""

import importlib
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from . import init_db, FunctionCallTracker, ObjectManager
from . import models


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
                       import_path: Optional[str] = None) -> Any:
    """
    Reanimate a function execution from its stored data.
    
    This function loads the function execution data, imports the target function,
    and executes it with the same arguments as the original execution.
    
    Args:
        function_execution_id: The ID of the function execution to reanimate
        db_path: Path to the database file containing the function execution data
        import_path: Optional path to add to sys.path before importing (useful for importing from specific directories)
        
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
    # Initialize database connection
    Session = init_db(db_path)
    session = Session()
    
    try:
        # Create a FunctionCallTracker
        call_tracker = FunctionCallTracker(session)
        obj_manager = ObjectManager(session)
        
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
                print(f"Reloading module {module_name} from {file_dir}")

                #reload the module
                importlib.reload(sys.modules[module_name])
                module = sys.modules[module_name]
            else:
                print(f"Importing module {module_name} from {file_dir}")
                module = importlib.import_module(module_name)
            
        else:
            # If we can't determine the module path, look for the module path in code info
            module_path = call_info['code'].get('module_path') if call_info['code'] else None
            
            if not module_path:
                raise ValueError(f"Could not determine module path for function {function_name}")
                
            # Import the module
            module = importlib.import_module(module_path)
        
        # Get the function object
        function = getattr(module, function_name)
        
        # Load the execution data
        args, kwargs = load_execution_data(function_execution_id, db_path)

        # init the global variables
        globals_dict = obj_manager.rehydrate_dict(call_info['globals'])
        for key, value in globals_dict.items():
            setattr(module, key, value)
        # Set the function's globals to the rehydrated globals
        # This is a workaround for Python's function closure behavior
        # and may not work in all cases
        function.__globals__.update(globals_dict)
        

        
        # Execute the function
        return function(*args, **kwargs)
        
    finally:
        # Close the session
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