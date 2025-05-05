#!/usr/bin/env python3
"""
PyMonitor API

API endpoints for PyMonitor database access.
"""

import os
import sys
import logging
import json
import datetime
from typing import Dict, Any, List, Optional, TypedDict, Union, cast

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sqlalchemy.orm import Session
from monitoringpy.core import (
    init_db, StoredObject, FunctionCall, StackSnapshot, 
    CodeDefinition, FunctionCallTracker, ObjectManager,
    MonitoringSession
)
from monitoringpy.core.representation import Object, Primitive, List as ListObj, DictObject, CustomClass

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables for database access
db_path = None
session = None
call_tracker = None
object_manager = None

# Create FastAPI app
app = FastAPI(
    title="PyMonitor API",
    description="API endpoints for PyMonitor database access",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define FunctionCallInfo type
class FunctionCallInfo(TypedDict, total=False):
    function: str
    file: Optional[str]
    line: Optional[int]
    start_time: Optional[datetime.datetime]
    end_time: Optional[datetime.datetime]
    locals: Dict[str, Any]
    globals: Dict[str, Any]
    return_value: Any

# Helper functions
def serialize_value(value: Any) -> str:
    """Serialize a value to a string representation"""
    if value is None:
        return "None"
    elif isinstance(value, (int, float, bool, str)):
        return str(value)
    elif isinstance(value, (list, tuple)):
        # Limit array size and handle non-serializable items
        items = []
        for item in value[:3]:  # Only show first 3 items
            try:
                items.append(serialize_value(item))
            except:
                items.append(f"<{type(item).__name__}>")
        return f"[{', '.join(items)}{'...' if len(value) > 3 else ''}]"
    elif isinstance(value, dict):
        # Limit dict size and handle non-serializable items
        items = []
        for k, v in list(value.items())[:3]:  # Only show first 3 items
            try:
                key_str = serialize_value(k)
                val_str = serialize_value(v)
                items.append(f"{key_str}: {val_str}")
            except:
                items.append(f"<{type(k).__name__}>: <{type(v).__name__}>")
        return f"{{{', '.join(items)}{'...' if len(value) > 3 else ''}}}"
    else:
        try:
            return str(value)
        except:
            return f"<{type(value).__name__} object>"

def serialize_stored_value(ref: Optional[str]) -> Dict[str, Any]:
    """Serialize a stored value, handling cases where the original class is not available"""
    global object_manager
    
    if ref is None:
        return {"value": "None", "type": "NoneType"}
        
    if object_manager is None:
        return {"value": "<no object manager>", "type": "Error"}
        
    try:
        # If ref is not a string, or if it's a string but looks like a direct value
        # (not a 32-char hex hash), we need to store it first
        if not isinstance(ref, str) or (
            isinstance(ref, str) and 
            not (len(ref) == 32 and all(c in '0123456789abcdef' for c in ref.lower()))
        ):
            try:
                logger.debug(f"Got direct value instead of reference, storing it first: {type(ref)}")
                ref = object_manager.store(ref)
                logger.debug(f"Stored value, got reference: {ref}")
            except Exception as e:
                logger.error(f"Failed to store direct value: {e}")
                return {"value": f"<storage error: {str(e)}>", "type": "Error"}
        
        # Now we should have a proper reference string
        ref_str = str(ref)
        
        # Try to get the value using ObjectManager
        value = object_manager.get(ref_str)
        if value is None:
            # If we couldn't get it, it's truly not found
            return {"value": f"<not found: {ref_str}>", "type": "Error"}
            
        # Successfully got the value
        if type(value).__name__ == 'MyCustomClass':
            logger.info(f"Found MyCustomClass: {value}")
            
        # Get code definition if available
        code_info = None
        if object_manager.code_manager:
            code_info = object_manager.code_manager.get_object_code(ref_str)
            if code_info:
                code_info = {
                    'name': code_info.get('name', type(value).__name__),
                    'module_path': code_info.get('module_path', 'unknown'),
                    'code_content': code_info.get('code', ''),
                    'creation_time': code_info.get('creation_time', datetime.datetime.now()).isoformat()
                }
            
        return {
            "value": str(value),
            "type": type(value).__name__,
            "code": code_info
        }
            
    except Exception as e:
        logger.error(f"Error serializing value for ref {ref}: {e}")
        return {"value": f"<error: {str(e)}>", "type": "Error"}

def serialize_call_info(call_info: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a function call info object to a JSON-compatible dict"""
    # Don't use the TypedDict for parameter typing - use a generic Dict instead
    # to avoid typing conflicts with the core module's FunctionCallInfo
    
    result = {}
    
    # Add fields with safety checks
    if "function" in call_info:
        result["function"] = call_info["function"]
    if "file" in call_info:
        result["file"] = call_info["file"]
    if "line" in call_info:
        result["line"] = call_info["line"]
    
    # Handle timestamps with safety checks - use .get() to avoid KeyError
    start_time = call_info.get("start_time")
    if start_time and hasattr(start_time, "isoformat"):
        result["start_time"] = start_time.isoformat()
    
    end_time = call_info.get("end_time")
    if end_time and hasattr(end_time, "isoformat"):
        result["end_time"] = end_time.isoformat()
        
    # Process locals
    if "locals" in call_info and call_info["locals"]:
        locals_dict = {}
        for name, value in call_info["locals"].items():
            locals_dict[name] = serialize_stored_value(value)
        result["locals"] = locals_dict
    else:
        result["locals"] = {}
    
    # Process globals
    if "globals" in call_info and call_info["globals"]:
        globals_dict = {}
        for name, value in call_info["globals"].items():
            # Filter out module-level imports and other large objects
            if not name.startswith("__") and not name.endswith("__"):
                globals_dict[name] = serialize_stored_value(value)
        result["globals"] = globals_dict
    else:
        result["globals"] = {}
    
    # Process return value
    if "return_value" in call_info:
        result["return_value"] = serialize_stored_value(call_info["return_value"])
        
    # Add call_metadata if present
    if "call_metadata" in call_info and call_info["call_metadata"] is not None:
        # Assuming call_metadata is already JSON-serializable
        result["call_metadata"] = call_info["call_metadata"]
    else:
        result["call_metadata"] = None
    
    return result

# Define routes with actual implementation
@app.get("/api/functions-with-stack-recordings")
async def get_functions_with_stack_recordings():
    """Get a list of functions that have stack recordings (previously called 'traces')"""
    global call_tracker
    
    try:
        if call_tracker is None:
            raise ValueError("Call tracker is not initialized")
                
        functions = call_tracker.get_functions_with_traces()
        
        # Convert function data to a serializable format
        result = []
        for function in functions:
            func_data = {
                "id": function["id"],
                "function": function["function"],
                "trace_count": function["trace_count"],
                "file": function.get("file", "unknown"),
                "line": function.get("line", 0),
            }
            
            # Add the first occurrence time if available
            if function.get("first_occurrence"):
                # Check if it's already a string or a datetime
                if hasattr(function["first_occurrence"], 'isoformat'):
                    func_data["first_occurrence"] = function["first_occurrence"].isoformat()
                else:
                    func_data["first_occurrence"] = function["first_occurrence"]
            
            # Add the last occurrence time if available
            if function.get("last_occurrence"):
                # Check if it's already a string or a datetime
                if hasattr(function["last_occurrence"], 'isoformat'):
                    func_data["last_occurrence"] = function["last_occurrence"].isoformat()
                else:
                    func_data["last_occurrence"] = function["last_occurrence"]
            
            result.append(func_data)
        
        # Sort by function name
        result.sort(key=lambda x: x["function"])
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting functions with stack recordings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stack-recording/{function_id}")
async def get_stack_recording(function_id: str):
    """Get the stack snapshot information for a function call"""
    global session, object_manager
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
                
        function_call = session.query(FunctionCall).filter(FunctionCall.id == function_id).first()
        if not function_call:
            raise ValueError(f"Function call {function_id} not found")
        
        # Get all snapshots for this function call
        snapshots = session.query(StackSnapshot).filter(
            StackSnapshot.function_call_id == function_id
        ).order_by(StackSnapshot.timestamp.asc()).all()
        
        if not snapshots:
            return {
                "function": {
                    "id": function_id,
                    "name": function_call.function,
                    "file": function_call.file,
                    "line": function_call.line,
                },
                "frames": []
            }
        
        # Get code information if available
        code = None
        if function_call.code_definition_id:
            try:
                code_definition = session.query(CodeDefinition).filter(
                    CodeDefinition.id == function_call.code_definition_id
                ).first()
                
                if code_definition:
                    code = {
                        'content': code_definition.code_content,
                        'module_path': code_definition.module_path,
                        'type': code_definition.type,
                        'name': code_definition.name
                    }
            except Exception as e:
                logger.error(f"Error retrieving code definition: {e}")
        
        # Build a snapshots of function state for all recorded frames
        frames = []
        try:
            # Process each snapshot
            for stack_snapshot in snapshots:
                frame_info = {
                    "frame_id": stack_snapshot.frame_id,
                    "function_name": stack_snapshot.function_name,
                    "file_name": stack_snapshot.file_name,
                    "line_number": stack_snapshot.line_number,
                    "locals": stack_snapshot.locals_refs,
                    "globals_subset": stack_snapshot.globals_refs,
                    "snapshot_id": str(stack_snapshot.id),
                    "timestamp": stack_snapshot.timestamp.isoformat() if stack_snapshot.timestamp else None,
                    "previous_snapshot_id": str(stack_snapshot.previous_snapshot_id) if stack_snapshot.previous_snapshot_id else None,
                    "next_snapshot_id": str(stack_snapshot.next_snapshot_id) if stack_snapshot.next_snapshot_id else None,
                    "locals_refs": stack_snapshot.locals_refs,
                    "globals_refs": stack_snapshot.globals_refs
                }
                
                # Add code information if available
                if code:
                    frame_info["code"] = code
                
                # Add call metadata if available
                if function_call.call_metadata:
                    frame_info["call_metadata"] = function_call.call_metadata
                
                # Process locals from the snapshot's locals_refs
                if stack_snapshot.locals_refs:
                    for name, value in stack_snapshot.locals_refs.items():
                        try:
                            frame_info["locals"][name] = serialize_stored_value(value)
                        except Exception as e:
                            logger.error(f"Error serializing local {name}: {e}")
                            frame_info["locals"][name] = {"value": f"<error: {str(e)}>", "type": "Error"}
                
                # Process globals from the snapshot's globals_refs
                if stack_snapshot.globals_refs:
                    for name, value in stack_snapshot.globals_refs.items():
                        # Filter out module-level imports and other large objects
                        if not name.startswith("__") and not name.endswith("__"):
                            try:
                                frame_info["globals_subset"][name] = serialize_stored_value(value)
                            except Exception as e:
                                logger.error(f"Error serializing global {name}: {e}")
                                frame_info["globals_subset"][name] = {"value": f"<error: {str(e)}>", "type": "Error"}
                
                frames.append(frame_info)
        except Exception as e:
            logger.error(f"Error processing stack data: {e}")
            frames = []
        
        # Return the stack trace data
        return {
            "function": {
                "id": function_id,
                "name": function_call.function,
                "file": function_call.file,
                "line": function_call.line,
                "time": function_call.start_time.isoformat() if function_call.start_time else None,
                "end_time": function_call.end_time.isoformat() if function_call.end_time else None,
                "code_definition_id": function_call.code_definition_id,
                "call_metadata": function_call.call_metadata
            },
            "frames": frames
        }
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting stack recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/snapshot/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    """Get details of a specific stack snapshot"""
    global session, object_manager
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
                
        snapshot = session.query(StackSnapshot).filter(StackSnapshot.id == snapshot_id).first()
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        # Get the function call
        function_call = session.query(FunctionCall).filter(
            FunctionCall.id == snapshot.function_call_id
        ).first()
        
        # Build the response with locals and globals data
        locals_data = {}
        globals_data = {}
        
        # Process locals_refs
        if snapshot.locals_refs:
            for name, value in snapshot.locals_refs.items():
                try:
                    locals_data[name] = serialize_stored_value(value)
                except Exception as e:
                    logger.error(f"Error serializing local {name}: {e}")
                    locals_data[name] = {"value": f"<error: {str(e)}>", "type": "Error"}
        
        # Process globals_refs
        if snapshot.globals_refs:
            for name, value in snapshot.globals_refs.items():
                if not name.startswith("__") and not name.endswith("__"):
                    try:
                        globals_data[name] = serialize_stored_value(value)
                    except Exception as e:
                        logger.error(f"Error serializing global {name}: {e}")
                        globals_data[name] = {"value": f"<error: {str(e)}>", "type": "Error"}
        
        return {
            "id": snapshot.id,
            "function_call_id": snapshot.function_call_id,
            "function": function_call.function if function_call else "unknown",
            "file": function_call.file if function_call else "unknown",
            "line": snapshot.line_number,
            "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
            "locals": locals_data,
            "globals": globals_data,
            "previous_snapshot_id": snapshot.previous_snapshot_id,
            "next_snapshot_id": snapshot.next_snapshot_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/object-graph")
async def get_object_graph():
    """Get the object graph for visualization"""
    global object_manager, session
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
                
        objects = session.query(StoredObject).all()
        
        # Build a graph of object references
        nodes = []
        edges = []
        
        for obj in objects:
            try:
                # Get the object's type
                if object_manager is None:
                    continue
                        
                obj_value = object_manager.get(obj.id)
                if obj_value is None:
                    continue
                
                obj_type = type(obj_value).__name__
                
                # Create a node for the object
                node = {
                    "id": obj.id,
                    "label": obj_type,
                    "type": obj_type,
                    "size": len(str(obj_value)) if hasattr(obj_value, "__len__") else 1
                }
                
                nodes.append(node)
                
                # For container objects, create edges to their contents
                if isinstance(obj_value, (list, tuple)):
                    for i, item in enumerate(obj_value):
                        if isinstance(item, str) and len(item) == 32 and all(c in '0123456789abcdef' for c in item.lower()):
                            edges.append({
                                "source": obj.id,
                                "target": item,
                                "label": f"[{i}]"
                            })
                elif isinstance(obj_value, dict):
                    for key, value in obj_value.items():
                        key_str = str(key)
                        if isinstance(value, str) and len(value) == 32 and all(c in '0123456789abcdef' for c in value.lower()):
                            edges.append({
                                "source": obj.id,
                                "target": value,
                                "label": key_str[:10] + ("..." if len(key_str) > 10 else "")
                            })
            except Exception as e:
                logger.error(f"Error processing object {obj.id}: {e}")
        
        return {"nodes": nodes, "edges": edges}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting object graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/db-info")
async def get_db_info():
    """Get database path information"""
    global db_path
    
    try:
        if db_path is None:
            raise ValueError("DB path is not initialized")
            
        return {"db_path": db_path}
    except Exception as e:
        logger.error(f"Error getting DB info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/function-calls")
async def get_function_calls(
    search: str = Query(None, description="Search term to filter function calls"),
    file: str = Query(None, description="File filter"),
    function: str = Query(None, description="Function name filter")
):
    """Get a list of function calls with optional filtering"""
    global session
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
                
        function_calls = session.query(FunctionCall).all()
        
        # Convert to a serializable format
        result = []
        for fc in function_calls:
            # get locals
            locals_data = {}
            for name, value in fc.locals_refs.items():
                locals_data[name] = serialize_stored_value(value)
            # get return value
            return_value = serialize_stored_value(fc.return_ref)
            call_data = {
                "id": fc.id,
                "function": fc.function,
                "file": fc.file,
                "line": fc.line,
                "start_time": fc.start_time.isoformat() if fc.start_time else None,
                "end_time": fc.end_time.isoformat() if fc.end_time else None,
                "duration": (fc.end_time - fc.start_time).total_seconds() if fc.end_time and fc.start_time else None,
                "has_stack_recording": session.query(StackSnapshot).filter(StackSnapshot.function_call_id == fc.id).count() > 0,
                "locals": locals_data,
                "return_value": return_value
            }
            
            # Apply filters
            if search and search.lower() not in fc.function.lower() and (not fc.file or search.lower() not in fc.file.lower()):
                continue
                
            if file and (not fc.file or file.lower() not in fc.file.lower()):
                continue
                
            if function and function.lower() not in fc.function.lower():
                continue
                
            result.append(call_data)
        
        # Sort by time
        result.sort(key=lambda x: x["start_time"] if x["start_time"] else "", reverse=True)
        
        # Return as dict with function_calls key to match UI expectations
        return {"function_calls": result}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting function calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/function-call/{call_id}")
async def get_function_call(call_id: str):
    """Get details of a specific function call"""
    global call_tracker
    
    try:
        if call_tracker is None:
            raise ValueError("Call tracker is not initialized")
                
        call_info = call_tracker.get_call(call_id)
        if call_info is None:
            raise ValueError(f"Function call {call_id} not found")
        
        # Serialize the call info - cast to Dict[str, Any] to avoid typing issues
        # between different FunctionCallInfo definitions
        return serialize_call_info(cast(Dict[str, Any], call_info))
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting function call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions")
async def get_monitoring_sessions():
    """Get all monitoring sessions"""
    global session
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
                
        # Query all monitoring sessions
        monitoring_sessions = session.query(MonitoringSession).all()
        
        # Convert sessions to a serializable format
        result = []
        for ms in monitoring_sessions:
            session_data = {
                "id": ms.id,
                "name": ms.name,
                "description": ms.description,
                "start_time": ms.start_time.isoformat() if ms.start_time else None,
                "end_time": ms.end_time.isoformat() if ms.end_time else None,
                "function_count": len(ms.function_calls_map) if ms.function_calls_map else 0,
                "total_calls": sum(len(calls) for calls in ms.function_calls_map.values()) if ms.function_calls_map else 0,
                "metadata": ms.session_metadata
            }
            result.append(session_data)
        
        # Sort sessions by start_time in descending order (newest first)
        result.sort(key=lambda x: x["start_time"] if x["start_time"] else "", reverse=True)
        
        return {"sessions": result}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting monitoring sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session/{session_id}")
async def get_monitoring_session(session_id: int):
    """Get details of a specific monitoring session"""
    global session
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
                
        # Query the monitoring session
        monitoring_session = session.query(MonitoringSession).filter(MonitoringSession.id == session_id).first()
        if not monitoring_session:
            raise ValueError(f"Monitoring session {session_id} not found")
        
        # Get all function calls for this session
        function_calls = []
        if monitoring_session.function_calls_map:
            for func_name, call_ids in monitoring_session.function_calls_map.items():
                for call_id in call_ids:
                    # Get the function call from the database
                    func_call = session.query(FunctionCall).filter(FunctionCall.id == call_id).first()
                    if func_call:
                        call_data = {
                            "id": func_call.id,
                            "function": func_call.function,
                            "file": func_call.file,
                            "line": func_call.line,
                            "start_time": func_call.start_time.isoformat() if func_call.start_time else None,
                            "end_time": func_call.end_time.isoformat() if func_call.end_time else None,
                            "duration": (func_call.end_time - func_call.start_time).total_seconds() if func_call.end_time and func_call.start_time else None,
                            "has_stack_recording": session.query(StackSnapshot).filter(StackSnapshot.function_call_id == func_call.id).count() > 0
                        }
                        function_calls.append(call_data)
        
        # Calculate common variables information for display
        common_vars_info = {}
        if monitoring_session.common_globals:
            for func_name, var_names in monitoring_session.common_globals.items():
                if func_name not in common_vars_info:
                    common_vars_info[func_name] = {"globals": [], "locals": []}
                common_vars_info[func_name]["globals"] = var_names
        
        if monitoring_session.common_locals:
            for func_name, var_names in monitoring_session.common_locals.items():
                if func_name not in common_vars_info:
                    common_vars_info[func_name] = {"globals": [], "locals": []}
                common_vars_info[func_name]["locals"] = var_names
        
        # Serialize the monitoring session
        result = {
            "id": monitoring_session.id,
            "name": monitoring_session.name,
            "description": monitoring_session.description,
            "start_time": monitoring_session.start_time.isoformat() if monitoring_session.start_time else None,
            "end_time": monitoring_session.end_time.isoformat() if monitoring_session.end_time else None,
            "function_calls_map": monitoring_session.function_calls_map,
            "common_variables": common_vars_info,
            "common_globals": monitoring_session.common_globals,
            "common_locals": monitoring_session.common_locals,
            "metadata": monitoring_session.session_metadata,
            "function_calls": function_calls
        }
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting monitoring session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def initialize_db(db_file: str):
    """Initialize the database with the given file path"""
    global session, call_tracker, db_path, object_manager
    
    print(f"Initializing database: {db_file}")
    
    if not os.path.exists(db_file):
        logger.error(f"Database file not found: {db_file}")
        sys.exit(1)
    
    # Initialize the database and tracker
    Session = init_db(db_file)
    session = Session()
    object_manager = ObjectManager(session)
    call_tracker = FunctionCallTracker(session)
    db_path = db_file
    
    logger.info(f"Database initialized: {db_file}")
    print(id(session), id(call_tracker))
    return session

def close_db():
    """Close the database connection"""
    global session
    
    if session:
        session.close()
        session = None
        logger.info("Database connection closed")

def run_api(db_file: str, host: str = '127.0.0.1', port: int = 8000):
    """Run the API server"""
    import uvicorn
    
    try:
        # Initialize the database BEFORE starting the server
        initialize_db(db_file)
        print(id(session))
        # Run the server
        logger.info(f"Starting API server at http://{host}:{port}")
        uvicorn.run(app, host=host, port=port)
    except KeyboardInterrupt:
        logger.info("API server stopped.")
    finally:
        # Clean up database connections on exit
        close_db() 