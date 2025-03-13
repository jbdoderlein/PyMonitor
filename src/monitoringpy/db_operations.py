import json
import datetime
import logging
import pickle
import hashlib
import inspect
import uuid
import os
import sqlite3
from sqlalchemy.exc import SQLAlchemyError
from .models import (
    FunctionCall, Object, ObjectAttribute, ObjectItem,
    function_call_locals, function_call_globals
)
import types
import sys

# Configure logging
logger = logging.getLogger(__name__)

# Set debug level for more detailed logging
debug_enabled = os.environ.get('PYMONITOR_DEBUG', '0') == '1'
if debug_enabled:
    logger.setLevel(logging.DEBUG)
    # Add a handler if none exists
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

# Types that can be stored directly as primitive values
PRIMITIVE_TYPES = (int, float, str, bool, type(None))
# Types that can be stored as structured objects
STRUCTURED_TYPES = (dict, list, tuple, set)

class DatabaseManager:
    """
    Handles database operations for the monitoring system.
    This class encapsulates all database-related functionality.
    """
    
    def __init__(self, session_factory):
        """
        Initialize the database manager with a session factory.
        
        Args:
            session_factory: SQLAlchemy session factory created by init_db
        """
        self.Session = session_factory
        self.object_cache = {}  # Cache to avoid duplicate object storage
    
    def _get_object_hash(self, obj):
        """
        Generate a hash for an object to use as its ID.
        For primitive types, use the value itself.
        For complex objects, use pickle and hash.
        
        Args:
            obj: The object to hash
            
        Returns:
            str: Hash of the object
        """
        if isinstance(obj, PRIMITIVE_TYPES):
            # For primitive types, use a hash of the type and value
            return hashlib.md5(f"{type(obj).__name__}:{str(obj)}".encode()).hexdigest()
        elif isinstance(obj, STRUCTURED_TYPES):
            try:
                # For structured types, use a hash of the serialized structure
                if isinstance(obj, dict):
                    # Sort dict keys for consistent hashing
                    serialized = json.dumps(obj, sort_keys=True, default=str)
                elif isinstance(obj, (list, tuple)):
                    serialized = json.dumps(list(obj), default=str)
                elif isinstance(obj, set):
                    serialized = json.dumps(sorted(list(obj)), default=str)
                else:
                    serialized = str(obj)
                return hashlib.md5(f"{type(obj).__name__}:{serialized}".encode()).hexdigest()
            except (TypeError, ValueError):
                # If serialization fails, use pickle
                try:
                    pickled = pickle.dumps(obj)
                    return hashlib.md5(pickled).hexdigest()
                except (pickle.PickleError, TypeError):
                    # If pickling fails, use object's string representation
                    return hashlib.md5(f"{type(obj).__name__}:{str(obj)}".encode()).hexdigest()
        else:
            # For complex objects, try pickle first
            try:
                pickled = pickle.dumps(obj)
                return hashlib.md5(pickled).hexdigest()
            except (pickle.PickleError, TypeError):
                # If pickling fails, use object's string representation and type
                return hashlib.md5(f"{type(obj).__name__}:{str(obj)}".encode()).hexdigest()
    
    def _store_object(self, obj, session, max_depth=3, current_depth=0):
        """
        Store an object in the database with its structure.
        
        Args:
            obj: The object to store
            session: SQLAlchemy session
            max_depth: Maximum depth for nested objects
            current_depth: Current depth in the object hierarchy
            
        Returns:
            Object: The stored object model
        """
        try:
            # Prevent infinite recursion
            if current_depth > max_depth:
                # For objects beyond max depth, store as string
                obj_hash = self._get_object_hash(str(obj))
                # Create object with constructor parameters
                obj_model = Object(
                    id=obj_hash, 
                    type_name="str", 
                    is_primitive=True,
                    primitive_value=f"<max depth reached: {str(obj)[:100]}...>"
                )
                
                # Check if object is already in database before adding
                existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                if existing_obj:
                    return existing_obj
                    
                session.add(obj_model)
                try:
                    session.flush()  # Ensure the object is persisted and bound to the session
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for max depth object: {e}")
                    session.rollback()
                    # Try to get the object again after rollback
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        return existing_obj
                    # If not found, create a new session and try again
                    session.close()
                    session = self.Session()
                    obj_model = Object(
                        id=obj_hash, 
                        type_name="str", 
                        is_primitive=True,
                        primitive_value=f"<max depth reached: {str(obj)[:100]}...>"
                    )
                    session.add(obj_model)
                    session.flush()
                
                return obj_model
                
            obj_hash = self._get_object_hash(obj)
            
            # Check if object is already in cache
            if obj_hash in self.object_cache:
                if debug_enabled:
                    logger.debug(f"Object {obj_hash} found in cache")
                return self.object_cache[obj_hash]
            
            # Check if object is already in database
            existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
            if existing_obj:
                if debug_enabled:
                    logger.debug(f"Object {obj_hash} found in database")
                self.object_cache[obj_hash] = existing_obj
                return existing_obj
            
            # Create new object with all attributes in constructor
            if isinstance(obj, PRIMITIVE_TYPES):
                # Store primitive types directly
                if debug_enabled:
                    logger.debug(f"Storing primitive object of type {type(obj).__name__}")
                obj_model = Object(
                    id=obj_hash,
                    type_name=type(obj).__name__,
                    is_primitive=True,
                    primitive_value=str(obj)
                )
                session.add(obj_model)
                try:
                    session.flush()  # Ensure the object is persisted and bound to the session
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for primitive object: {e}")
                    session.rollback()
                    # Try to get the object again after rollback
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        return existing_obj
                    # If not found, create a new session and try again
                    session.close()
                    session = self.Session()
                    obj_model = Object(
                        id=obj_hash,
                        type_name=type(obj).__name__,
                        is_primitive=True,
                        primitive_value=str(obj)
                    )
                    session.add(obj_model)
                    session.flush()
                    
            elif isinstance(obj, STRUCTURED_TYPES):
                # Store structured types with their structure
                if debug_enabled:
                    logger.debug(f"Storing structured object of type {type(obj).__name__}")
                obj_structure = None
                try:
                    if isinstance(obj, dict):
                        obj_structure = {k: str(v) for k, v in obj.items()}
                    elif isinstance(obj, (list, tuple, set)):
                        obj_structure = [str(item) for item in obj]
                except (TypeError, ValueError):
                    # If JSON serialization fails, leave structure as None
                    pass
                
                obj_model = Object(
                    id=obj_hash,
                    type_name=type(obj).__name__,
                    is_primitive=False,
                    object_structure=obj_structure
                )
                    
                # Add the object to the session early to avoid circular references
                session.add(obj_model)
                try:
                    session.flush()  # Ensure the object is persisted and bound to the session
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for structured object: {e}")
                    session.rollback()
                    # Try to get the object again after rollback
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        self.object_cache[obj_hash] = existing_obj
                        return existing_obj
                    # If not found, create a new session and try again
                    session.close()
                    session = self.Session()
                    obj_model = Object(
                        id=obj_hash,
                        type_name=type(obj).__name__,
                        is_primitive=False,
                        object_structure=obj_structure
                    )
                    session.add(obj_model)
                    session.flush()
                    self.object_cache[obj_hash] = obj_model
                
                # Store items with references
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        try:
                            # Store the key and value as separate objects
                            key_obj = self._store_object(key, session, max_depth, current_depth + 1)
                            value_obj = self._store_object(value, session, max_depth, current_depth + 1)
                            
                            # Create the item linking the key and value
                            item = ObjectItem(
                                id=str(uuid.uuid4()),
                                parent_id=obj_model.id,
                                key=str(key),
                                value_id=value_obj.id
                            )
                            session.add(item)
                        except Exception as e:
                            logger.warning(f"Error storing dict item {key}: {e}")
                elif isinstance(obj, (list, tuple, set)):
                    for i, item in enumerate(obj):
                        try:
                            # Store the item as a separate object
                            item_obj = self._store_object(item, session, max_depth, current_depth + 1)
                            
                            # Create the item with its index
                            obj_item = ObjectItem(
                                id=str(uuid.uuid4()),
                                parent_id=obj_model.id,
                                key=str(i),
                                value_id=item_obj.id
                            )
                            session.add(obj_item)
                        except Exception as e:
                            logger.warning(f"Error storing list item at index {i}: {e}")
            else:
                # For complex objects, try to store attributes
                if debug_enabled:
                    logger.debug(f"Storing complex object of type {type(obj).__name__}")
                pickle_data = None
                try:
                    pickle_data = pickle.dumps(obj)
                except (pickle.PickleError, TypeError):
                    # If pickling fails, just store as string
                    pass
                
                obj_model = Object(
                    id=obj_hash,
                    type_name=type(obj).__name__,
                    is_primitive=False,
                    pickle_data=pickle_data,
                    primitive_value=str(obj) if pickle_data is None else None
                )
                    
                # Add the object to the session early to avoid circular references
                session.add(obj_model)
                try:
                    session.flush()  # Ensure the object is persisted and bound to the session
                    session.commit()  # Commit to ensure the object is in the database
                    self.object_cache[obj_hash] = obj_model
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for complex object: {e}")
                    session.rollback()
                    # Try to get the object again after rollback
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        self.object_cache[obj_hash] = existing_obj
                        return existing_obj
                    # If not found, create a new session and try again
                    session.close()
                    session = self.Session()
                    obj_model = Object(
                        id=obj_hash,
                        type_name=type(obj).__name__,
                        is_primitive=False,
                        pickle_data=pickle_data,
                        primitive_value=str(obj) if pickle_data is None else None
                    )
                    session.add(obj_model)
                    session.flush()
                    session.commit()
                    self.object_cache[obj_hash] = obj_model
                
                # Try to store object attributes
                try:
                    # Get all object attributes (excluding methods and private attributes)
                    attrs = {}
                    for attr_name in dir(obj):
                        if not attr_name.startswith('_') and not callable(getattr(obj, attr_name, None)):
                            try:
                                attrs[attr_name] = getattr(obj, attr_name)
                            except (AttributeError, Exception):
                                # Skip attributes that can't be accessed
                                continue
                    
                    if debug_enabled:
                        logger.debug(f"Found attributes for {type(obj).__name__}: {list(attrs.keys())}")
                    
                    # Store each attribute in a separate transaction to isolate failures
                    for attr_name, attr_value in attrs.items():
                        attr_session = self.Session()
                        try:
                            # Get the parent object in this session
                            parent_obj = attr_session.query(Object).filter(Object.id == obj_hash).first()
                            if not parent_obj:
                                logger.warning(f"Parent object {obj_hash} not found for attribute {attr_name}")
                                # Try to create the parent object again
                                parent_obj = Object(
                                    id=obj_hash,
                                    type_name=type(obj).__name__,
                                    is_primitive=False,
                                    pickle_data=pickle_data,
                                    primitive_value=str(obj) if pickle_data is None else None
                                )
                                attr_session.add(parent_obj)
                                attr_session.flush()
                                attr_session.commit()
                                
                            # Store the attribute value
                            attr_obj = self._store_object(attr_value, attr_session, max_depth, current_depth + 1)
                            if not attr_obj:
                                logger.warning(f"Failed to store attribute value for {attr_name}")
                                attr_session.close()
                                continue
                                
                            # Create the attribute relationship
                            attr_id = str(uuid.uuid4())
                            attr = ObjectAttribute(
                                id=attr_id,
                                parent_id=parent_obj.id,
                                name=attr_name,
                                value_id=attr_obj.id
                            )
                            attr_session.add(attr)
                            attr_session.flush()
                            attr_session.commit()
                            
                            if debug_enabled:
                                logger.debug(f"Added attribute {attr_name} for {type(obj).__name__}")
                        except Exception as e:
                            logger.warning(f"Error storing attribute {attr_name}: {e}")
                            attr_session.rollback()
                        finally:
                            attr_session.close()
                    
                except Exception as e:
                    logger.warning(f"Error storing attributes for {type(obj).__name__}: {e}")
            
            return obj_model
        except Exception as e:
            logger.error(f"Error storing object: {e}")
            # Return a placeholder object if we can't store the actual object
            try:
                placeholder_hash = self._get_object_hash(f"error_placeholder_{str(obj)[:50]}")
                existing_obj = session.query(Object).filter(Object.id == placeholder_hash).first()
                if existing_obj:
                    return existing_obj
                    
                placeholder = Object(
                    id=placeholder_hash,
                    type_name=f"Error_{type(obj).__name__}",
                    is_primitive=True,
                    primitive_value=f"Error storing object: {str(e)[:100]}"
                )
                session.add(placeholder)
                try:
                    session.flush()
                except SQLAlchemyError as flush_error:
                    logger.warning(f"Error flushing placeholder: {flush_error}")
                    session.rollback()
                    # Try with a new session
                    session.close()
                    session = self.Session()
                    placeholder = Object(
                        id=placeholder_hash,
                        type_name=f"Error_{type(obj).__name__}",
                        is_primitive=True,
                        primitive_value=f"Error storing object: {str(e)[:100]}"
                    )
                    session.add(placeholder)
                    session.flush()
                return placeholder
            except Exception as inner_e:
                logger.error(f"Error creating placeholder: {inner_e}")
                # If all else fails, return None and let the caller handle it
                return None
    
    def _store_function_locals(self, function_call, locals_dict, session):
        """
        Store function local variables.
        
        Args:
            function_call: FunctionCall model
            locals_dict: Dictionary of local variables
            session: SQLAlchemy session
        """
        try:
            # Make sure the function call is in the session
            if function_call not in session:
                function_call = session.merge(function_call)
            
            for arg_name, arg_value in locals_dict.items():
                if arg_name == 'self':
                    continue  # Skip self parameter
                    
                try:
                    # Store the object with the current session
                    obj_model = self._store_object(arg_value, session)
                    if obj_model is None:
                        continue  # Skip if object couldn't be stored
                    
                    # Make sure both objects are in the session
                    if function_call not in session:
                        function_call = session.merge(function_call)
                    if obj_model not in session:
                        obj_model = session.merge(obj_model)
                    
                    # Add to function_call_locals association table
                    try:
                        session.execute(
                            function_call_locals.insert().values(
                                function_call_id=function_call.id,
                                object_id=obj_model.id,
                                arg_name=arg_name
                            )
                        )
                        session.flush()
                    except Exception as e:
                        # If there's an error, try to recover
                        session.rollback()
                        logger.warning(f"Error associating function local {arg_name}, retrying: {e}")
                        
                        # Try again with a fresh session state
                        function_call = session.query(FunctionCall).filter(FunctionCall.id == function_call.id).first()
                        obj_model = session.query(Object).filter(Object.id == obj_model.id).first()
                        
                        if function_call and obj_model:
                            session.execute(
                                function_call_locals.insert().values(
                                    function_call_id=function_call.id,
                                    object_id=obj_model.id,
                                    arg_name=arg_name
                                )
                            )
                            session.flush()
                except Exception as e:
                    logger.warning(f"Error storing function local {arg_name}: {e}")
                    session.rollback()  # Rollback the current transaction but continue with others
        except Exception as e:
            logger.error(f"Error storing function locals: {e}")
            session.rollback()
    
    def _store_function_globals(self, function_call, globals_dict, session):
        """
        Store function global variables.
        
        Args:
            function_call: FunctionCall model
            globals_dict: Dictionary of global variables
            session: SQLAlchemy session
        """
        try:
            # Make sure the function call is in the session
            if function_call not in session:
                function_call = session.merge(function_call)
            
            # Filter out modules and built-ins
            filtered_globals = {
                k: v for k, v in globals_dict.items() 
                if not k.startswith('__') and not isinstance(v, types.ModuleType)
                and not isinstance(v, type) and not callable(v)
            }
            
            for var_name, var_value in filtered_globals.items():
                try:
                    # Store the object with the current session
                    obj_model = self._store_object(var_value, session)
                    if obj_model is None:
                        continue  # Skip if object couldn't be stored
                    
                    # Make sure both objects are in the session
                    if function_call not in session:
                        function_call = session.merge(function_call)
                    if obj_model not in session:
                        obj_model = session.merge(obj_model)
                    
                    # Add to function_call_globals association table
                    try:
                        session.execute(
                            function_call_globals.insert().values(
                                function_call_id=function_call.id,
                                object_id=obj_model.id,
                                var_name=var_name
                            )
                        )
                        session.flush()
                    except Exception as e:
                        # If there's an error, try to recover
                        session.rollback()
                        logger.warning(f"Error associating function global {var_name}, retrying: {e}")
                        
                        # Try again with a fresh session state
                        function_call = session.query(FunctionCall).filter(FunctionCall.id == function_call.id).first()
                        obj_model = session.query(Object).filter(Object.id == obj_model.id).first()
                        
                        if function_call and obj_model:
                            session.execute(
                                function_call_globals.insert().values(
                                    function_call_id=function_call.id,
                                    object_id=obj_model.id,
                                    var_name=var_name
                                )
                            )
                            session.flush()
                except Exception as e:
                    logger.warning(f"Error storing function global {var_name}: {e}")
                    session.rollback()  # Rollback the current transaction but continue with others
        except Exception as e:
            logger.error(f"Error storing function globals: {e}")
            session.rollback()
    
    def _store_function_return(self, function_call, return_value, session):
        """
        Store function return value.
        
        Args:
            function_call: FunctionCall model
            return_value: Return value of the function
            session: SQLAlchemy session
        """
        try:
            # Make sure the function call is in the session
            if function_call not in session:
                function_call = session.merge(function_call)
            
            # Store the return value
            obj_model = self._store_object(return_value, session)
            if obj_model is None:
                return  # Skip if object couldn't be stored
            
            # Make sure both objects are in the session
            if function_call not in session:
                function_call = session.merge(function_call)
            if obj_model not in session:
                obj_model = session.merge(obj_model)
            
            # Set the return object ID
            function_call.return_object_id = obj_model.id
            try:
                session.flush()
            except Exception as e:
                # If there's an error, try to recover
                session.rollback()
                logger.warning(f"Error setting function return value, retrying: {e}")
                
                # Try again with a fresh session state
                function_call = session.query(FunctionCall).filter(FunctionCall.id == function_call.id).first()
                obj_model = session.query(Object).filter(Object.id == obj_model.id).first()
                
                if function_call and obj_model:
                    function_call.return_object_id = obj_model.id
                    session.flush()
        except Exception as e:
            logger.error(f"Error storing function return value: {e}")
            session.rollback()
    
    def create_function_call_from_data(self, data, session):
        """
        Create a function call record from the provided data.
        
        Args:
            data (dict): The data to create the function call from.
            session (Session): The database session to use.
            
        Returns:
            FunctionCall: The created function call record, or None if an error occurs.
        """
        try:
            logger.debug(f"Creating function call for {data.get('function')}")
            
            # Parse datetime strings if they are in ISO format
            start_time = data.get('start_time')
            end_time = data.get('end_time')
            
            # Convert ISO format strings to datetime objects
            if isinstance(start_time, str):
                start_time = datetime.datetime.fromisoformat(start_time)
            if isinstance(end_time, str):
                end_time = datetime.datetime.fromisoformat(end_time)
            
            # Extract performance data from perf_result if available
            perf_label = None
            perf_pkg = None
            perf_dram = None
            
            if 'perf_result' in data and data['perf_result']:
                perf_result = data['perf_result']
                perf_label = perf_result.get('label')
                
                # Handle pkg energy - could be a list or a single value
                # Energy values are in microjoules (μJ)
                pkg = perf_result.get('pkg')
                if pkg is not None:
                    try:
                        if isinstance(pkg, list) and len(pkg) > 0:
                            perf_pkg = float(pkg[0])  # Take the first value if it's a list
                        else:
                            perf_pkg = float(pkg)
                    except (TypeError, ValueError):
                        logger.warning(f"Could not convert pkg energy to float: {pkg}")
                
                # Handle dram energy - could be a list or a single value
                # Energy values are in seconds
                dram = perf_result.get('dram')
                if dram is not None:
                    try:
                        if isinstance(dram, list) and len(dram) > 0:
                            perf_dram = float(dram[0])  # Take the first value if it's a list
                        else:
                            perf_dram = float(dram)
                    except (TypeError, ValueError):
                        logger.warning(f"Could not convert dram energy to float: {dram}")
            
            # Get the ID - check both 'id' and 'execution_id' fields
            record_id = data.get('id') or data.get('execution_id') or str(uuid.uuid4())
            
            # Create the function call record
            function_call = FunctionCall(
                id=record_id,
                event_type=data.get('event_type', 'call'),
                function=data.get('function', ''),
                file=data.get('file', ''),
                line=data.get('line', 0),
                start_time=start_time,
                end_time=end_time,
                perf_label=perf_label,
                perf_pkg=perf_pkg,
                perf_dram=perf_dram
            )
            
            # Add the function call to the session and flush to ensure it's persisted
            session.add(function_call)
            try:
                session.flush()
                return function_call
            except SQLAlchemyError as e:
                logger.error(f"Error flushing function call: {e}")
                session.rollback()
                return None
        except Exception as e:
            logger.error(f"Error creating function call: {e}")
            try:
                session.rollback()
            except:
                pass
            return None
    
    def save_to_database(self, data_items):
        """
        Save a list of data items to the database.
        
        Args:
            data_items: List of data items to save
        """
        if not data_items:
            return
        
        if debug_enabled:
            logger.debug(f"Saving {len(data_items)} items to database")
        
        # Process each data item in a separate transaction
        for data in data_items:
            session = None
            try:
                session = self.Session()
                
                # Create function call record
                function_call = self.create_function_call_from_data(data, session)
                if not function_call:
                    logger.error("Failed to create function call record")
                    continue
                
                # Store locals
                if 'locals' in data and function_call:
                    self._store_function_locals(function_call, data['locals'], session)
                    
                # Store globals
                if 'globals' in data and function_call:
                    self._store_function_globals(function_call, data['globals'], session)
                    
                # Store return value
                if 'return_value' in data and function_call:
                    self._store_function_return(function_call, data['return_value'], session)
                    
                # Commit the transaction
                try:
                    session.commit()
                    if debug_enabled and function_call:
                        logger.debug(f"Successfully saved function call {function_call.id}")
                except SQLAlchemyError as e:
                    logger.error(f"Error committing transaction: {e}")
                    session.rollback()
                    
            except Exception as e:
                logger.error(f"Error saving data to database: {e}")
                if session:
                    try:
                        session.rollback()
                    except:
                        pass
            finally:
                if session:
                    try:
                        session.close()
                    except:
                        pass
    
    def get_all_function_calls(self):
        """
        Retrieve all function calls from the database.
        
        Returns:
            list: List of FunctionCall objects
        """
        session = self.Session()
        try:
            return session.query(FunctionCall).all()
        except Exception as e:
            logger.error(f"Error retrieving function calls: {e}")
            return []
        finally:
            session.close()
    
    def _reconstruct_object(self, obj_model, session, visited=None):
        """
        Reconstruct a Python object from its database representation.
        
        Args:
            obj_model: Object model from the database
            session: SQLAlchemy session
            visited: Set of already visited object IDs to prevent infinite recursion
            
        Returns:
            The reconstructed Python object
        """
        try:
            if visited is None:
                visited = set()
                
            # Prevent infinite recursion
            if obj_model.id in visited:
                return f"<circular reference to {obj_model.type_name}>"
            
            visited.add(obj_model.id)
            
            # Handle primitive types
            if obj_model.is_primitive and obj_model.primitive_value is not None:
                value = obj_model.primitive_value
                # Convert string representations back to appropriate types
                if obj_model.type_name == 'int':
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        return value
                elif obj_model.type_name == 'float':
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return value
                elif obj_model.type_name == 'bool':
                    return value.lower() == 'true'
                elif obj_model.type_name == 'NoneType':
                    return None
                else:
                    return value
            
            # Handle structured types
            if obj_model.type_name in ('dict', 'OrderedDict'):
                # Reconstruct dictionary
                result = {}
                for item in obj_model.items:
                    # Get the value object
                    value_obj = session.query(Object).filter(Object.id == item.value_id).first()
                    if value_obj:
                        result[item.key] = self._reconstruct_object(value_obj, session, visited.copy())
                return result
            elif obj_model.type_name in ('list', 'tuple'):
                # Reconstruct list or tuple
                items = []
                # Query items and sort by key (index)
                for item in sorted(obj_model.items, key=lambda x: int(x.key) if x.key.isdigit() else float('inf')):
                    value_obj = session.query(Object).filter(Object.id == item.value_id).first()
                    if value_obj:
                        items.append(self._reconstruct_object(value_obj, session, visited.copy()))
                
                if obj_model.type_name == 'tuple':
                    return tuple(items)
                return items
            elif obj_model.type_name == 'set':
                # Reconstruct set
                items = []
                for item in obj_model.items:
                    value_obj = session.query(Object).filter(Object.id == item.value_id).first()
                    if value_obj:
                        items.append(self._reconstruct_object(value_obj, session, visited.copy()))
                return set(items)
            
            # Try to unpickle complex objects
            if obj_model.pickle_data is not None:
                try:
                    return pickle.loads(obj_model.pickle_data)
                except (pickle.PickleError, TypeError, ImportError) as e:
                    logger.debug(f"Failed to unpickle {obj_model.type_name}: {e}")
                    # Continue to attribute reconstruction
            
            # For custom classes, create a dictionary representation
            if obj_model.attributes:
                # Try to find the class in the current module namespace
                obj_class = None
                try:
                    # Look for the class in common modules
                    for module_name in [__name__, 'builtins', 'datetime', 'collections']:
                        module = sys.modules.get(module_name)
                        if module and hasattr(module, obj_model.type_name):
                            obj_class = getattr(module, obj_model.type_name)
                            break
                except Exception as e:
                    logger.debug(f"Error finding class {obj_model.type_name}: {e}")
                
                # If we can't find the class, create a dictionary representation
                if not obj_class:
                    # Create a dictionary with all attributes
                    result = {
                        '__class__': obj_model.type_name,
                        '__attributes__': {}
                    }
                    
                    # Add attributes
                    for attr in obj_model.attributes:
                        value_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                        if value_obj:
                            result['__attributes__'][attr.name] = self._reconstruct_object(value_obj, session, visited.copy())
                    
                    return result
                
                # If we found the class, try to create an instance
                try:
                    # Try to create an instance of the actual class
                    result = obj_class.__new__(obj_class)
                    
                    # Add attributes
                    for attr in obj_model.attributes:
                        value_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                        if value_obj:
                            setattr(result, attr.name, self._reconstruct_object(value_obj, session, visited.copy()))
                    
                    return result
                except Exception as e:
                    logger.debug(f"Error creating instance of {obj_model.type_name}: {e}")
                    
                    # Fallback to dictionary representation
                    result = {
                        '__class__': obj_model.type_name,
                        '__attributes__': {}
                    }
                    
                    # Add attributes
                    for attr in obj_model.attributes:
                        value_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                        if value_obj:
                            result['__attributes__'][attr.name] = self._reconstruct_object(value_obj, session, visited.copy())
                    
                    return result
            
            # Fallback to string representation
            if obj_model.primitive_value:
                return obj_model.primitive_value
            
            # If we have object structure, use that for representation
            if obj_model.object_structure:
                try:
                    if isinstance(obj_model.object_structure, dict):
                        return {
                            '__class__': obj_model.type_name,
                            '__structure__': obj_model.object_structure
                        }
                    elif isinstance(obj_model.object_structure, list):
                        return {
                            '__class__': obj_model.type_name,
                            '__structure__': obj_model.object_structure
                        }
                    else:
                        return {
                            '__class__': obj_model.type_name,
                            '__structure__': str(obj_model.object_structure)
                        }
                except Exception:
                    pass
            
            return {
                '__class__': obj_model.type_name,
                '__info__': 'Object could not be reconstructed'
            }
        except Exception as e:
            logger.error(f"Error reconstructing object: {e}")
            return {
                '__class__': obj_model.type_name if hasattr(obj_model, 'type_name') else 'Unknown',
                '__error__': str(e)
            }
    
    def get_function_call_data(self, function_call_id):
        """
        Get detailed data for a function call, focusing on raw database fields.
        
        Args:
            function_call_id: ID of the function call
            
        Returns:
            Dictionary with function call details
        """
        try:
            # Get the function call
            session = self.Session()
            function_call = session.query(FunctionCall).filter(FunctionCall.id == function_call_id).first()
            
            if not function_call:
                return None
            
            # Get local variables with their raw attributes
            locals_dict = {}
            for local_assoc in session.query(function_call_locals).filter(
                function_call_locals.c.function_call_id == function_call_id
            ).all():
                obj = session.query(Object).filter(Object.id == local_assoc.object_id).first()
                if obj:
                    # Create a raw representation of the object
                    obj_data = {
                        'type': obj.type_name,
                        'id': obj.id
                    }
                    
                    # Add primitive value if available
                    if obj.is_primitive and obj.primitive_value:
                        obj_data['value'] = obj.primitive_value
                    
                    # Add attributes if available
                    attributes = {}
                    for attr in session.query(ObjectAttribute).filter(ObjectAttribute.parent_id == obj.id).all():
                        attr_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                        if attr_obj:
                            if attr_obj.is_primitive and attr_obj.primitive_value:
                                attributes[attr.name] = attr_obj.primitive_value
                            else:
                                attributes[attr.name] = {
                                    'type': attr_obj.type_name,
                                    'id': attr_obj.id
                                }
                    
                    if attributes:
                        obj_data['attributes'] = attributes
                    
                    # Add items if available (for lists, dicts, etc.)
                    items = {}
                    for item in session.query(ObjectItem).filter(ObjectItem.parent_id == obj.id).all():
                        item_obj = session.query(Object).filter(Object.id == item.value_id).first()
                        if item_obj:
                            if item_obj.is_primitive and item_obj.primitive_value:
                                items[item.key] = item_obj.primitive_value
                            else:
                                items[item.key] = {
                                    'type': item_obj.type_name,
                                    'id': item_obj.id
                                }
                    
                    if items:
                        obj_data['items'] = items
                    
                    locals_dict[local_assoc.arg_name] = obj_data
            
            # Get global variables with their raw attributes
            globals_dict = {}
            for global_assoc in session.query(function_call_globals).filter(
                function_call_globals.c.function_call_id == function_call_id
            ).all():
                obj = session.query(Object).filter(Object.id == global_assoc.object_id).first()
                if obj:
                    # Create a raw representation of the object
                    obj_data = {
                        'type': obj.type_name,
                        'id': obj.id
                    }
                    
                    # Add primitive value if available
                    if obj.is_primitive and obj.primitive_value:
                        obj_data['value'] = obj.primitive_value
                    
                    # Add attributes if available
                    attributes = {}
                    for attr in session.query(ObjectAttribute).filter(ObjectAttribute.parent_id == obj.id).all():
                        attr_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                        if attr_obj:
                            if attr_obj.is_primitive and attr_obj.primitive_value:
                                attributes[attr.name] = attr_obj.primitive_value
                            else:
                                attributes[attr.name] = {
                                    'type': attr_obj.type_name,
                                    'id': attr_obj.id
                                }
                    
                    if attributes:
                        obj_data['attributes'] = attributes
                    
                    # Add items if available (for lists, dicts, etc.)
                    items = {}
                    for item in session.query(ObjectItem).filter(ObjectItem.parent_id == obj.id).all():
                        item_obj = session.query(Object).filter(Object.id == item.value_id).first()
                        if item_obj:
                            if item_obj.is_primitive and item_obj.primitive_value:
                                items[item.key] = item_obj.primitive_value
                            else:
                                items[item.key] = {
                                    'type': item_obj.type_name,
                                    'id': item_obj.id
                                }
                    
                    if items:
                        obj_data['items'] = items
                    
                    globals_dict[global_assoc.var_name] = obj_data
            
            # Get return value with its raw attributes
            return_value = None
            if function_call.return_object_id:
                obj = session.query(Object).filter(Object.id == function_call.return_object_id).first()
                if obj:
                    # Create a raw representation of the object
                    obj_data = {
                        'type': obj.type_name,
                        'id': obj.id
                    }
                    
                    # Add primitive value if available
                    if obj.is_primitive and obj.primitive_value:
                        # Store the primitive value in the dictionary instead of returning it directly
                        obj_data['value'] = obj.primitive_value
                        return_value = obj_data
                    else:
                        # Add attributes if available
                        attributes = {}
                        for attr in session.query(ObjectAttribute).filter(ObjectAttribute.parent_id == obj.id).all():
                            attr_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                            if attr_obj:
                                if attr_obj.is_primitive and attr_obj.primitive_value:
                                    attributes[attr.name] = attr_obj.primitive_value
                                else:
                                    attributes[attr.name] = {
                                        'type': attr_obj.type_name,
                                        'id': attr_obj.id
                                    }
                        
                        if attributes:
                            obj_data['attributes'] = attributes
                        
                        # Add items if available (for lists, dicts, etc.)
                        items = {}
                        for item in session.query(ObjectItem).filter(ObjectItem.parent_id == obj.id).all():
                            item_obj = session.query(Object).filter(Object.id == item.value_id).first()
                            if item_obj:
                                if item_obj.is_primitive and item_obj.primitive_value:
                                    items[item.key] = item_obj.primitive_value
                                else:
                                    items[item.key] = {
                                        'type': item_obj.type_name,
                                        'id': item_obj.id
                                    }
                        
                        if items:
                            obj_data['items'] = items
                        
                        return_value = obj_data
            
            session.close()
            
            return {
                'locals': locals_dict,
                'globals': globals_dict,
                'return_value': return_value
            }
        except Exception as e:
            logger.error(f"Error getting function call data: {e}")
            return None
    
    def query_objects_by_type(self, type_name):
        """
        Query objects by their type.
        
        Args:
            type_name: Type name to query for
            
        Returns:
            list: List of Object models
        """
        session = self.Session()
        try:
            return session.query(Object).filter(Object.type_name == type_name).all()
        except Exception as e:
            logger.error(f"Error querying objects by type: {e}")
            return []
        finally:
            session.close()
    
    def query_objects_by_attribute(self, attr_name, attr_value=None):
        """
        Query objects by attribute name and optionally value.
        
        Args:
            attr_name: Attribute name to query for
            attr_value: Optional attribute value to match
            
        Returns:
            list: List of Object models
        """
        session = self.Session()
        try:
            query = session.query(Object).join(
                ObjectAttribute, 
                Object.id == ObjectAttribute.parent_id
            ).filter(
                ObjectAttribute.name == attr_name
            )
            
            if attr_value is not None:
                # Find the value object
                value_hash = self._get_object_hash(attr_value)
                query = query.filter(ObjectAttribute.value_id == value_hash)
                
            return query.all()
        except Exception as e:
            logger.error(f"Error querying objects by attribute: {e}")
            return []
        finally:
            session.close() 