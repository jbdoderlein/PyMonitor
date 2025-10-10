"""
Functions for reanimating function executions from stored data.

This module provides functionality to load and replay function executions
that were previously monitored and stored by PyMonitor.
"""

import importlib
import logging  # Add logging import
import os
import re
import sys
import traceback
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from . import models
from .function_call import FunctionCallRepository
from .models import init_db
from .monitoring import PyMonitoring
from .representation import ObjectManager

# Configure logging
logger = logging.getLogger(__name__)

# Add the src directory to the path so we can import our modules
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, "..", "..")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)


@contextmanager
def get_db_session(db_path_or_session: str | Any):
    """
    Context manager that yields a database session.

    Args:
        db_path_or_session: Either a string path to the database file,
                           or an existing SQLAlchemy session object

    Yields:
        A database session object

    Example:
        ```python
        # Using with a database path
        with get_db_session("monitoring.db") as session:
            # Use session here
            pass

        # Using with an existing session
        with get_db_session(existing_session) as session:
            # session is the same as existing_session, no cleanup needed
            pass
        ```
    """
    if isinstance(db_path_or_session, str):
        # It's a database path, create a new session
        Session = init_db(db_path_or_session)
        session = Session()
        try:
            yield session
        finally:
            session.close()
    else:
        # It's already a session object, just yield it
        # Don't close it since we didn't create it
        yield db_path_or_session


def load_execution_data(
    function_execution_id: str, db_path_or_session: str | Any
) -> tuple[list[Any], dict[str, Any]]:
    """
    Load the function execution data for a given function execution ID.

    This function connects to the database, retrieves the function call data,
    and returns the arguments required to replay the function execution.

    Args:
        function_execution_id: The ID of the function execution to load
        db_path_or_session: Either a string path to the database file,
                           or an existing SQLAlchemy session object

    Returns:
        A tuple containing (args, kwargs) where:
        - args is a list of positional arguments
        - kwargs is a dictionary of keyword arguments

    Example:
        ```python
        import spacetimepy
        from my_module import my_function

        # Load the arguments for a specific function execution
        args, kwargs = spacetimepy.load_execution_data("123", "monitoring.db")

        # Replay the function with the same arguments
        result = my_function(*args, **kwargs)
        ```
    """
    with get_db_session(db_path_or_session) as session:
        # Create an ObjectManager to retrieve the stored objects
        obj_manager = ObjectManager(session)

        # Create a FunctionCallRepository
        call_repository = FunctionCallRepository(session)

        # Get the function call details
        call_info = call_repository.get_call_with_code(function_execution_id)

        if not call_info:
            raise ValueError(f"Function execution ID {function_execution_id} not found")

        return _load_execution_data_from_call_info(
            call_info, obj_manager, use_signature_parsing=True
        )


