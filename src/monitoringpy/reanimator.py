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
from sqlalchemy import and_, or_, create_engine, func, desc
from sqlalchemy.orm import sessionmaker
from .models import init_db, FunctionCall, Object, ObjectAttribute, ObjectItem, ObjectVersion, ObjectIdentity
from .db_operations import DatabaseManager

# Configure logging
logger = logging.getLogger(__name__)

class Reanimator:
    """
    Class for reanimating function calls from the database.
    This allows retrieving and reconstructing function calls with their inputs and outputs.
    """
    
    def __init__(self, db_path):
        """
        Initialize the reanimator with a database path.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        
        # Create engine and session factory
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.Session = sessionmaker(bind=self.engine)
        
        # Create database manager
        self.db_manager = DatabaseManager(self.Session)
    
    def search(self, function_filter=None, file_filter=None, line_filter=None, 
               perf_filter=None, start_time=None, end_time=None, limit=100):
        """
        Search for function calls in the database.
        
        Args:
            function_filter: Filter by function name (string or list of strings)
            file_filter: Filter by file path (string or list of strings)
            line_filter: Filter by line number (int or list of ints)
            perf_filter: Filter by performance metrics (dict with keys 'pkg' and/or 'dram')
            start_time: Filter by start time (datetime or ISO format string)
            end_time: Filter by end time (datetime or ISO format string)
            limit: Maximum number of results to return
            
        Returns:
            list: List of function call dictionaries
        """
        session = self.Session()
        try:
            # Start with a base query
            query = session.query(FunctionCall)
            
            # Apply filters
            if function_filter:
                if isinstance(function_filter, list):
                    query = query.filter(FunctionCall.function.in_(function_filter))
                else:
                    query = query.filter(FunctionCall.function == function_filter)
            
            if file_filter:
                if isinstance(file_filter, list):
                    query = query.filter(FunctionCall.file.in_(file_filter))
                else:
                    query = query.filter(FunctionCall.file == file_filter)
            
            if line_filter:
                if isinstance(line_filter, list):
                    query = query.filter(FunctionCall.line.in_(line_filter))
                else:
                    query = query.filter(FunctionCall.line == line_filter)
            
            if perf_filter:
                if 'pkg' in perf_filter:
                    query = query.filter(FunctionCall.perf_pkg <= perf_filter['pkg'])
                if 'dram' in perf_filter:
                    query = query.filter(FunctionCall.perf_dram <= perf_filter['dram'])
            
            if start_time:
                if isinstance(start_time, str):
                    start_time = datetime.datetime.fromisoformat(start_time)
                query = query.filter(FunctionCall.start_time >= start_time)
            
            if end_time:
                if isinstance(end_time, str):
                    end_time = datetime.datetime.fromisoformat(end_time)
                query = query.filter(FunctionCall.end_time <= end_time)
            
            # Order by start time (most recent first) and limit results
            query = query.order_by(desc(FunctionCall.start_time)).limit(limit)
            
            # Execute query
            function_calls = query.all()
            
            # Convert to dictionaries
            result = []
            for call in function_calls:
                call_dict = {
                    'id': call.id,
                    'function': call.function,
                    'file': call.file,
                    'line': call.line,
                    'start_time': call.start_time.isoformat() if call.start_time else None,
                    'end_time': call.end_time.isoformat() if call.end_time else None
                }
                
                # Add performance metrics if available
                if call.perf_pkg is not None or call.perf_dram is not None:
                    call_dict['performance'] = {}
                    if call.perf_pkg is not None:
                        call_dict['performance']['pkg'] = call.perf_pkg
                    if call.perf_dram is not None:
                        call_dict['performance']['dram'] = call.perf_dram
                
                result.append(call_dict)
            
            return result
        except Exception as e:
            logger.error(f"Error searching function calls: {e}")
            return []
        finally:
            session.close()
    
    def get_call_details(self, call_id: Union[str, int]) -> Dict[str, Any]:
        """
        Get detailed information about a function call.
        
        Args:
            call_id: ID of the function call (can be string or integer)
            
        Returns:
            dict: Dictionary with function call details
        """
        try:
            # Convert call_id to integer
            try:
                call_id = int(call_id)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid call ID: {call_id}. Must be convertible to an integer.")
            
            session = self.Session()
            
            # Get the function call
            function_call = session.query(FunctionCall).filter(FunctionCall.id == call_id).first()
            
            if not function_call:
                raise ValueError(f"Function call with ID {call_id} not found")
            
            # Get basic function call information
            result = {
                'id': function_call.id,
                'function': function_call.function,
                'file': function_call.file,
                'line': function_call.line,
                'start_time': function_call.start_time.isoformat() if function_call.start_time else None,
                'end_time': function_call.end_time.isoformat() if function_call.end_time else None
            }
            
            # Add performance metrics if available
            if function_call.perf_pkg is not None or function_call.perf_dram is not None:
                result['performance'] = {}
                if function_call.perf_pkg is not None:
                    result['performance']['pkg'] = function_call.perf_pkg
                if function_call.perf_dram is not None:
                    result['performance']['dram'] = function_call.perf_dram
            
            # Get detailed data from the database manager
            detailed_data = self.db_manager.get_function_call_data(call_id)
            
            if detailed_data:
                # Merge with basic information
                result.update(detailed_data)
            
            session.close()
            return result
        except Exception as e:
            logger.error(f"Error getting call details: {e}")
            return {'error': str(e)}
    
    def reanimate_objects(self, call_id: Union[str, int]) -> Dict[str, Any]:
        """
        Reanimate a function call by reconstructing Python objects.
        
        Args:
            call_id: ID of the function call (can be string or integer)
            
        Returns:
            dict: Dictionary with reanimated objects
        """
        try:
            # Get call details first
            call_details = self.get_call_details(call_id)
            
            if 'error' in call_details:
                return call_details
            
            # Initialize result with basic function information
            result = {
                'function_name': call_details.get('function'),
                'file_path': call_details.get('file'),
                'line_number': call_details.get('line')
            }
            
            # Create a session for object reconstruction
            session = self.Session()
            
            # Reconstruct local variables
            locals_dict = {}
            for name, obj_data in call_details.get('locals', {}).items():
                try:
                    # Get the object model
                    obj_model = session.query(Object).filter(Object.id == obj_data.get('id')).first()
                    if obj_model:
                        # Use the version if available
                        version_id = None
                        if 'version' in obj_data:
                            version_id = obj_data['version'].get('id')
                        
                        # Reconstruct the object
                        locals_dict[name] = self.db_manager._reconstruct_object(obj_model, session)
                except Exception as e:
                    logger.error(f"Error reconstructing local variable {name}: {e}")
                    locals_dict[name] = f"<Error: {str(e)}>"
            
            result['locals'] = locals_dict
            
            # Reconstruct global variables
            globals_dict = {}
            for name, obj_data in call_details.get('globals', {}).items():
                try:
                    # Get the object model
                    obj_model = session.query(Object).filter(Object.id == obj_data.get('id')).first()
                    if obj_model:
                        # Use the version if available
                        version_id = None
                        if 'version' in obj_data:
                            version_id = obj_data['version'].get('id')
                        
                        # Reconstruct the object
                        globals_dict[name] = self.db_manager._reconstruct_object(obj_model, session)
                except Exception as e:
                    logger.error(f"Error reconstructing global variable {name}: {e}")
                    globals_dict[name] = f"<Error: {str(e)}>"
            
            result['globals'] = globals_dict
            
            # Reconstruct return value
            if 'return_value' in call_details and call_details['return_value']:
                try:
                    # Get the object model
                    obj_model = session.query(Object).filter(
                        Object.id == call_details['return_value'].get('id')
                    ).first()
                    
                    if obj_model:
                        # Use the version if available
                        version_id = None
                        if 'version' in call_details['return_value']:
                            version_id = call_details['return_value']['version'].get('id')
                        
                        # Reconstruct the object
                        result['return_value'] = self.db_manager._reconstruct_object(obj_model, session)
                except Exception as e:
                    logger.error(f"Error reconstructing return value: {e}")
                    result['return_value'] = f"<Error: {str(e)}>"
            
            session.close()
            return result
        except Exception as e:
            logger.error(f"Error reanimating objects: {e}")
            return {'error': str(e)}
    
    def get_object_history(self, object_name: str) -> List[Dict[str, Any]]:
        """
        Get the version history for an object by name.
        
        Args:
            object_name: Name of the object to find
            
        Returns:
            list: List of object identities with their version history
        """
        try:
            # Find objects with this name
            identities = self.db_manager.find_object_by_name(object_name)
            
            result = []
            for identity in identities:
                # Get version history for this identity
                history = self.db_manager.get_object_version_history(identity['identity_hash'])
                
                # Add to result
                result.append({
                    'identity': identity,
                    'versions': history
                })
            
            return result
        except Exception as e:
            logger.error(f"Error getting object history: {e}")
            return []
    
    def compare_versions(self, version_id1: int, version_id2: int) -> Dict[str, Any]:
        """
        Compare two versions of an object.
        
        Args:
            version_id1: ID of the first version
            version_id2: ID of the second version
            
        Returns:
            dict: Comparison results
        """
        try:
            return self.db_manager.compare_object_versions(version_id1, version_id2)
        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            return {'error': str(e)}
    
    def debug_nested_structure(self, call_id: Union[str, int], var_name: str) -> Dict[str, Any]:
        """
        Debug the structure of a nested object in the database.
        
        Args:
            call_id: ID of the function call
            var_name: Name of the variable to debug
            
        Returns:
            dict: Structure information
        """
        try:
            # Get call details
            call_details = self.get_call_details(call_id)
            
            if 'error' in call_details:
                return call_details
            
            # Find the variable
            var_data = None
            var_location = None
            
            if var_name in call_details.get('locals', {}):
                var_data = call_details['locals'][var_name]
                var_location = 'locals'
            elif var_name in call_details.get('globals', {}):
                var_data = call_details['globals'][var_name]
                var_location = 'globals'
            elif var_name == 'return_value' and 'return_value' in call_details:
                var_data = call_details['return_value']
                var_location = 'return'
            
            if not var_data:
                return {'error': f"Variable {var_name} not found in function call {call_id}"}
            
            # Get the object model
            session = self.Session()
            obj_model = session.query(Object).filter(Object.id == var_data.get('id')).first()
            
            if not obj_model:
                session.close()
                return {'error': f"Object for variable {var_name} not found in database"}
            
            # Get structure information
            result = {
                'variable': var_name,
                'location': var_location,
                'type': obj_model.type_name,
                'is_primitive': obj_model.is_primitive
            }
            
            # Add version information if available
            if 'version' in var_data:
                result['version'] = var_data['version']
            
            # Add primitive value if available
            if obj_model.is_primitive and obj_model.primitive_value:
                result['value'] = obj_model.primitive_value
            
            # Add object structure if available
            if obj_model.object_structure:
                result['structure'] = obj_model.object_structure
            
            # Add attributes if available
            attributes = {}
            for attr in session.query(ObjectAttribute).filter(ObjectAttribute.parent_id == obj_model.id).all():
                attr_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                if attr_obj:
                    if attr_obj.is_primitive and attr_obj.primitive_value:
                        attributes[attr.name] = {
                            'type': attr_obj.type_name,
                            'value': attr_obj.primitive_value
                        }
                    else:
                        attributes[attr.name] = {
                            'type': attr_obj.type_name,
                            'id': attr_obj.id
                        }
            
            if attributes:
                result['attributes'] = attributes
            
            # Add items if available
            items = {}
            for item in session.query(ObjectItem).filter(ObjectItem.parent_id == obj_model.id).all():
                item_obj = session.query(Object).filter(Object.id == item.value_id).first()
                if item_obj:
                    if item_obj.is_primitive and item_obj.primitive_value:
                        items[item.key] = {
                            'type': item_obj.type_name,
                            'value': item_obj.primitive_value
                        }
                    else:
                        items[item.key] = {
                            'type': item_obj.type_name,
                            'id': item_obj.id
                        }
            
            if items:
                result['items'] = items
            
            session.close()
            return result
        except Exception as e:
            logger.error(f"Error debugging nested structure: {e}")
            return {'error': str(e)}
    
    def debug_object_versions(self, var_name: str) -> Dict[str, Any]:
        """
        Debug the versions of an object by name.
        
        Args:
            var_name: Name of the object to debug
            
        Returns:
            dict: Version information
        """
        try:
            # Get object history
            history = self.get_object_history(var_name)
            
            if not history:
                return {"error": f"No object history found for '{var_name}'"}
            
            # Get all function calls that reference this object
            session = self.Session()
            result = {
                "variable": var_name,
                "identities": []
            }
            
            for identity_info in history:
                identity = identity_info["identity"]
                versions = identity_info["versions"]
                
                identity_data = {
                    "identity_hash": identity["identity_hash"],
                    "name": identity["name"],
                    "versions": []
                }
                
                for version in versions:
                    version_data = {
                        "version_id": version["version_id"],
                        "version_number": version["version_number"],
                        "timestamp": version["timestamp"],
                        "function_calls": []
                    }
                    
                    # Add attributes if available
                    if "object_id" in version:
                        obj = session.query(Object).filter(Object.id == version["object_id"]).first()
                        if obj:
                            attributes = {}
                            for attr in session.query(ObjectAttribute).filter(ObjectAttribute.parent_id == obj.id).all():
                                attr_obj = session.query(Object).filter(Object.id == attr.value_id).first()
                                if attr_obj and attr_obj.is_primitive and attr_obj.primitive_value:
                                    attributes[attr.name] = attr_obj.primitive_value
                            
                            if attributes:
                                version_data["attributes"] = attributes
                    
                    # Add function calls that reference this version
                    if "function_calls" in version:
                        for call in version["function_calls"]:
                            call_data = {
                                "call_id": call["call_id"],
                                "function": call["function"],
                                "role": call["role"],
                                "name": call["name"],
                                "timestamp": call["timestamp"]
                            }
                            version_data["function_calls"].append(call_data)
                    
                    identity_data["versions"].append(version_data)
                
                result["identities"].append(identity_data)
            
            session.close()
            return result
        except Exception as e:
            logger.error(f"Error debugging object versions: {e}")
            return {"error": str(e)}

def load_pydb(db_path):
    """
    Load a PyMonitor database and return a Reanimator instance.
    
    Args:
        db_path: Path to the database file
        
    Returns:
        Reanimator: Reanimator instance for the database
    """
    return Reanimator(db_path) 