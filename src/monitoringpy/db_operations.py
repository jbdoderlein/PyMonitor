import json
import datetime
import logging
import pickle
import hashlib
import inspect
import uuid
import os
import sqlite3
import traceback
from sqlalchemy.exc import SQLAlchemyError
from .db_models import (
    FunctionCall, Object, ObjectAttribute, ObjectItem,
    function_call_locals, function_call_globals, ObjectIdentity, ObjectVersion
)
import types
import sys
from typing import Any, Dict, List, Optional, Tuple, Union, Set
from sqlalchemy.orm import Session, sessionmaker

# Configure logging
logger = logging.getLogger(__name__)

# Set debug level for more detailed logging
debug_enabled = os.environ.get('PYMONITOR_DEBUG', '1') == '1'  # Enable debug by default
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
    
    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Initialize the database manager with a session factory.
        
        Args:
            session_factory: SQLAlchemy session factory created by init_db
        """
        self.Session = session_factory
        self.object_cache: Dict[str, Object] = {}  # Cache to avoid duplicate object storage
    
    def _get_object_hash(self, obj: Any) -> str:
        """
        Generate a hash for an object to use as its ID.
        For primitive types, use the value itself.
        For complex objects, use both the object's identity (memory address) and pickled content.
        
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
            # For custom objects, use both identity and pickled content
            try:
                # Get the object's memory address and type
                obj_id = id(obj)
                obj_type = type(obj).__name__
                
                # Try to pickle the object
                try:
                    pickled = pickle.dumps(obj)
                    # Combine both identity and pickled content
                    combined = f"{obj_type}:{obj_id}:{pickled.hex()}"
                    return hashlib.md5(combined.encode()).hexdigest()
                except (pickle.PickleError, TypeError):
                    # If pickling fails, use string representation
                    combined = f"{obj_type}:{obj_id}:{str(obj)}"
                    return hashlib.md5(combined.encode()).hexdigest()
            except Exception:
                # If we can't get the object's identity or pickle it, fall back to string representation
                return hashlib.md5(f"{type(obj).__name__}:{str(obj)}".encode()).hexdigest()
    
    def _get_identity_hash(self, obj: Any, obj_name: Optional[str] = None) -> str:
        """
        Generate a stable identity hash for an object.
        This is different from _get_object_hash as it aims to identify the same object
        across different versions.
        
        Args:
            obj: The object to generate an identity hash for
            obj_name: Optional name of the object (e.g., variable name)
            
        Returns:
            str: Identity hash for the object
        """
        # For primitive types, the identity is the same as the object hash
        if isinstance(obj, PRIMITIVE_TYPES):
            return self._get_object_hash(obj)
            
        # For complex objects, try to use the built-in __hash__ method if defined
        # and the object is hashable (immutable)
        try:
            if hasattr(obj, '__hash__') and obj.__hash__ is not None:
                obj_hash = str(hash(obj))
                # Combine with type to avoid collisions between different types
                return hashlib.md5(f"{type(obj).__name__}:{obj_hash}".encode()).hexdigest()
        except TypeError:
            # Object is not hashable, continue with fallback
            pass
        
        # Fallback to a combination of:
        # 1. Object type
        # 2. Object name (if provided)
        # 3. Object id (memory address)
        
        obj_type = type(obj).__name__
        obj_id = id(obj)
        
        # For named objects, use a combination of name and type
        if obj_name:
            identity_str = f"{obj_type}:{obj_name}"
            return hashlib.md5(identity_str.encode()).hexdigest()
        
        # For unnamed objects, use a combination of type and memory address
        # This will identify the same object instance across calls
        identity_str = f"{obj_type}:{obj_id}"
        return hashlib.md5(identity_str.encode()).hexdigest()
    
    def _create_object_identity(self, obj: Any, obj_name: Optional[str] = None, session: Optional[Session] = None) -> Tuple[ObjectIdentity, Session]:
        """
        Create or retrieve an object identity record.
        
        Args:
            obj: The object to create an identity for
            obj_name: Optional name of the object (e.g., variable name)
            session: SQLAlchemy session (will create one if not provided)
            
        Returns:
            tuple: (ObjectIdentity, session)
        """
        close_session = False
        if session is None:
            session = self.Session()
            close_session = True
            
        # Ensure session is not None and properly typed
        assert session is not None
        current_session: Session = session
            
        try:
            # Generate identity hash
            identity_hash = self._get_identity_hash(obj, obj_name)
            
            # Check if identity already exists
            identity = current_session.query(ObjectIdentity).filter(
                ObjectIdentity.identity_hash == identity_hash
            ).first()
            
            if identity:
                logger.debug(f"Found existing identity for {obj_name}: {identity_hash}")
                return identity, current_session
                
            # Create new identity
            logger.debug(f"Creating new identity for {obj_name}: {identity_hash}")
            identity = ObjectIdentity(
                identity_hash=identity_hash,
                name=obj_name,
                creation_time=datetime.datetime.now()
            )
            current_session.add(identity)
            
            try:
                current_session.flush()
            except SQLAlchemyError as e:
                logger.warning(f"Error flushing object identity: {e}")
                current_session.rollback()
                
                # Try to get the identity again after rollback
                # (it might have been created by another concurrent operation)
                identity = current_session.query(ObjectIdentity).filter(
                    ObjectIdentity.identity_hash == identity_hash
                ).first()
                
                if identity:
                    return identity, current_session
                    
                # If still not found, try one more time to create it
                identity = ObjectIdentity(
                    identity_hash=identity_hash,
                    name=obj_name,
                    creation_time=datetime.datetime.now()
                )
                current_session.add(identity)
                current_session.flush()
            
            return identity, current_session
        except Exception as e:
            logger.error(f"Error creating object identity: {e}")
            if close_session:
                current_session.close()
            raise
    
    def _create_object_version(self, obj: Any, identity: ObjectIdentity, session: Optional[Session] = None) -> Tuple[ObjectVersion, Session]:
        """
        Create a new version of an object.
        
        Args:
            obj: The object to version
            identity: The ObjectIdentity record
            session: SQLAlchemy session (will create one if not provided)
            
        Returns:
            tuple: (ObjectVersion, session)
        """
        close_session = False
        if session is None:
            current_session: Session = self.Session()
            close_session = True
        else:
            current_session: Session = session
            
        try:
            # Store the object first to get its ID
            obj_model = self._store_object(obj, current_session)
            if not obj_model:
                raise ValueError("Failed to store object")
                
            # Get the latest version number for this identity
            latest_version = current_session.query(ObjectVersion).filter(
                ObjectVersion.identity_id == identity.id
            ).order_by(ObjectVersion.version_number.desc()).first()
            
            version_number = 1
            if latest_version:
                version_number = latest_version.version_number + 1
                
            # Create new version
            version = ObjectVersion(
                identity_id=identity.id,
                object_id=obj_model.id,
                version_number=version_number,
                timestamp=datetime.datetime.now()
            )
            current_session.add(version)
            
            # Update the latest version reference in the identity
            identity.latest_version_id = version.object_id
            
            try:
                current_session.flush()
                logger.debug(f"Created version {version_number} for identity {identity.identity_hash}")
                return version, current_session
            except SQLAlchemyError as e:
                logger.warning(f"Error flushing object version: {e}")
                current_session.rollback()
                
                # Try again with a fresh object model
                obj_model = self._store_object(obj, current_session)
                if not obj_model:
                    raise ValueError("Failed to store object after rollback")
                
                # Get the latest version number again
                latest_version = current_session.query(ObjectVersion).filter(
                    ObjectVersion.identity_id == identity.id
                ).order_by(ObjectVersion.version_number.desc()).first()
                
                version_number = 1
                if latest_version:
                    version_number = latest_version.version_number + 1
                    
                # Create new version again
                version = ObjectVersion(
                    identity_id=identity.id,
                    object_id=obj_model.id,
                    version_number=version_number,
                    timestamp=datetime.datetime.now()
                )
                current_session.add(version)
                
                # Update the latest version reference in the identity
                identity.latest_version_id = version.object_id
                
                current_session.flush()
                logger.debug(f"Created version {version_number} for identity {identity.identity_hash} after retry")
                return version, current_session
                
        except Exception as e:
            logger.error(f"Error creating object version: {e}")
            if close_session:
                current_session.close()
            raise
    
    def _store_object_with_versioning(self, obj: Any, obj_name: Optional[str] = None, session: Optional[Session] = None) -> Tuple[Object, ObjectVersion, Session]:
        """
        Store an object with versioning support.
        
        Args:
            obj: The object to store
            obj_name: Optional name of the object (e.g., variable name)
            session: SQLAlchemy session (will create one if not provided)
            
        Returns:
            tuple: (Object, ObjectVersion, session)
        """
        close_session = False

        if session is None:
            current_session: Session = self.Session()
            close_session = True
        else:
            current_session: Session = session
            
        try:
            # Create or get object identity
            identity, current_session = self._create_object_identity(obj, obj_name, current_session)
            
            # Create object version
            version, current_session = self._create_object_version(obj, identity, current_session)
            
            # Get the object model
            obj_model = current_session.query(Object).filter(
                Object.id == version.object_id
            ).first()
            
            if not obj_model:
                raise ValueError(f"Object not found after creating version: {version.object_id}")
            
            return obj_model, version, current_session
        except Exception as e:
            logger.error(f"Error storing object with versioning: {e}")
            if close_session:
                current_session.close()
            raise
    
    def _store_object(self, obj: Any, session: Session, max_depth: int = 3, current_depth: int = 0) -> Optional[Object]:
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
                    session.flush()
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for max depth object: {e}")
                    session.rollback()
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        return existing_obj
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
            
            # For primitive types, store directly without versioning
            if isinstance(obj, PRIMITIVE_TYPES):
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
                    session.flush()
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for primitive object: {e}")
                    session.rollback()
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        return existing_obj
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
                return obj_model
            
            # For structured types, store their structure
            if isinstance(obj, STRUCTURED_TYPES):
                if debug_enabled:
                    logger.debug(f"Storing structured object of type {type(obj).__name__}")
                
                # Create the object model
                obj_model = Object(
                    id=obj_hash,
                    type_name=type(obj).__name__,
                    is_primitive=False
                )
                
                # Add the object to the session early to avoid circular references
                session.add(obj_model)
                try:
                    session.flush()
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for structured object: {e}")
                    session.rollback()
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        self.object_cache[obj_hash] = existing_obj
                        return existing_obj
                    session.close()
                    session = self.Session()
                    obj_model = Object(
                        id=obj_hash,
                        type_name=type(obj).__name__,
                        is_primitive=False
                    )
                    session.add(obj_model)
                    session.flush()
                    self.object_cache[obj_hash] = obj_model
                
                # Store items with references
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        try:
                            # Store the key and value as separate objects
                            key_obj = self._store_object(str(key), session, max_depth, current_depth + 1)
                            value_obj = self._store_object(value, session, max_depth, current_depth + 1)
                            if value_obj:
                                # Create the item linking the key and value
                                item = ObjectItem(
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
                            if item_obj:
                                # Create the item with its index
                                obj_item = ObjectItem(
                                    parent_id=obj_model.id,
                                    key=str(i),
                                    value_id=item_obj.id
                                )
                                session.add(obj_item)
                        except Exception as e:
                            logger.warning(f"Error storing list item at index {i}: {e}")
                
                try:
                    session.flush()
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing items for structured object: {e}")
                    session.rollback()
                
                return obj_model
            
            # For custom objects, try to store attributes
            if not isinstance(obj, PRIMITIVE_TYPES):
                if debug_enabled:
                    logger.debug(f"Storing custom object of type {type(obj).__name__}")
                
                # Try to pickle the object
                pickle_data = None
                try:
                    pickle_data = pickle.dumps(obj)
                except (pickle.PickleError, TypeError):
                    pass
                
                # Create the object model
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
                    session.flush()
                except SQLAlchemyError as e:
                    logger.warning(f"Error flushing session for custom object: {e}")
                    session.rollback()
                    existing_obj = session.query(Object).filter(Object.id == obj_hash).first()
                    if existing_obj:
                        self.object_cache[obj_hash] = existing_obj
                        return existing_obj
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
                                continue
                    
                    if debug_enabled:
                        logger.debug(f"Found attributes for {type(obj).__name__}: {list(attrs.keys())}")
                    
                    # Store each attribute
                    for attr_name, attr_value in attrs.items():
                        try:
                            # Store the attribute value
                            attr_obj = self._store_object(attr_value, session, max_depth, current_depth + 1)
                            if attr_obj:
                                # Create the attribute relationship
                                attr = ObjectAttribute(
                                    parent_id=obj_model.id,
                                    name=attr_name,
                                    value_id=attr_obj.id
                                )
                                session.add(attr)
                        except Exception as e:
                            logger.warning(f"Error storing attribute {attr_name}: {e}")
                    
                    try:
                        session.flush()
                    except SQLAlchemyError as e:
                        logger.warning(f"Error flushing attributes for custom object: {e}")
                        session.rollback()
                        
                except Exception as e:
                    logger.warning(f"Error storing attributes for {type(obj).__name__}: {e}")
                
                return obj_model
            
            # If we get here, something unexpected happened
            logger.warning(f"Unexpected object type: {type(obj).__name__}")
            return None
            
        except Exception as e:
            logger.error(f"Error storing object: {e}")
            logger.error(f"Object type: {type(obj).__name__}")
            logger.error(f"Error details: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def _store_function_locals(self, function_call: FunctionCall, locals_dict: Dict[str, Any], session: Session) -> None:
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
                    # Store the object with versioning using the same session
                    obj_model, version, session = self._store_object_with_versioning(arg_value, arg_name, session)
                    
                    if obj_model is None or version is None:
                        logger.warning(f"Failed to store local variable: {arg_name}")
                        continue  # Skip if object couldn't be stored
                    
                    # Add to function_call_locals association table with version info
                    try:
                        session.execute(
                            function_call_locals.insert().values(
                                function_call_id=function_call.id,
                                object_id=obj_model.id,
                                object_version_id=version.id,
                                arg_name=arg_name
                            )
                        )
                        session.flush()
                    except Exception as e:
                        logger.warning(f"Error linking local variable {arg_name} to function call: {e}")
                        # Continue with other variables even if this one fails
                except Exception as e:
                    logger.warning(f"Error storing local variable {arg_name}: {e}")
                    # Continue with other variables even if this one fails
        except Exception as e:
            logger.error(f"Error storing function locals: {e}")
            # Let the caller handle the exception
    
    def _store_function_globals(self, function_call: FunctionCall, globals_dict: Dict[str, Any], session: Session) -> None:
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
            
            for var_name, var_value in globals_dict.items():
                # Skip modules, functions, and other non-serializable objects
                if not self._should_store_global(var_name, var_value):
                    continue
                    
                try:
                    # Store the object with versioning using the same session
                    obj_model, version, session = self._store_object_with_versioning(var_value, var_name, session)
                    
                    if obj_model is None or version is None:
                        logger.warning(f"Failed to store global variable: {var_name}")
                        continue  # Skip if object couldn't be stored
                    
                    # Add to function_call_globals association table with version info
                    try:
                        session.execute(
                            function_call_globals.insert().values(
                                function_call_id=function_call.id,
                                object_id=obj_model.id,
                                object_version_id=version.id,
                                var_name=var_name
                            )
                        )
                        session.flush()
                    except Exception as e:
                        logger.warning(f"Error linking global variable {var_name} to function call: {e}")
                        # Continue with other variables even if this one fails
                except Exception as e:
                    logger.warning(f"Error storing global variable {var_name}: {e}")
                    # Continue with other variables even if this one fails
        except Exception as e:
            logger.error(f"Error storing function globals: {e}")
            # Let the caller handle the exception
    
    def _store_function_return(self, function_call: FunctionCall, return_value: Any, session: Session) -> None:
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
            
            # Skip if return value is None
            if return_value is None:
                return
                
            try:
                # Store the object with versioning using the same session
                obj_model, version, session = self._store_object_with_versioning(return_value, f"return_{function_call.function}", session)
                
                if obj_model is None or version is None:
                    logger.warning(f"Failed to store return value for {function_call.function}")
                    return  # Skip if object couldn't be stored
                
                # Update the function call with the return value
                function_call.return_object_id = obj_model.id
                function_call.return_object_version_id = version.id
                session.flush()
            except Exception as e:
                logger.warning(f"Error storing return value for {function_call.function}: {e}")
        except Exception as e:
            logger.error(f"Error storing function return value: {e}")
            # Let the caller handle the exception
    
    def create_function_call_from_data(self, data: Dict[str, Any], session: Session) -> Optional[FunctionCall]:
        """
        Create a function call record from the provided data.
        
        Args:
            data: The data to create the function call from
            session: The database session to use
            
        Returns:
            FunctionCall: The created function call record, or None if an error occurs
        """
        try:
            function_name = data.get('function', 'unknown')
            file_path = data.get('file', 'unknown')
            line_number = data.get('line', 0)
            
            logger.debug(f"Creating function call for {function_name} in {file_path}:{line_number}")
            
            # Parse datetime strings if they are in ISO format
            start_time = data.get('start_time')
            end_time = data.get('end_time')
            
            # Convert ISO format strings to datetime objects
            if isinstance(start_time, str):
                try:
                    start_time = datetime.datetime.fromisoformat(start_time)
                except ValueError as e:
                    logger.error(f"Invalid start_time format for {function_name}: {start_time} - {e}")
                    start_time = datetime.datetime.now()  # Use current time as fallback
                    
            if isinstance(end_time, str):
                try:
                    end_time = datetime.datetime.fromisoformat(end_time)
                except ValueError as e:
                    logger.error(f"Invalid end_time format for {function_name}: {end_time} - {e}")
                    end_time = None  # Use None as fallback
            
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
                            # Make sure we have a numeric value before converting
                            if isinstance(pkg[0], (int, float, str)) and str(pkg[0]).replace('.', '', 1).isdigit():
                                perf_pkg = float(pkg[0])  # Take the first value if it's a list
                        elif isinstance(pkg, (int, float, str)) and str(pkg).replace('.', '', 1).isdigit():
                            perf_pkg = float(pkg)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Could not convert pkg energy to float for {function_name}: {pkg} - {e}")
                
                # Handle dram energy - could be a list or a single value
                # Energy values are in seconds
                dram = perf_result.get('dram')
                if dram is not None:
                    try:
                        if isinstance(dram, list) and len(dram) > 0:
                            # Make sure we have a numeric value before converting
                            if isinstance(dram[0], (int, float, str)) and str(dram[0]).replace('.', '', 1).isdigit():
                                perf_dram = float(dram[0])  # Take the first value if it's a list
                        elif isinstance(dram, (int, float, str)) and str(dram).replace('.', '', 1).isdigit():
                            perf_dram = float(dram)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Could not convert dram energy to float for {function_name}: {dram} - {e}")
            
            # Create the function call record - let the database assign the primary key ID
            function_call = FunctionCall(
                event_type=data.get('event_type', 'call'),
                function=function_name,
                file=file_path,
                line=line_number,
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
                logger.error(f"Database error flushing function call for {function_name} in {file_path}:{line_number}: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error details: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                if hasattr(e, '__cause__') and e.__cause__:
                    logger.error(f"Caused by: {e.__cause__}")
                session.rollback()
                return None
        except Exception as e:
            logger.error(f"Error creating function call for {data.get('function', 'unknown')} in {data.get('file', 'unknown')}: {e}")
            if 'traceback' in locals():
                logger.error(f"Traceback: {traceback.format_exc()}")
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during session rollback: {rollback_error}")
            return None
    
    def save_to_database(self, data_list):
        """Save a list of trace data to the database"""
        try:
            logger.info(f"Starting to save {len(data_list)} items to database")
            session = self.Session()
            try:
                for data in data_list:
                    try:
                        logger.debug(f"Processing item for function: {data.get('function', 'unknown')}")
                        # Create function call
                        function_call = self.create_function_call_from_data(data, session)
                        if function_call:
                            logger.debug(f"Created function call for {data.get('function', 'unknown')}")
                            session.add(function_call)
                            
                            # Store function arguments
                            if 'locals' in data:
                                logger.debug(f"Storing locals for {data.get('function', 'unknown')}")
                                self._store_function_locals(function_call, data['locals'], session)
                            
                            # Store global variables
                            if 'globals' in data:
                                logger.debug(f"Storing globals for {data.get('function', 'unknown')}")
                                self._store_function_globals(function_call, data['globals'], session)
                            
                            # Store return value
                            if 'return_value' in data:
                                logger.debug(f"Storing return value for {data.get('function', 'unknown')}")
                                self._store_function_return(function_call, data['return_value'], session)
                        else:
                            logger.warning(f"Failed to create function call for {data.get('function', 'unknown')}")
                    except Exception as e:
                        logger.error(f"Error processing item: {e}")
                        logger.error(traceback.format_exc())
                        continue
                
                logger.info("Attempting to commit session")
                session.commit()
                logger.info("Successfully committed session")
                return True
            except Exception as e:
                logger.error(f"Error during database save: {e}")
                logger.error(traceback.format_exc())
                session.rollback()
                return False
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error creating database session: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def get_all_function_calls(self) -> List[FunctionCall]:
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
    
    def _reconstruct_object(self, obj_model: Object, session: Session, visited: Optional[Set[str]] = None) -> Any:
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
            
            visited.add(obj_model.id) # type: ignore
            
            # Handle primitive types
            is_primitive = bool(obj_model.is_primitive)
            primitive_value = str(obj_model.primitive_value) if obj_model.primitive_value is not None else None
            if is_primitive and primitive_value is not None:
                value = primitive_value
                # Convert string representations back to appropriate types
                type_name = str(obj_model.type_name)
                if type_name == 'int':
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        return value
                elif type_name == 'float':
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return value
                elif type_name == 'bool':
                    return value.lower() == 'true'
                elif type_name == 'NoneType':
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
            elif obj_model.type_name == 'set': # type: ignore
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
                    pickle_data = bytes(obj_model.pickle_data) # type: ignore
                    return pickle.loads(pickle_data)
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
                        if module and hasattr(module, obj_model.type_name): # type: ignore
                            obj_class = getattr(module, obj_model.type_name) # type: ignore
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
                    for attr in obj_model.attributes: # type: ignore
                        value_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                        if value_obj:
                            result['__attributes__'][attr.name] = self._reconstruct_object(value_obj, session, visited.copy())
                    
                    return result
                
                # If we found the class, try to create an instance
                try:
                    # Try to create an instance of the actual class
                    result = obj_class.__new__(obj_class)
                    
                    # Add attributes
                    for attr in obj_model.attributes: # type: ignore
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
    
    def get_function_call_data(self, function_call_id: int) -> Dict[str, Any]:
        """
        Get detailed data for a function call.
        
        Args:
            function_call_id: ID of the function call
            
        Returns:
            dict: Dictionary with function call data
        """
        session = self.Session()
        try:
            # Initialize result
            result = {}
            
            # Get local variables
            locals_dict = {}
            for local_assoc in session.query(function_call_locals).filter(
                function_call_locals.c.function_call_id == function_call_id
            ).all():
                # Get the object data with version information
                obj_data = self.get_version_specific_object_data(
                    local_assoc.object_id, 
                    local_assoc.object_version_id, 
                    session
                )
                
                if obj_data:
                    locals_dict[local_assoc.arg_name] = obj_data
            
            if locals_dict:
                result['locals'] = locals_dict
            
            # Get global variables with their raw attributes and version info
            globals_dict = {}
            for global_assoc in session.query(function_call_globals).filter(
                function_call_globals.c.function_call_id == function_call_id
            ).all():
                # Get the object data with version information
                obj_data = self.get_version_specific_object_data(
                    global_assoc.object_id, 
                    global_assoc.object_version_id, 
                    session
                )
                
                if obj_data:
                    globals_dict[global_assoc.var_name] = obj_data
            
            if globals_dict:
                result['globals'] = globals_dict
            
            # Get return value with its raw attributes and version info
            function_call = session.query(FunctionCall).filter(
                FunctionCall.id == function_call_id
            ).first()
            
            if function_call and function_call.return_object_id:
                # Get the object data with version information
                return_obj_data = self.get_version_specific_object_data(
                    function_call.return_object_id, 
                    function_call.return_object_version_id, 
                    session
                )
                
                if return_obj_data:
                    result['return_value'] = return_obj_data
            
            return result
        except Exception as e:
            logger.error(f"Error getting function call data: {e}")
            return {}
        finally:
            session.close()
    
    def query_objects_by_type(self, type_name: str) -> List[Object]:
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
    
    def query_objects_by_attribute(self, attr_name: str, attr_value: Optional[Any] = None) -> List[Object]:
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
    
    def get_object_version_history(self, identity_hash: str) -> List[Dict[str, Any]]:
        """
        Get the version history for an object identity.
        
        Args:
            identity_hash: The identity hash of the object
            
        Returns:
            list: List of versions with their details
        """
        session = self.Session()
        try:
            # Find the identity
            identity = session.query(ObjectIdentity).filter(
                ObjectIdentity.identity_hash == identity_hash
            ).first()
            
            if not identity:
                return []
                
            # Get all versions for this identity
            versions = session.query(ObjectVersion).filter(
                ObjectVersion.identity_id == identity.id
            ).order_by(ObjectVersion.version_number).all()
            
            # Build the version history
            history = []
            for version in versions:
                # Get the object for this version
                obj = session.query(Object).filter(
                    Object.id == version.object_id
                ).first()
                
                if not obj:
                    continue
                    
                # Create a version entry
                version_entry = {
                    'version_id': version.id,
                    'version_number': version.version_number,
                    'timestamp': version.timestamp.isoformat() if version.timestamp else None,
                    'object_id': obj.id,
                    'object_type': obj.type_name
                }
                
                # Add primitive value if available
                if obj.is_primitive and obj.primitive_value:
                    version_entry['value'] = obj.primitive_value
                
                # Find function calls that reference this version
                local_calls = session.query(FunctionCall).join(
                    function_call_locals,
                    FunctionCall.id == function_call_locals.c.function_call_id
                ).filter(
                    function_call_locals.c.object_version_id == version.id
                ).all()
                
                global_calls = session.query(FunctionCall).join(
                    function_call_globals,
                    FunctionCall.id == function_call_globals.c.function_call_id
                ).filter(
                    function_call_globals.c.object_version_id == version.id
                ).all()
                
                return_calls = session.query(FunctionCall).filter(
                    FunctionCall.return_object_version_id == version.id
                ).all()
                
                # Add function call references
                function_calls = []
                
                for call in local_calls:
                    # Find the variable name
                    var_name = session.query(function_call_locals.c.arg_name).filter(
                        function_call_locals.c.function_call_id == call.id,
                        function_call_locals.c.object_version_id == version.id
                    ).first()
                    
                    function_calls.append({
                        'call_id': call.id,
                        'function': call.function,
                        'file': call.file,
                        'line': call.line,
                        'role': 'local',
                        'name': var_name[0] if var_name else None,
                        'timestamp': call.start_time.isoformat() if call.start_time else None
                    })
                
                for call in global_calls:
                    # Find the variable name
                    var_name = session.query(function_call_globals.c.var_name).filter(
                        function_call_globals.c.function_call_id == call.id,
                        function_call_globals.c.object_version_id == version.id
                    ).first()
                    
                    function_calls.append({
                        'call_id': call.id,
                        'function': call.function,
                        'file': call.file,
                        'line': call.line,
                        'role': 'global',
                        'name': var_name[0] if var_name else None,
                        'timestamp': call.start_time.isoformat() if call.start_time else None
                    })
                
                for call in return_calls:
                    function_calls.append({
                        'call_id': call.id,
                        'function': call.function,
                        'file': call.file,
                        'line': call.line,
                        'role': 'return',
                        'name': 'return_value',
                        'timestamp': call.end_time.isoformat() if call.end_time else None
                    })
                
                if function_calls:
                    version_entry['function_calls'] = function_calls
                
                history.append(version_entry)
            
            return history
        except Exception as e:
            logger.error(f"Error getting object version history: {e}")
            return []
        finally:
            session.close()
    
    def find_object_by_name(self, name: str) -> List[Dict[str, Any]]:
        """
        Find object identities by name.
        
        Args:
            name: The name to search for
            
        Returns:
            list: List of object identities
        """
        session = self.Session()
        try:
            # Find identities with this name
            identities = session.query(ObjectIdentity).filter(
                ObjectIdentity.name == name
            ).all()
            
            result = []
            for identity in identities:
                # Get the latest version
                latest_version = session.query(ObjectVersion).filter(
                    ObjectVersion.identity_id == identity.id
                ).order_by(ObjectVersion.version_number.desc()).first()
                
                if not latest_version:
                    continue
                
                # Get the object
                obj = session.query(Object).filter(
                    Object.id == latest_version.object_id
                ).first()
                
                if not obj:
                    continue
                
                # Create an identity entry
                identity_entry = {
                    'identity_id': identity.id,
                    'identity_hash': identity.identity_hash,
                    'name': identity.name,
                    'creation_time': identity.creation_time.isoformat() if identity.creation_time else None,
                    'latest_version': {
                        'version_id': latest_version.id,
                        'version_number': latest_version.version_number,
                        'timestamp': latest_version.timestamp.isoformat() if latest_version.timestamp else None,
                        'object_id': obj.id,
                        'object_type': obj.type_name
                    }
                }
                
                # Add primitive value if available
                if obj.is_primitive and obj.primitive_value:
                    identity_entry['latest_version']['value'] = obj.primitive_value
                
                result.append(identity_entry)
            
            return result
        except Exception as e:
            logger.error(f"Error finding object by name: {e}")
            return []
        finally:
            session.close()
    
    def compare_object_versions(self, version_id1: int, version_id2: int) -> Dict[str, Any]:
        """
        Compare two versions of an object and identify differences.
        
        Args:
            version_id1: ID of the first version
            version_id2: ID of the second version
            
        Returns:
            dict: Comparison results
        """
        session = self.Session()
        try:
            # Get the versions
            version1 = session.query(ObjectVersion).filter(
                ObjectVersion.id == version_id1
            ).first()
            
            version2 = session.query(ObjectVersion).filter(
                ObjectVersion.id == version_id2
            ).first()
            
            if not version1 or not version2:
                return {'error': 'One or both versions not found'}
                
            # Check if they belong to the same identity
            if version1.identity_id != version2.identity_id:
                return {'error': 'Versions belong to different objects'}
                
            # Get the identity
            identity = session.query(ObjectIdentity).filter(
                ObjectIdentity.id == version1.identity_id
            ).first()
            
            if not identity:
                return {'error': 'Object identity not found'}
                
            # Get the objects
            obj1 = session.query(Object).filter(
                Object.id == version1.object_id
            ).first()
            
            obj2 = session.query(Object).filter(
                Object.id == version2.object_id
            ).first()
            
            if not obj1 or not obj2:
                return {'error': 'One or both objects not found'}
                
            # Initialize comparison result
            result = {
                'identity': {
                    'id': identity.id,
                    'hash': identity.identity_hash,
                    'name': identity.name
                },
                'version1': {
                    'id': version1.id,
                    'number': version1.version_number,
                    'timestamp': version1.timestamp.isoformat() if version1.timestamp else None
                },
                'version2': {
                    'id': version2.id,
                    'number': version2.version_number,
                    'timestamp': version2.timestamp.isoformat() if version2.timestamp else None
                },
                'differences': []
            }
            
            # Compare primitive values
            if obj1.is_primitive and obj2.is_primitive:
                if obj1.primitive_value != obj2.primitive_value:
                    result['differences'].append({
                        'type': 'primitive_value',
                        'value1': obj1.primitive_value,
                        'value2': obj2.primitive_value
                    })
                return result
                
            # Compare attributes
            attrs1 = {attr.name: attr.value_id for attr in session.query(ObjectAttribute).filter(
                ObjectAttribute.parent_id == obj1.id
            ).all()}
            
            attrs2 = {attr.name: attr.value_id for attr in session.query(ObjectAttribute).filter(
                ObjectAttribute.parent_id == obj2.id
            ).all()}
            
            # Find attributes in version1 but not in version2
            for name, value_id in attrs1.items():
                if name not in attrs2:
                    # Attribute removed
                    attr_obj = session.query(Object).filter(Object.id == value_id).first()
                    value = attr_obj.primitive_value if attr_obj and attr_obj.is_primitive else None
                    
                    result['differences'].append({
                        'type': 'attribute_removed',
                        'name': name,
                        'value1': value,
                        'value2': None
                    })
                elif attrs2[name] != value_id:
                    # Attribute changed
                    attr_obj1 = session.query(Object).filter(Object.id == value_id).first()
                    attr_obj2 = session.query(Object).filter(Object.id == attrs2[name]).first()
                    
                    value1 = attr_obj1.primitive_value if attr_obj1 and attr_obj1.is_primitive else None
                    value2 = attr_obj2.primitive_value if attr_obj2 and attr_obj2.is_primitive else None
                    
                    result['differences'].append({
                        'type': 'attribute_changed',
                        'name': name,
                        'value1': value1,
                        'value2': value2
                    })
            
            # Find attributes in version2 but not in version1
            for name, value_id in attrs2.items():
                if name not in attrs1:
                    # Attribute added
                    attr_obj = session.query(Object).filter(Object.id == value_id).first()
                    value = attr_obj.primitive_value if attr_obj and attr_obj.is_primitive else None
                    
                    result['differences'].append({
                        'type': 'attribute_added',
                        'name': name,
                        'value1': None,
                        'value2': value
                    })
            
            # Compare items (for lists, dicts, etc.)
            items1 = {item.key: item.value_id for item in session.query(ObjectItem).filter(
                ObjectItem.parent_id == obj1.id
            ).all()}
            
            items2 = {item.key: item.value_id for item in session.query(ObjectItem).filter(
                ObjectItem.parent_id == obj2.id
            ).all()}
            
            # Find items in version1 but not in version2
            for key, value_id in items1.items():
                if key not in items2:
                    # Item removed
                    item_obj = session.query(Object).filter(Object.id == value_id).first()
                    value = item_obj.primitive_value if item_obj and item_obj.is_primitive else None
                    
                    result['differences'].append({
                        'type': 'item_removed',
                        'key': key,
                        'value1': value,
                        'value2': None
                    })
                elif items2[key] != value_id:
                    # Item changed
                    item_obj1 = session.query(Object).filter(Object.id == value_id).first()
                    item_obj2 = session.query(Object).filter(Object.id == items2[key]).first()
                    
                    value1 = item_obj1.primitive_value if item_obj1 and item_obj1.is_primitive else None
                    value2 = item_obj2.primitive_value if item_obj2 and item_obj2.is_primitive else None
                    
                    result['differences'].append({
                        'type': 'item_changed',
                        'key': key,
                        'value1': value1,
                        'value2': value2
                    })
            
            # Find items in version2 but not in version1
            for key, value_id in items2.items():
                if key not in items1:
                    # Item added
                    item_obj = session.query(Object).filter(Object.id == value_id).first()
                    value = item_obj.primitive_value if item_obj and item_obj.is_primitive else None
                    
                    result['differences'].append({
                        'type': 'item_added',
                        'key': key,
                        'value1': None,
                        'value2': value
                    })
            
            return result
        except Exception as e:
            logger.error(f"Error comparing object versions: {e}")
            return {'error': str(e)}
        finally:
            session.close()
    
    def find_object_modifications(self, identity_hash: str) -> List[Dict[str, Any]]:
        """
        Find all function calls that modified a specific object.
        
        Args:
            identity_hash: The identity hash of the object
            
        Returns:
            list: List of function calls with modification details
        """
        session = self.Session()
        try:
            # Find the identity
            identity = session.query(ObjectIdentity).filter(
                ObjectIdentity.identity_hash == identity_hash
            ).first()
            
            if not identity:
                return []
                
            # Get all versions for this identity
            versions = session.query(ObjectVersion).filter(
                ObjectVersion.identity_id == identity.id
            ).order_by(ObjectVersion.version_number).all()
            
            if len(versions) <= 1:
                return []  # No modifications if there's only one version
                
            # Find function calls that might have modified the object
            modifications = []
            
            # For each version transition (v1 -> v2), find function calls that happened between them
            for i in range(len(versions) - 1):
                v1 = versions[i]
                v2 = versions[i + 1]
                
                # Find function calls where this object appears as a local variable
                local_calls = session.query(FunctionCall).join(
                    function_call_locals,
                    FunctionCall.id == function_call_locals.c.function_call_id
                ).filter(
                    function_call_locals.c.object_id.in_(
                        session.query(Object.id).filter(
                            Object.id.in_(
                                session.query(ObjectVersion.object_id).filter(
                                    ObjectVersion.identity_id == identity.id
                                )
                            )
                        )
                    )
                ).filter(
                    FunctionCall.start_time >= v1.timestamp,
                    FunctionCall.end_time <= v2.timestamp
                ).all()
                
                # Find function calls where this object appears as a global variable
                global_calls = session.query(FunctionCall).join(
                    function_call_globals,
                    FunctionCall.id == function_call_globals.c.function_call_id
                ).filter(
                    function_call_globals.c.object_id.in_(
                        session.query(Object.id).filter(
                            Object.id.in_(
                                session.query(ObjectVersion.object_id).filter(
                                    ObjectVersion.identity_id == identity.id
                                )
                            )
                        )
                    )
                ).filter(
                    FunctionCall.start_time >= v1.timestamp,
                    FunctionCall.end_time <= v2.timestamp
                ).all()
                
                # Combine and deduplicate calls
                all_calls = {call.id: call for call in local_calls + global_calls}
                
                for call_id, call in all_calls.items():
                    # Get the before and after versions
                    modification = {
                        'call_id': call.id,
                        'function': call.function,
                        'file': call.file,
                        'line': call.line,
                        'start_time': call.start_time.isoformat() if call.start_time else None,
                        'end_time': call.end_time.isoformat() if call.end_time else None,
                        'before_version': {
                            'id': v1.id,
                            'number': v1.version_number,
                            'timestamp': v1.timestamp.isoformat() if v1.timestamp else None
                        },
                        'after_version': {
                            'id': v2.id,
                            'number': v2.version_number,
                            'timestamp': v2.timestamp.isoformat() if v2.timestamp else None
                        }
                    }
                    
                    # Find how the object was used in this call
                    local_vars = session.query(function_call_locals.c.arg_name).filter(
                        function_call_locals.c.function_call_id == call.id,
                        function_call_locals.c.object_id.in_(
                            session.query(Object.id).filter(
                                Object.id.in_(
                                    session.query(ObjectVersion.object_id).filter(
                                        ObjectVersion.identity_id == identity.id
                                    )
                                )
                            )
                        )
                    ).all()
                    
                    global_vars = session.query(function_call_globals.c.var_name).filter(
                        function_call_globals.c.function_call_id == call.id,
                        function_call_globals.c.object_id.in_(
                            session.query(Object.id).filter(
                                Object.id.in_(
                                    session.query(ObjectVersion.object_id).filter(
                                        ObjectVersion.identity_id == identity.id
                                    )
                                )
                            )
                        )
                    ).all()
                    
                    # Add variable names
                    if local_vars:
                        modification['local_vars'] = [var[0] for var in local_vars]
                    
                    if global_vars:
                        modification['global_vars'] = [var[0] for var in global_vars]
                    
                    modifications.append(modification)
            
            return modifications
        except Exception as e:
            logger.error(f"Error finding object modifications: {e}")
            return []
        finally:
            session.close()
    
    def store_object_version(self, obj: Any, obj_name: Optional[str] = None) -> Tuple[Optional[Object], Optional[ObjectVersion]]:
        """
        Store an object with versioning support. This is the main public interface
        for storing objects with versioning.
        
        This method will:
        1. Create or retrieve an identity for the object
        2. Store the object in the database
        3. Create a new version of the object
        
        Args:
            obj: The object to store
            obj_name: Optional name of the object (e.g., variable name)
            
        Returns:
            tuple: (Object, ObjectVersion) - The stored object and its version
        """
        session = self.Session()
        try:
            obj_model, version, session = self._store_object_with_versioning(obj, obj_name, session)
            session.commit()
            return obj_model, version
        except Exception as e:
            logger.error(f"Error in store_object_version: {e}")
            session.rollback()
            return None, None
        finally:
            session.close()
            
    def get_object_version(self, identity_hash: str, version_number: Optional[int] = None) -> Tuple[Optional[Object], Optional[ObjectVersion]]:
        """
        Retrieve a specific version of an object.
        
        Args:
            identity_hash: The identity hash of the object
            version_number: Optional version number (if not provided, returns the latest version)
            
        Returns:
            tuple: (Object, ObjectVersion) - The object and its version
        """
        session = self.Session()
        try:
            # Get the identity
            identity = session.query(ObjectIdentity).filter(
                ObjectIdentity.identity_hash == identity_hash
            ).first()
            
            if not identity:
                logger.warning(f"Identity not found: {identity_hash}")
                return None, None
                
            # Get the version
            if version_number is not None:
                # Get specific version
                version = session.query(ObjectVersion).filter(
                    ObjectVersion.identity_id == identity.id,
                    ObjectVersion.version_number == version_number
                ).first()
            else:
                # Get latest version
                version = session.query(ObjectVersion).filter(
                    ObjectVersion.identity_id == identity.id
                ).order_by(ObjectVersion.version_number.desc()).first()
                
            if not version:
                logger.warning(f"Version not found for identity: {identity_hash}")
                return None, None
                
            # Get the object
            obj_model = session.query(Object).filter(
                Object.id == version.object_id
            ).first()
            
            if not obj_model:
                logger.warning(f"Object not found for version: {version.id}")
                return None, None
                
            return obj_model, version
        except Exception as e:
            logger.error(f"Error in get_object_version: {e}")
            return None, None
        finally:
            session.close()
    
    def _should_store_global(self, var_name: str, var_value: Any) -> bool:
        """
        Determine if a global variable should be stored.
        
        Args:
            var_name: Name of the variable
            var_value: Value of the variable
            
        Returns:
            bool: True if the variable should be stored, False otherwise
        """
        # Skip special variables
        if var_name.startswith('__'):
            return False
            
        # Skip modules
        if isinstance(var_value, types.ModuleType):
            return False
            
        # Skip classes
        if isinstance(var_value, type):
            return False
            
        # Skip functions and methods
        if callable(var_value):
            return False
            
        # Skip other non-serializable objects
        try:
            # Try to pickle the object to see if it's serializable
            pickle.dumps(var_value)
            return True
        except:
            return False
    
    def get_version_specific_object_data(self, obj_id: str, version_id: Optional[int] = None, session: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """
        Get object data for a specific version.
        
        Args:
            obj_id: ID of the object
            version_id: Optional ID of the version (if not provided, uses the object directly)
            session: SQLAlchemy session (will create one if not provided)
            
        Returns:
            dict: Object data with version information
        """
        close_session = False
        if session is None:
            current_session: Session = self.Session()
            close_session = True
        else:
            current_session: Session = session
            
        try:
            # Get the object
            obj = current_session.query(Object).filter(Object.id == obj_id).first()
            if not obj:
                logger.warning(f"Object not found: {obj_id}")
                return None
                
            # Initialize result
            obj_data = {
                'id': obj.id,
                'type': obj.type_name
            }
            
            # If version_id is provided, get the version-specific object
            if version_id:
                version = current_session.query(ObjectVersion).filter(ObjectVersion.id == version_id).first()
                if version:
                    # Add version information
                    obj_data['version'] = {
                        'id': version.id,
                        'version_number': version.version_number,
                        'timestamp': version.timestamp
                    }
                    
                    # Get the identity
                    identity = current_session.query(ObjectIdentity).filter(ObjectIdentity.id == version.identity_id).first()
                    if identity:
                        obj_data['identity'] = {
                            'id': identity.id,
                            'identity_hash': identity.identity_hash,
                            'name': identity.name
                        }
                    
                    # Use the version-specific object for attributes
                    version_obj = current_session.query(Object).filter(Object.id == version.object_id).first()
                    if version_obj:
                        logger.debug(f"Using version-specific object for {obj.id}: version {version.version_number}, object ID {version_obj.id}")
                        obj = version_obj  # Use the version-specific object instead
                    else:
                        logger.warning(f"Version-specific object not found: version {version.version_number}, object ID {version.object_id}")
            
            # Add primitive value if available
            if obj.is_primitive and obj.primitive_value:
                obj_data['value'] = obj.primitive_value
            
            # Add attributes if available
            attributes = {}
            for attr in current_session.query(ObjectAttribute).filter(ObjectAttribute.parent_id == obj.id).all():
                attr_obj = current_session.query(Object).filter(Object.id == attr.value_id).first()
                if attr_obj:
                    if attr_obj.is_primitive and attr_obj.primitive_value:
                        attributes[attr.name] = {
                            'id': attr_obj.id,
                            'type': attr_obj.type_name,
                            'value': attr_obj.primitive_value
                        }
                    else:
                        attributes[attr.name] = {
                            'id': attr_obj.id,
                            'type': attr_obj.type_name
                        }
            
            if attributes:
                obj_data['attributes'] = attributes
            
            # Add items if available
            items = {}
            for item in current_session.query(ObjectItem).filter(ObjectItem.parent_id == obj.id).all():
                item_obj = current_session.query(Object).filter(Object.id == item.value_id).first()
                if item_obj:
                    if item_obj.is_primitive and item_obj.primitive_value:
                        items[item.key] = {
                            'id': item_obj.id,
                            'type': item_obj.type_name,
                            'value': item_obj.primitive_value
                        }
                    else:
                        items[item.key] = {
                            'id': item_obj.id,
                            'type': item_obj.type_name
                        }
            
            if items:
                obj_data['items'] = items
            
            return obj_data
        except Exception as e:
            logger.error(f"Error getting version-specific object data: {e}")
            return None
        finally:
            if close_session:
                current_session.close()