def execute_function_call(
    function_execution_id: str,
    db_path_or_session: str | Any,
    import_path: str | None = None,
    ignore_globals: list[str] | None = None,
    mock_function: list[str] = [],
    enable_monitoring: bool = False,
    reload_module: bool = True,
    additional_decorators: list[Callable] | None = None,
) -> Any:
    """
    Execute a single function call from its stored data.

    This function loads the function execution data, imports the target function,
    and executes it with the same arguments as the original execution.

    Args:
        function_execution_id: The ID of the function execution to execute
        db_path: Path to the database file containing the function execution data
        import_path: Optional path to add to sys.path before importing
        ignore_globals: Optional list of global variables to ignore
        mock_function: Optional list of functions to mock
        enable_monitoring: Whether to enable monitoring during execution (default: False)

    Returns:
        The result of the function execution

    Example:
        ```python
        import spacetimepy

        # Execute a function call without monitoring
        result = spacetimepy.execute_function_call("123", "monitoring.db")

        # Execute with monitoring enabled
        result = spacetimepy.execute_function_call("123", "monitoring.db", enable_monitoring=True)
        ```
    """
    with get_db_session(db_path_or_session) as session:
        # Get the monitor instance to control recording
        monitor_instance = PyMonitoring.get_instance()
        original_recording_state = None

        try:
            # Control recording based on enable_monitoring parameter
            if monitor_instance and not enable_monitoring:
                original_recording_state = monitor_instance.is_recording_enabled
                monitor_instance.is_recording_enabled = False

            # Create a FunctionCallRepository for reading data
            call_repository = FunctionCallRepository(session)
            obj_manager = ObjectManager(session)

            # Get the function call details
            call_info = call_repository.get_call_with_code(function_execution_id)

            if not call_info:
                raise ValueError(
                    f"Function execution ID {function_execution_id} not found"
                )

            # Get function name and file path
            function_name = call_info["function"]
            file_path = call_info["file"]

            logger.info(f"Replaying function {function_name} from {file_path}")

            if not file_path:
                raise ValueError(
                    f"Could not determine file path for function {function_name}"
                )

            # Add the import path to sys.path if provided
            if import_path and import_path not in sys.path:
                    sys.path.insert(0, import_path)

            # Load the function and module using the helper
            loaded_modules_cache: dict[str, Any] = {}
            function_obj, module = _load_or_reload_function_and_module(
                call_info, loaded_modules_cache, reload_module=reload_module
            )

            # FIX: Ensure classes are available for unpickling before loading execution data
            _ensure_class_availability_for_unpickling(obj_manager, module)

            # Load the execution data (args, kwargs)
            args, kwargs = _load_execution_data_from_call_info(call_info, obj_manager)

            # Load globals (needed for injection)
            globals_dict = _load_globals_from_call_info(
                call_info, obj_manager, ignore_globals
            )

            # Inject globals into module and function context
            _inject_globals(module, function_obj, globals_dict)

            # Mock functions if provided
            _load_mock_functions(session, function_execution_id, obj_manager, module, mock_function)

            if additional_decorators:
                for decorator in additional_decorators:
                    function_obj = decorator(function_obj)
            # Execute the function
            result = function_obj(*args, **kwargs)

            # Restore the original functions
            for func_name in mock_function:
                if func_name in module.__dict__:
                    module.__dict__[func_name] = module.__dict__[f"_old_{func_name}"]
                    del module.__dict__[f"_old_{func_name}"]
            return result

        finally:
            # Restore original recording state if it was changed
            if monitor_instance and original_recording_state is not None:
                monitor_instance.is_recording_enabled = original_recording_state


def load_snapshot(
    snapshot_id: str, db_path_or_session: str | Any
) -> dict[str, Any]:
    """
    Load the snapshot data for a given snapshot ID.

    This function connects to the database, retrieves the stack snapshot data,
    and returns the locals and globals dictionaries from that snapshot.

    Args:
        snapshot_id: The ID of the stack snapshot to load
        db_path_or_session: Either a string path to the database file,
                           or an existing SQLAlchemy session object

    Returns:
        A dictionary containing the following keys:
        - 'locals': Dictionary of local variables
        - 'globals': Dictionary of global variables

    Example:
        ```python
        import spacetimepy

        # Load a specific snapshot
        snapshot_data = spacetimepy.load_snapshot("123", "monitoring.db")

        # Access the local and global variables
        local_vars = snapshot_data['locals']
        global_vars = snapshot_data['globals']
        ```
    """
    with get_db_session(db_path_or_session) as session:
        # Create an ObjectManager to retrieve the stored objects
        obj_manager = ObjectManager(session)

        # Query the StackSnapshot table for the given ID
        snapshot = session.query(models.StackSnapshot).filter_by(id=snapshot_id).first()

        if not snapshot:
            raise ValueError(f"Snapshot with ID {snapshot_id} not found")

        # Rehydrate the locals and globals dictionaries
        locals_refs = getattr(snapshot, "locals_refs", {}) if snapshot else {}
        globals_refs = getattr(snapshot, "globals_refs", {}) if snapshot else {}
        locals_dict = obj_manager.rehydrate_dict(locals_refs)
        globals_dict = obj_manager.rehydrate_dict(globals_refs)

        return {"locals": locals_dict, "globals": globals_dict}


