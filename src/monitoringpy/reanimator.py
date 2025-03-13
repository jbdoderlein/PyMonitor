import inspect
import types
import sys
import os
import logging
import pickle
import importlib
import importlib.util
import datetime
import re
import builtins
from typing import Any, Dict, List, Callable, Optional, Tuple, Union, cast
from sqlalchemy import and_, or_
from .models import init_db, FunctionCall, Object, ObjectAttribute, ObjectItem
from .db_operations import DatabaseManager

# Configure logging
logger = logging.getLogger(__name__)

class PyDBReanimator:
    """
    Class for loading and reanimating function calls from a monitoring database.
    This allows for searching, inspecting, and reanimating past function executions.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize the reanimator with a database path.
        
        Args:
            db_path: Path to the SQLite database file
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
            
        self.db_path = db_path
        self.Session = init_db(db_path)
        self.db_manager = DatabaseManager(self.Session)
        logger.info(f"Initialized reanimator with database: {db_path}")
    
    def search(self, 
               function_filter: Optional[Union[str, Callable]] = None, 
               file_filter: Optional[str] = None,
               time_range: Optional[Tuple[datetime.datetime, datetime.datetime]] = None,
               perf_filter: Optional[Dict[str, float]] = None,
               limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search for function calls in the database based on various filters.
        
        Args:
            function_filter: Function name or callable to filter by
            file_filter: File path to filter by
            time_range: Tuple of (start_time, end_time) as datetime objects
            perf_filter: Dict with performance thresholds (e.g., {'pkg': 100, 'dram': 50})
            limit: Maximum number of results to return
            
        Returns:
            List of function call metadata dictionaries
        """
        session = self.Session()
        try:
            query = session.query(FunctionCall)
            
            # Apply function filter
            if function_filter:
                if callable(function_filter):
                    # If a callable is provided, get its name
                    function_name = function_filter.__name__
                else:
                    function_name = function_filter
                query = query.filter(FunctionCall.function == function_name)
            
            # Apply file filter
            if file_filter:
                query = query.filter(FunctionCall.file.like(f"%{file_filter}%"))
            
            # Apply time range filter
            if time_range:
                start_time, end_time = time_range
                # Use explicit comparison operators instead of relying on __bool__
                if start_time is not None:
                    query = query.filter(FunctionCall.start_time >= start_time)
                if end_time is not None:
                    query = query.filter(FunctionCall.start_time <= end_time)
            
            # Apply performance filter
            if perf_filter:
                if 'pkg' in perf_filter:
                    query = query.filter(FunctionCall.perf_pkg <= perf_filter['pkg'])
                if 'dram' in perf_filter:
                    query = query.filter(FunctionCall.perf_dram <= perf_filter['dram'])
            
            # Order by start time descending (most recent first)
            query = query.order_by(FunctionCall.start_time.desc()).limit(limit)
            
            # Convert to list of dictionaries
            results = []
            for call in query.all():
                # Handle datetime objects safely
                start_time_str = None
                end_time_str = None
                if hasattr(call.start_time, 'isoformat'):
                    start_time_str = call.start_time.isoformat()
                if hasattr(call.end_time, 'isoformat'):
                    end_time_str = call.end_time.isoformat()
                
                results.append({
                    'id': call.id,
                    'function': call.function,
                    'file': call.file,
                    'line': call.line,
                    'start_time': start_time_str,
                    'end_time': end_time_str,
                    'perf_pkg': call.perf_pkg,
                    'perf_dram': call.perf_dram,
                })
            
            return results
        finally:
            session.close()
    
    def get_call_details(self, call_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific function call.
        
        Args:
            call_id: ID of the function call
            
        Returns:
            Dictionary with detailed function call information
        """
        session = self.Session()
        try:
            # First get the basic function call information
            function_call = session.query(FunctionCall).filter(FunctionCall.id == call_id).first()
            if not function_call:
                raise ValueError(f"Function call with ID {call_id} not found")
            
            # Get the basic function call information
            call_info = {
                'id': function_call.id,
                'function': function_call.function,
                'file': function_call.file,
                'line': function_call.line,
                'start_time': function_call.start_time.isoformat() if hasattr(function_call.start_time, 'isoformat') else None,
                'end_time': function_call.end_time.isoformat() if hasattr(function_call.end_time, 'isoformat') else None,
                'perf_pkg': function_call.perf_pkg,
                'perf_dram': function_call.perf_dram,
            }
            
            # Use the existing method to get detailed function call data (locals, globals, return value)
            call_data = self.db_manager.get_function_call_data(call_id)
            if not call_data:
                raise ValueError(f"Function call data with ID {call_id} not found")
            
            # Merge the basic information with the detailed data
            call_info.update(call_data)
            
            return call_info
        finally:
            session.close()
    
    def _import_module_from_file(self, file_path: str) -> Optional[Any]:
        """
        Import a module from a file path.
        
        Args:
            file_path: Path to the Python file
            
        Returns:
            Imported module or None if import fails
        """
        try:
            # Convert file path to module path
            if file_path.endswith('.py'):
                file_path = file_path[:-3]
            
            # Handle absolute paths
            if file_path.startswith('/'):
                # Get the directory containing the file
                dir_path = os.path.dirname(file_path)
                
                # Add the directory to sys.path temporarily
                sys.path.insert(0, dir_path)
                
                # Get the module name (filename without extension)
                module_name = os.path.basename(file_path)
                
                try:
                    # Import the module
                    module = importlib.import_module(module_name)
                    return module
                finally:
                    # Remove the directory from sys.path
                    sys.path.pop(0)
            else:
                # For relative paths, try standard import
                module_path = file_path.replace('/', '.').replace('\\', '.')
                module_path = module_path.lstrip('.')
                return importlib.import_module(module_path)
        except (ImportError, AttributeError) as e:
            logger.error(f"Error importing module from {file_path}: {e}")
            return None
    
    def _convert_primitive_value(self, value: Optional[str], type_name: Optional[str]) -> Any:
        """
        Convert a primitive value string to its appropriate Python type.
        
        Args:
            value: String value to convert
            type_name: Type name to convert to
            
        Returns:
            Converted value
        """
        if value is None or type_name is None:
            return None
            
        if type_name == 'int':
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0
        elif type_name == 'float':
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        elif type_name == 'str':
            return str(value)
        elif type_name == 'bool':
            return value.lower() == 'true' if hasattr(value, 'lower') else False
        elif type_name == 'NoneType':
            return None
        else:
            # For other primitive types, return the value as is
            return value
    
    def _reconstruct_object(self, obj_data: Dict[str, Any], session, visited=None, function_file=None) -> Any:
        """
        Recursively reconstruct a Python object from its stored representation.
        
        Args:
            obj_data: Dictionary containing object data
            session: SQLAlchemy session
            visited: Set of already visited object IDs to prevent infinite recursion
            function_file: File path of the function that used this object
            
        Returns:
            Reconstructed Python object
        """
        if visited is None:
            visited = set()
            
        # If we've already visited this object, return None to prevent infinite recursion
        obj_id = obj_data.get('id')
        if obj_id in visited:
            return f"<Circular reference to {obj_data.get('type')}>"
        
        # Add this object to the visited set
        if obj_id:
            visited.add(obj_id)
        
        # Handle primitive types
        if 'value' in obj_data:
            type_name = obj_data.get('type')
            value = obj_data.get('value')
            return self._convert_primitive_value(value, type_name)
        
        # Handle complex types
        type_name = obj_data.get('type')
        if type_name is None:
            return None
        
        # Handle lists
        if type_name == 'list':
            items = obj_data.get('items', {})
            result = []
            # Sort by key (which should be the index)
            for key in sorted(items.keys(), key=lambda k: int(k) if k.isdigit() else k):
                item_value = items[key]
                if isinstance(item_value, dict):
                    result.append(self._reconstruct_object(item_value, session, visited, function_file))
                else:
                    result.append(item_value)
            return result
        
        # Handle tuples
        elif type_name == 'tuple':
            items = obj_data.get('items', {})
            result = []
            # Sort by key (which should be the index)
            for key in sorted(items.keys(), key=lambda k: int(k) if k.isdigit() else k):
                item_value = items[key]
                if isinstance(item_value, dict):
                    result.append(self._reconstruct_object(item_value, session, visited, function_file))
                else:
                    result.append(item_value)
            return tuple(result)
        
        # Handle dictionaries
        elif type_name == 'dict':
            items = obj_data.get('items', {})
            result = {}
            for key, item_value in items.items():
                if isinstance(item_value, dict):
                    result[key] = self._reconstruct_object(item_value, session, visited, function_file)
                else:
                    result[key] = item_value
            return result
        
        # Handle sets
        elif type_name == 'set':
            items = obj_data.get('items', {})
            result = set()
            for key, item_value in items.items():
                if isinstance(item_value, dict):
                    result.add(self._reconstruct_object(item_value, session, visited, function_file))
                else:
                    result.add(item_value)
            return result
        
        # Handle custom classes
        else:
            # Try to import the class
            try:
                class_obj = None
                
                # Extract module and class name from the type name
                # This assumes the type name is in the format "module.ClassName"
                if '.' in type_name:
                    module_name, class_name = type_name.rsplit('.', 1)
                    try:
                        module = importlib.import_module(module_name)
                        class_obj = getattr(module, class_name)
                    except (ImportError, AttributeError):
                        pass
                else:
                    # If no module is specified, try to find the class in the builtins
                    class_name = type_name
                    class_obj = getattr(builtins, class_name, None)
                
                # If not found yet, try to find it in the module of the function
                if class_obj is None and function_file:
                    # Try to import the module from the function file
                    module = self._import_module_from_file(function_file)
                    if module:
                        class_obj = getattr(module, class_name, None)
                
                # If still not found, try to find it in the current directory
                if class_obj is None:
                    # Get the current working directory
                    cwd = os.getcwd()
                    
                    # Look for Python files in the current directory
                    for filename in os.listdir(cwd):
                        if filename.endswith('.py'):
                            # Try to import the module
                            module_name = filename[:-3]
                            try:
                                spec = importlib.util.spec_from_file_location(module_name, os.path.join(cwd, filename))
                                if spec and spec.loader:
                                    module = importlib.util.module_from_spec(spec)
                                    spec.loader.exec_module(module)
                                    if hasattr(module, class_name):
                                        class_obj = getattr(module, class_name)
                                        break
                            except (ImportError, AttributeError):
                                pass
                
                # If we found the class, create an instance
                if class_obj:
                    # Create an empty instance
                    instance = object.__new__(class_obj)
                    
                    # Set attributes
                    attributes = obj_data.get('attributes', {})
                    for attr_name, attr_value in attributes.items():
                        if isinstance(attr_value, dict):
                            setattr(instance, attr_name, self._reconstruct_object(attr_value, session, visited, function_file))
                        else:
                            # Convert string values to appropriate types for common attributes
                            if attr_name in ('x', 'y', 'z') and isinstance(attr_value, str):
                                try:
                                    # Try to convert to int or float
                                    if '.' in attr_value:
                                        setattr(instance, attr_name, float(attr_value))
                                    else:
                                        setattr(instance, attr_name, int(attr_value))
                                except (ValueError, TypeError):
                                    setattr(instance, attr_name, attr_value)
                            else:
                                setattr(instance, attr_name, attr_value)
                    
                    return instance
                else:
                    # If we couldn't find the class, return a placeholder
                    attributes = obj_data.get('attributes', {})
                    reconstructed_attrs = {}
                    for attr_name, attr_value in attributes.items():
                        if isinstance(attr_value, dict):
                            reconstructed_attrs[attr_name] = self._reconstruct_object(attr_value, session, visited, function_file)
                        else:
                            reconstructed_attrs[attr_name] = attr_value
                    
                    return f"<{type_name} object with attributes: {reconstructed_attrs}>"
            except Exception as e:
                logger.error(f"Error reconstructing object of type {type_name}: {e}")
                return f"<Error reconstructing {type_name}: {e}>"
    
    def reanimate(self, call_id: str) -> Dict[str, Any]:
        """
        Reanimate a function call by reconstructing its arguments and local variables.
        
        Args:
            call_id: ID of the function call to reanimate
            
        Returns:
            Dictionary containing the reconstructed arguments and local variables
        """
        call_data = self.get_call_details(call_id)
        
        # Extract the necessary information
        function_name = call_data.get('function')
        file_path = call_data.get('file')
        locals_dict = call_data.get('locals', {})
        globals_dict = call_data.get('globals', {})
        return_value = call_data.get('return_value')
        
        # Create a result dictionary with all the reanimated data
        result = {
            'function_name': function_name,
            'file_path': file_path,
            'locals': locals_dict,
            'globals': globals_dict,
            'return_value': return_value,
            'call_id': call_id
        }
        
        return result
    
    def reanimate_objects(self, call_id: str) -> Dict[str, Any]:
        """
        Reanimate a function call by reconstructing its arguments and local variables
        into actual Python objects.
        
        Args:
            call_id: ID of the function call to reanimate
            
        Returns:
            Dictionary containing the reconstructed arguments and local variables as Python objects
        """
        session = self.Session()
        try:
            call_data = self.get_call_details(call_id)
            
            # Extract the necessary information
            function_name = call_data.get('function')
            file_path = call_data.get('file')
            locals_dict = call_data.get('locals', {})
            globals_dict = call_data.get('globals', {})
            return_value_data = call_data.get('return_value')
            
            # Reconstruct local variables
            reanimated_locals = {}
            for var_name, var_data in locals_dict.items():
                reanimated_locals[var_name] = self._reconstruct_object(var_data, session, None, file_path)
            
            # Reconstruct global variables
            reanimated_globals = {}
            for var_name, var_data in globals_dict.items():
                reanimated_globals[var_name] = self._reconstruct_object(var_data, session, None, file_path)
            
            # Reconstruct return value
            reanimated_return = None
            if return_value_data:
                if isinstance(return_value_data, dict):
                    # If it's a complex object
                    reanimated_return = self._reconstruct_object(return_value_data, session, None, file_path)
                else:
                    # If it's a primitive value, we need to determine its type and convert it
                    # Query the database directly to get the return object
                    function_call = session.query(FunctionCall).get(call_id)
                    if function_call and function_call.return_object_id:
                        # Get the return object to determine its type
                        return_obj = session.query(Object).get(function_call.return_object_id)
                        if return_obj and return_obj.type_name:
                            # Convert the value based on the type
                            type_name = str(return_obj.type_name)
                            reanimated_return = self._convert_primitive_value(str(return_value_data), type_name)
                        else:
                            # If we can't determine the type, try to infer it
                            reanimated_return = self._infer_primitive_type(return_value_data)
                    else:
                        # If we can't determine the type, try to infer it
                        reanimated_return = self._infer_primitive_type(return_value_data)
            
            # Create a result dictionary with all the reanimated data
            result = {
                'function_name': function_name,
                'file_path': file_path,
                'locals': reanimated_locals,
                'globals': reanimated_globals,
                'return_value': reanimated_return,
                'call_id': call_id
            }
            
            return result
        finally:
            session.close()
    
    def _infer_primitive_type(self, value: str) -> Any:
        """
        Infer the type of a primitive value and convert it.
        
        Args:
            value: String value to convert
            
        Returns:
            Converted value
        """
        if value is None:
            return None
            
        # Try to infer the type
        if value.isdigit():
            return int(value)
        elif value.replace('.', '', 1).isdigit() and value.count('.') == 1:
            return float(value)
        elif value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        else:
            return value
    
    def execute_reanimated(self, call_id: str) -> Any:
        """
        Execute a function with its reanimated arguments.
        
        Args:
            call_id: ID of the function call to execute
            
        Returns:
            The result of the function execution
        """
        reanimated_data = self.reanimate_objects(call_id)
        
        function_name = reanimated_data['function_name']
        file_path = reanimated_data['file_path']
        locals_dict = reanimated_data['locals']
        
        # Try to import the module containing the function
        try:
            # Import the module from the file path
            module = self._import_module_from_file(file_path)
            if not module:
                raise ImportError(f"Could not import module from {file_path}")
            
            # Get the function from the module
            func = getattr(module, function_name)
            
            # Extract arguments from locals
            # This assumes the first argument is 'self' for methods or that
            # all arguments are named and in locals_dict
            sig = inspect.signature(func)
            args = []
            kwargs = {}
            
            for param_name, param in sig.parameters.items():
                if param_name in locals_dict:
                    if param.kind == param.POSITIONAL_ONLY:
                        args.append(locals_dict[param_name])
                    else:
                        kwargs[param_name] = locals_dict[param_name]
            
            # Execute the function with the reanimated arguments
            return func(*args, **kwargs)
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to import or execute function: {e}")
            raise RuntimeError(f"Failed to execute reanimated function: {e}")

# Convenience function to load a PyDB
def load_pydb(db_path: str) -> PyDBReanimator:
    """
    Load a PyMonitor database for reanimation.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        PyDBReanimator instance
    """
    return PyDBReanimator(db_path) 