def load_snapshot_in_frame(
    snapshot_id: str, db_path_or_session: str | Any, frame=None
) -> None:
    """
    Load a snapshot directly into the provided frame's locals and globals dictionaries.

    This function connects to the database, retrieves the stack snapshot data,
    and updates the provided frame's local and global variables with the values from the snapshot.

    Args:
        snapshot_id: The ID of the stack snapshot to load
        db_path_or_session: Either a string path to the database file,
                           or an existing SQLAlchemy session object
        frame: The frame to update (defaults to the current frame if None)

    Returns:
        None

    Example:
        ```python
        import spacetimepy
        import inspect

        # Load a snapshot directly into the current execution frame
        spacetimepy.load_snapshot_in_frame("123", "monitoring.db", inspect.currentframe())

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
    snapshot_data = load_snapshot(snapshot_id, db_path_or_session)

    # Update the frame's locals with the snapshot's locals
    frame_locals.update(snapshot_data["locals"])

    # Update the frame's globals with the snapshot's globals
    # Only update globals that don't conflict with builtins or module-level constants
    for key, value in snapshot_data["globals"].items():
        # Skip updating certain globals that might cause issues
        if not (key.startswith("__") and key.endswith("__")):
            frame_globals[key] = value

    # Force update of the frame locals (needed in some Python implementations)
    # This uses ctypes to access CPython internals safely
    try:
        import ctypes

        ctypes.pythonapi.PyFrame_LocalsToFast(ctypes.py_object(frame), ctypes.c_int(0))
    except (ImportError, AttributeError):
        # If ctypes is not available or PyFrame_LocalsToFast doesn't exist,
        # we've done our best with the frame.f_locals.update() above
        pass


def run_with_state(
    function_execution_id: str,
    db_path_or_session: str | Any,
    module_name: str | None = None,
    ignore_globals: list[str] | None = None,
) -> Any:
    """
    Load global state from a specific function execution and run the script
    where that function was defined with the loaded state.

    This function loads the global variables from a tracked function execution,
    locates the script where the function was originally defined,
    imports that script as a module, applies the loaded globals,
    and executes the module.

    Args:
        function_execution_id: The ID of the function execution to load state from
        db_path_or_session: Either a string path to the database file,
                           or an existing SQLAlchemy session object
        module_name: Optional name to use for the imported module
        ignore_globals: Optional list of global variables to ignore

    Returns:
        The loaded module after execution

    Example:
        ```python
        import spacetimepy

        # After modifying the script where the original function lives
        modified_module = spacetimepy.run_with_state(
            "specific_execution_id",
            "monitoring.db"
        )
        ```
    """
    with get_db_session(db_path_or_session) as session:
        # Create required trackers and managers
        call_repository = FunctionCallRepository(session)
        obj_manager = ObjectManager(session)

        # Get function call details
        call_info = call_repository.get_call(function_execution_id)

        if not call_info:
            raise ValueError(f"Function execution ID {function_execution_id} not found")

        # Get file path where the function is defined
        script_path = call_info["file"]
        if not script_path or not os.path.exists(script_path):
            # Try to get from code info if file path not directly available or invalid
            code_definition_id = call_info.get("code_definition_id")
            if code_definition_id:
                code_def = session.query(models.CodeDefinition).get(code_definition_id)
                if code_def and code_def.file and os.path.exists(code_def.file):
                    script_path = code_def.file
                else:
                    raise ValueError(
                        f"Could not determine a valid script path from code definition for function execution {function_execution_id}"
                    )
            else:
                raise ValueError(
                    f"Could not determine a valid script path for function execution {function_execution_id}"
                )

        # Load global state
        globals_dict = _load_globals_from_call_info(
            call_info, obj_manager, ignore_globals
        )

        # Import the script as a module with the loaded globals
        import importlib.util

        logger.info(f"Importing script from {script_path}")

        # Determine module name if not provided
        if not module_name:
            # Try to get module path from call info first
            code_info = call_info.get("code")
            module_path_from_info = code_info.get("module_path") if code_info else None
            if module_path_from_info:
                module_name = module_path_from_info
            else:
                # Fallback to deriving from script path
                basename = os.path.basename(script_path)
                module_name = basename[:-3] if basename.endswith(".py") else basename

        # Ensure module_name is a valid string
        if not module_name:
            raise ValueError(
                f"Could not determine a valid module name for script {script_path}"
            )

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
        filtered_globals = {
            k: v
            for k, v in globals_dict.items()
            if not (k.startswith("__") and k.endswith("__"))
        }
        module.__dict__.update(filtered_globals)

        # Execute the module with loaded globals
        spec.loader.exec_module(module)

        return module


def replay_session_sequence(
    starting_function_id: int,
    db_path: str,
    ignore_globals: list[str] | None = None,
    enable_monitoring: bool = True,
    mock_functions: list[str] | None = None,
) -> int | None:
    """
    Replays a sequence of function calls from a monitoring session.

    Loads the state (code, globals) once at the start, then executes the
    original function call sequence, loading only locals for each subsequent call.
    The new execution can optionally be recorded by the active PyMonitoring instance.

    Args:
        starting_function_id: The integer ID of the function execution within the
                               original session to start the replay from.
        db_path: Path to the database file.
        ignore_globals: Optional list of global variable names to ignore when
                        loading the initial state.
        enable_monitoring: Whether to enable monitoring during replay (default: True)
        mock_functions: Optional list of function names to mock during replay
    Returns:
        The integer ID of the first function call recorded in the new replay
        sequence, or None if replay fails.

    Raises:
        ValueError: If IDs not found, function/module fails to load, etc.
        RuntimeError: If PyMonitoring instance is not available and monitoring is enabled.
    """
    monitor_instance = PyMonitoring.get_instance()
    if enable_monitoring and (not monitor_instance or not monitor_instance.session):
        raise RuntimeError(
            "PyMonitoring is not initialized or has no active session. Cannot replay with monitoring enabled."
        )

    if enable_monitoring and monitor_instance:
        read_session = monitor_instance.session
    else:
        ReadSession = init_db(db_path)
        read_session = ReadSession()

    # Cache for loaded modules during replay
    loaded_modules_cache: dict[str, Any] = {}
    first_replayed_call_id: int | None = None
    # We need ObjectManager associated with the read session
    read_obj_manager = ObjectManager(read_session)
    # We need FunctionCallRepository associated with the read session
    read_call_repository = FunctionCallRepository(read_session)

    # Backup monitor state (optional, but good practice)
    original_parent_id_for_next_call = None
    original_recording_state = None
    if monitor_instance:
        original_parent_id_for_next_call = monitor_instance._parent_id_for_next_call
        if not enable_monitoring:
            original_recording_state = monitor_instance.is_recording_enabled
            monitor_instance.is_recording_enabled = False

    try:
        # 1. Load Starting State (using read_session)
        logger.info(f"Loading starting function call info: {starting_function_id}")
        start_call_info = read_call_repository.get_call(str(starting_function_id))
        if not start_call_info:
            raise ValueError(
                f"Function execution ID {starting_function_id} not found in db: {db_path}"
            )

        # 2. Load Starting Function Object (load/reload module ONCE)
        logger.info(
            f"Loading starting function and module... :{start_call_info}, {loaded_modules_cache}"
        )
        start_function, start_module = _load_or_reload_function_and_module(
            start_call_info.to_dict(), loaded_modules_cache, reload_module=True
        )
        logger.info(
            f"Loaded starting function: {start_function.__name__} from module {start_module.__name__}"
        )

        # 3. Load Starting Args & Globals
        logger.info("Loading starting arguments and globals...")
        start_args, start_kwargs = _load_execution_data_from_call_info(
            start_call_info.to_dict(), read_obj_manager
        )
        current_globals = _load_globals_from_call_info(
            start_call_info.to_dict(), read_obj_manager, ignore_globals
        )
        logger.info(
            f"Loaded {len(start_args)} args, {len(start_kwargs)} kwargs, {len(current_globals)} globals."
        )

        # 4. Inject Initial Globals
        _inject_globals(start_module, start_function, current_globals)

        # 5. Mock Functions
        if mock_functions:
            _load_mock_functions(read_session, starting_function_id, read_obj_manager, start_module, mock_functions)

        # --- Start Replay Execution ---

        # 5. Execute First Call (monitor will record if enabled)
        if enable_monitoring and monitor_instance:
            logger.info(f"Setting parent ID for next call to: {starting_function_id}")
            monitor_instance._parent_id_for_next_call = starting_function_id

        logger.info(f"Executing first replay call: {start_function.__name__}...")
        start_function(*start_args, **start_kwargs)  # Execution happens here

        # Check if the call was actually recorded by the monitor (only if monitoring enabled)
        if enable_monitoring and monitor_instance:
            first_replayed_call_id = monitor_instance._current_session_last_call_id
            if monitor_instance._parent_id_for_next_call is not None:
                # This means the flag wasn't reset by monitor_callback_function_start,
                # likely because the function wasn't monitored or capture_call failed.
                monitor_instance._parent_id_for_next_call = None  # Reset anyway
                raise RuntimeError(
                    f"First function call '{start_function.__name__}' was executed but not recorded by the monitor. Aborting replay."
                )

            logger.info(f"First replayed call recorded with ID: {first_replayed_call_id}")

        # 6. Loop through subsequent original calls - use session ordering instead of next_call_id
        # Note: UI filtering is separate from replay execution
        original_current_call_id: int | None = starting_function_id
        while original_current_call_id is not None:
            # Get the current call from the *original* sequence (using read_session)
            original_call = read_session.get(
                models.FunctionCall, original_current_call_id
            )
            if not original_call:
                logger.warning(
                    f"Warning: Could not find original call {original_current_call_id} in read session."
                )
                break

            # Find the next call in the session sequence using order_in_session
            original_next_call_id = None
            if original_call.session_id is not None and original_call.order_in_session is not None:
                # Get the next call in the same session with the next order number
                next_call = read_session.query(models.FunctionCall).filter(
                    models.FunctionCall.session_id == original_call.session_id,
                    models.FunctionCall.function == original_call.function,
                    models.FunctionCall.order_in_session > original_call.order_in_session
                ).first()

                if next_call:
                    original_next_call_id = next_call.id

            if not original_next_call_id:
                logger.info("Reached end of original sequence.")
                break  # End of original chain

            logger.info(f"Processing next original call ID: {original_next_call_id}")

            # Fetch details of the next original call
            next_call_info = read_call_repository.get_call_with_code(str(original_next_call_id))
            if not next_call_info:
                logger.warning(
                    f"Warning: Could not get call info for original call {original_next_call_id}"
                )
                original_current_call_id = original_next_call_id  # Skip to next potential
                continue

            # Load function object (DO NOT reload module)
            try:
                next_function, next_module = _load_or_reload_function_and_module(
                    next_call_info, loaded_modules_cache, reload_module=False
                )
            except Exception as load_exc:
                logger.error(
                    f"Error loading function/module for call {original_next_call_id}: {load_exc}. Skipping call."
                )
                original_current_call_id = original_next_call_id
                continue

            # Load LOCALS ONLY for this call
            try:
                next_args, next_kwargs = _load_execution_data_from_call_info(
                    next_call_info, read_obj_manager
                )
            except Exception as locals_exc:
                logger.error(
                    f"Error loading locals for call {original_next_call_id}: {locals_exc}. Skipping call."
                )
                original_current_call_id = original_next_call_id
                continue

            # 7 . Inject mock functions
            if mock_functions:
                _load_mock_functions(read_session, original_next_call_id, read_obj_manager, next_module, mock_functions)

            # Execute the next function (monitor records it, linking automatically if enabled)
            logger.info(f"Executing next replay call: {next_function.__name__}...")
            try:
                next_function(*next_args, **next_kwargs)
                logger.info(f"Call {original_next_call_id} replayed successfully.")
            except Exception as exec_exc:
                import debugpy
                debugpy.breakpoint()
                logger.error(
                    f"Error executing replayed call for original ID {original_next_call_id} ('{next_function.__name__}'): {exec_exc}"
                )
                logger.info("Stopping replay sequence due to execution error.")
                break

            # Move to the next call in the original sequence for the next iteration
            original_current_call_id = original_next_call_id

        # --- End Replay Loop ---

        # 7. Commit monitor session to save all recorded calls from the replay (if monitoring enabled)
        if enable_monitoring and monitor_instance:
            logger.info(
                f"Committing monitor session to save replayed calls (starting from {first_replayed_call_id})."
            )
            monitor_instance.session.commit()
            logger.info("Replay sequence committed.")

        return first_replayed_call_id  # Return ID of the start of the new branch

    except Exception as e:
        logger.error(f"Error during session replay: {e}")
        traceback.print_exc()  # Print full traceback for debugging
        # Rollback the *main* monitor session to undo potential partial recordings (if monitoring enabled)
        if enable_monitoring and monitor_instance:
            try:
                monitor_instance.session.rollback()
                logger.info("Rolled back main monitoring session due to error.")
            except Exception as rb_err:
                logger.error(f"Error rolling back main monitoring session: {rb_err}")
        return None  # Indicate failure
    finally:
        # Restore monitor state if backed up
        if monitor_instance:
            if original_parent_id_for_next_call is not None:
                monitor_instance._parent_id_for_next_call = (
                    original_parent_id_for_next_call
                )
            if original_recording_state is not None:
                monitor_instance.is_recording_enabled = original_recording_state
        # Close the separate read session
        read_session.commit()
        assert monitor_instance is not None
        monitor_instance.export_db()
        read_session.close()
        logger.info("Replay function finished.")


# Helper function (can be moved elsewhere if preferred)
def _load_or_reload_function_and_module(
    call_info: dict[str, Any],
    loaded_modules_cache: dict[str, Any],
    reload_module: bool = True,
) -> tuple[Callable, Any]:
    """Loads/reloads module and gets function object based on call_info."""
    function_name = call_info["function"]
    file_path = call_info["file"]
    # Safely get module_path, handling if 'code' key exists but is None
    code_info = call_info.get("code")  # Get 'code' dict or None
    module_path_from_info = code_info.get("module_path") if code_info else None
    module = None
    module_key = None  # Use file_path or module_path as key

    # Prioritize file_path if it exists
    if file_path and file_path.endswith(".py") and os.path.exists(file_path):
        module_key = file_path
        if module_key in loaded_modules_cache:
            module = loaded_modules_cache[module_key]
        else:
            file_dir = os.path.dirname(file_path)
            module_name_from_path = os.path.basename(file_path)[
                :-3
            ]  # Remove .py extension

            # Ensure the directory is in sys.path
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

                # FIX: Handle __main__ vs module name mapping for pickle compatibility
                _setup_module_name_mapping(module, module_name_from_path)

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

                # FIX: Handle __main__ vs module name mapping for pickle compatibility
                _setup_module_name_mapping(module, module_path_from_info)

        if not module:
            raise ValueError(
                f"Could not load module for function '{function_name}'. Checked file '{file_path}' and module path '{module_path_from_info}'."
            )

    # Handle qualified names (e.g., Class.method)
    func_parts = function_name.split(".")
    obj = module
    try:
        for part in func_parts:
            obj = getattr(obj, part)
        function = obj
    except AttributeError:
        # Check if module exists before accessing __name__
        module_name_str = module.__name__ if module else "<unknown module>"
        raise ValueError(
            f"Could not find function/method '{function_name}' in module '{module_name_str}'."
        )

    if not callable(function):
        raise ValueError(f"Attribute '{function_name}' found but is not callable.")

    return function, module


def _setup_module_name_mapping(module: Any, module_name: str):
    """
    Set up module name mapping to handle __main__ vs module name mismatch during pickle.

    This function ensures that classes defined in a script are available under both
    the __main__ namespace (when run as script) and the module namespace (when imported).
    """
    try:
        # Enhanced approach: Use metadata-driven normalization instead of simple mapping
        logger.info(f"Setting up module mapping for {module_name}")

        # Ensure the module is available under both names in sys.modules
        if '__main__' in sys.modules and module_name not in sys.modules:
            sys.modules[module_name] = module
            logger.info(f"Made module available as {module_name}")
        elif module_name in sys.modules and '__main__' not in sys.modules:
            sys.modules['__main__'] = module
            logger.info("Made module available as __main__")

        # For all classes in the module, ensure they can be found under the correct module path
        for name in dir(module):
            attr = getattr(module, name)
            if isinstance(attr, type):  # It's a class
                # The PickleConfig will handle the module path normalization during pickle/unpickle
                # We just need to ensure the class is accessible
                logger.debug(f"Found class {name} in module {module_name}")

    except Exception as e:
        logger.warning(f"Error setting up module name mapping for {module_name}: {e}")


def _ensure_class_availability_for_unpickling(obj_manager: ObjectManager, module: Any):
    """
    Ensure that classes are available in the correct namespace before unpickling objects.

    This function inspects the stored objects and tries to make their classes available
    in the current execution context using the metadata-driven approach.
    """
    try:
        # The ObjectManager now handles module path normalization automatically
        # using stored metadata, so we just need to ensure basic module availability

        logger.info(f"Ensuring class availability for module {module.__name__}")

        # Make sure the module is available under common names
        if module.__name__ not in sys.modules:
            sys.modules[module.__name__] = module

        # If this is a main script, also make it available as __main__
        if module.__name__ == "main" and '__main__' not in sys.modules:
            sys.modules['__main__'] = module
            logger.info("Made main module available as __main__")

    except Exception as e:
        logger.warning(f"Error ensuring class availability for unpickling: {e}")


# Helper function
def _load_execution_data_from_call_info(
    call_info: dict[str, Any],
    obj_manager: ObjectManager,
    use_signature_parsing: bool = False,
) -> tuple[list[Any], dict[str, Any]]:
    """Rehydrates args and kwargs from call_info locals."""
    if not call_info:
        raise ValueError("call_info cannot be None")

    locals_refs = call_info.get("locals_refs", {})
    locals_dict = obj_manager.rehydrate_dict(locals_refs)

    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    if use_signature_parsing:
        # Try to get function code information to separate args from kwargs
        code_definition_id = call_info.get("code_definition_id")
        if code_definition_id is not None:
            code_info = call_info.get("code")
            code_content = code_info.get("content") if code_info else None

            if code_content:
                # Try to identify function parameters
                # Look for def function_name(params): pattern
                match = re.search(r"def\s+([^(]+)\s*\(([^)]*)\)", code_content)
                if match:
                    param_str = match.group(2)
                    params = [p.strip() for p in param_str.split(",")]

                    # Extract positional args based on parameter order
                    args = []
                    kwargs = {}
                    for param in params:
                        # Skip empty parameters
                        if not param:
                            continue

                        # Handle default values
                        if "=" in param:
                            param_name = param.split("=")[0].strip()
                            if param_name in locals_dict:
                                kwargs[param_name] = locals_dict[param_name]
                        else:
                            # Remove any type annotations
                            if ":" in param:
                                param_name = param.split(":")[0].strip()
                            else:
                                param_name = param.strip()

                            # Skip self/cls parameter for methods
                            if param_name in ("self", "cls"):
                                continue

                            if param_name in locals_dict:
                                args.append(locals_dict[param_name])

                    return args, kwargs

    # Fallback: return all as kwargs
    kwargs = locals_dict
    args = []

    return args, kwargs


# Helper function
def _load_globals_from_call_info(
    call_info: dict[str, Any],
    obj_manager: ObjectManager,
    ignore_globals: list[str] | None,
) -> dict[str, Any]:
    """Rehydrates and filters globals from call_info."""
    if not call_info:
        raise ValueError("call_info cannot be None")

    globals_refs = call_info.get("globals_refs", {})
    globals_dict = obj_manager.rehydrate_dict(globals_refs)
    return {
        k: v
        for k, v in globals_dict.items()
        if not (k.startswith("__") and k.endswith("__"))
        and not (ignore_globals and k in ignore_globals)
    }


# Helper function
def _inject_globals(module: Any, function: Callable, globals_dict: dict[str, Any]):
    """Injects globals into module and function context."""
    if module:
        module.__dict__.update(globals_dict)

    if function:
        try:
            # Update the function's own __globals__ dict as well
            function.__globals__.update(globals_dict)
        except (AttributeError, TypeError) as e:
            print(
                f"Warning: Could not update __globals__ for function {getattr(function, '__name__', '<unknown>')}: {e}"
            )


# Backward compatibility aliases
def reanimate_function(*args, **kwargs):
    """
    Deprecated: Use execute_function_call() instead.
    This function is kept for backward compatibility.
    """
    import warnings

    warnings.warn(
        "reanimate_function() is deprecated. Use execute_function_call() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return execute_function_call(*args, **kwargs)


def replay_session_from(*args, **kwargs):
    """
    Deprecated: Use replay_session_sequence() instead.
    This function is kept for backward compatibility.
    """
    import warnings

    warnings.warn(
        "replay_session_from() is deprecated. Use replay_session_sequence() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return replay_session_sequence(*args, **kwargs)


def _load_mock_functions(session, function_execution_id, obj_manager, module, mock_function):
    """
    Loads mock functions for a given function execution.

    Args:
        session: The database session.
        function_execution_id: The ID of the function execution.
        obj_manager: The ObjectManager instance.
        module: The module to inject mock functions into.
        mock_function: List of function names to mock.

    Returns:
        None
    """
    if not mock_function:
        return

    fct = session.query(models.FunctionCall).filter_by(id=function_execution_id).first()
    if not fct:
        return
    subcalls = fct.get_child_calls(session)
    if not subcalls:
        return

    possible_names = {x.function for x in subcalls}
    return_values_dict = defaultdict(list)
    for subcall in subcalls:
        return_values_dict[subcall.function].append(subcall.return_ref)

    # Convert to generators
    return_values_dict = {k: (obj_manager.get(x)[0] for x in v) for k, v in return_values_dict.items()}
    for func_name in mock_function:
        if func_name in possible_names:
            db_func_name = func_name
            working_module = module
            if "." in func_name:
                func_name_parts = func_name.split(".")
                while len(func_name_parts) > 1:
                    module_name = func_name_parts.pop(0).lower()
                    if module_name in working_module.__dict__:
                        working_module = working_module.__dict__[module_name]
                    else:
                        break
                func_name = func_name_parts[-1]

            if func_name in working_module.__dict__:
                working_module.__dict__[f"_old_{func_name}"] = working_module.__dict__[func_name]

                # Create a closure that captures the current func_name value
                def create_mock_func(captured_func_name):
                    def mock_func(*args, **kwargs):
                        try:
                            return next(return_values_dict[captured_func_name])
                        except StopIteration:
                            # If the generator is exhausted, return the original function
                            old_func = working_module.__dict__[f"_old_{captured_func_name.split('.')[-1]}"]
                            return old_func(*args, **kwargs)
                    return mock_func

                working_module.__dict__[func_name] = create_mock_func(db_func_name)
        else:
            pass  # TODO(jb): Handle case when func_name is not in module.__dict__
