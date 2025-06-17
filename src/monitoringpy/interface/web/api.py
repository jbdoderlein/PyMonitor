#!/usr/bin/env python3
"""
PyMonitor API

API endpoints for PyMonitor database access.
"""

import os
import sys
import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from monitoringpy.core import (
    init_db, StoredObject, FunctionCall, StackSnapshot, 
    CodeDefinition, FunctionCallRepository, ObjectManager,
    MonitoringSession
)

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
            items.append(serialize_value(item))
        return f"[{', '.join(items)}{'...' if len(value) > 3 else ''}]"
    elif isinstance(value, dict):
        # Limit dict size and handle non-serializable items
        items = []
        for k, v in list(value.items())[:3]:  # Only show first 3 items
            key_str = serialize_value(k)
            val_str = serialize_value(v)
            items.append(f"{key_str}: {val_str}")
        return f"{{{', '.join(items)}{'...' if len(value) > 3 else ''}}}"
    else:
        return str(value)
        

def serialize_stored_value(ref: Optional[str]) -> Dict[str, Any]:
    """Serialize a stored value, handling cases where the original class is not available"""
    global object_manager
    assert object_manager is not None
    if ref is None:
        return {"value": "None", "type": "NoneType"}
        
    try:
        # Try to get the value using ObjectManager
        try:
            result = object_manager.get(ref)
        except Exception:
            result = object_manager.get_without_pickle(ref)
        
        # Handle case where result is None
        if result is None:
            return {"value": f"<not found: {ref}>", "type": "Error"}
            
        # Handle case where result is a tuple as expected
        if isinstance(result, tuple) and len(result) == 2:
            value, type_name = result
            if value is None:
                # If we couldn't get it, it's truly not found
                return {"value": f"<not found: {ref}>", "type": "Error"}
                
            return {
                "value": str(value),
                "type": type_name,
            }
            
        # Handle unexpected result type
        return {"value": "<error: unexpected result type>", "type": "Error"}
            
    except Exception as e:
        logger.error(f"Error serializing value for ref {ref}: {e}")
        return {"value": f"<error: {str(e)}>", "type": "Error"}

def serialize_call_info(call_info: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a function call info object to a JSON-compatible dict"""
    
    result = {k: v for k, v in call_info.items()}
    
        
    # Process locals
    if "locals_refs" in call_info and call_info["locals_refs"]:
        locals_dict = {}
        for name, value in call_info["locals_refs"].items():
            locals_dict[name] = serialize_stored_value(value)
        result["locals"] = locals_dict
    else:
        result["locals"] = {}
    
    # Process globals
    if "globals_refs" in call_info and call_info["globals_refs"]:
        globals_dict = {}
        for name, value in call_info["globals_refs"].items():
            if not name.startswith("__") and not name.endswith("__"):
                globals_dict[name] = serialize_stored_value(value)
        result["globals"] = globals_dict
    else:
        result["globals"] = {}
    
    # Process return value
    if "return_ref" in call_info:
        result["return_value"] = serialize_stored_value(call_info["return_ref"])
        
    return result

# Define routes with actual implementation

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
        ).order_by(StackSnapshot.order_in_call.asc()).all()
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
                    first_line_no = code_definition.first_line_no if code_definition.first_line_no is not None else function_call.line
                    code = {
                        'content': code_definition.code_content,
                        'module_path': code_definition.module_path,
                        'type': code_definition.type,
                        'name': code_definition.name,
                        'first_line_no': first_line_no
                    }
            except Exception as e:
                logger.error(f"Error retrieving code definition: {e}")
        
        # Build a snapshots of function state for all recorded frames
        frames = []
        try:
            # Process each snapshot
            for stack_snapshot in snapshots:
                frame_info = {
                    "id": stack_snapshot.id,
                    "line": stack_snapshot.line_number,
                    "snapshot_id": str(stack_snapshot.id),
                    "timestamp": stack_snapshot.timestamp.isoformat() if stack_snapshot.timestamp else None,
                    "locals_refs": stack_snapshot.locals_refs,
                    "globals_refs": stack_snapshot.globals_refs
                }
                if (previous_snapshot := stack_snapshot.get_previous_snapshot(session)):
                    frame_info["previous_snapshot_id"] = str(previous_snapshot.id)

                if stack_snapshot.next_snapshot_id:
                    frame_info["next_snapshot_id"] = str(stack_snapshot.next_snapshot_id)
                
                # Add code information if available
                if code:
                    frame_info["code"] = code
                
                # Add call metadata if available
                if function_call.call_metadata:
                    frame_info["call_metadata"] = function_call.call_metadata
                
                # Process locals from the snapshot's locals_refs
                if stack_snapshot.locals_refs:
                    frame_info["locals"] = {}
                    for name, value in stack_snapshot.locals_refs.items():
                        frame_info["locals"][name] = serialize_stored_value(value)

                
                # Process globals from the snapshot's globals_refs
                if stack_snapshot.globals_refs:
                    frame_info["globals"] = {}
                    for name, value in stack_snapshot.globals_refs.items():
                        # Filter out module-level imports and other large objects
                        if not name.startswith("__") and not name.endswith("__"):
                            frame_info["globals"][name] = serialize_stored_value(value)

                
                frames.append(frame_info)
        except Exception as e:
            logger.error(f"Error processing stack data: {e}")
            frames = []
        
        # Return the stack trace data
        function_dict = {
            "id": function_id,
            "name": function_call.function,
            "file": function_call.file,
            "line": function_call.line,
            "time": function_call.start_time.isoformat() if function_call.start_time else None,
            "end_time": function_call.end_time.isoformat() if function_call.end_time else None,
            "code_definition_id": function_call.code_definition_id,
            "call_metadata": function_call.call_metadata
        }
        if code:
            function_dict["code"] = code
        return {
            "function": function_dict,
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
        
        # Get previous snapshot using the model method
        previous_snapshot = snapshot.get_previous_snapshot(session)
        
        return {
            "id": snapshot.id,
            "function_call_id": snapshot.function_call_id,
            "function": function_call.function if function_call else "unknown",
            "file": function_call.file if function_call else "unknown",
            "line": snapshot.line_number,
            "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
            "locals": locals_data,
            "globals": globals_data,
            "previous_snapshot_id": previous_snapshot.id if previous_snapshot else None,
            "next_snapshot_id": snapshot.next_snapshot_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/object-graph")
async def get_object_graph(show_isolated: bool = False):
    """Get the object graph for visualization
    
    Args:
        show_isolated: Whether to include isolated object nodes with no connections
    """
    global object_manager, session, call_tracker
    
    try:
        if session is None or object_manager is None:
            raise ValueError("Session or object manager is not initialized")
                
        # Get all stored objects
        objects = session.query(StoredObject).all()
        
        # Get all function calls
        function_calls = session.query(FunctionCall).all()
        
        # Get all code definitions
        code_definitions = session.query(CodeDefinition).all()
        
        # Build graph data structures for Cytoscape
        nodes = []
        edges = []
        
        # Map to keep track of nodes we've already processed
        processed_ids = set()
        
        # First add function call nodes
        for fc in function_calls:
            try:
                # Create a node for the function call
                func_id = f"func_{fc.id}"  # Add prefix to make ID unique
                node_data = {
                    "data": {
                        "id": func_id,
                        "originalId": fc.id,  # Store original ID for reference
                        "label": fc.function,
                        "nodeType": "function",
                        "type": "FunctionCall",
                        "file": fc.file,
                        "line": fc.line,
                        "startTime": fc.start_time.isoformat() if fc.start_time else None,
                        "endTime": fc.end_time.isoformat() if fc.end_time else None,
                        "parentCallId": fc.parent_call_id  # Add parent call ID for relationship tracking
                    }
                }
                nodes.append(node_data)
                processed_ids.add(func_id)
                
                # Add connection to parent function call if available
                if fc.parent_call_id:
                    try:
                        parent_id = f"func_{fc.parent_call_id}"  # Add prefix for parent function
                        edge_id = f"edge_{func_id}_parent"
                        edges.append({
                            "data": {
                                "id": edge_id,
                                "source": parent_id,  # Parent is the source
                                "target": func_id,    # Child is the target
                                "label": "calls",
                                "edgeType": "function_call"
                            }
                        })
                        logger.debug(f"Added parent-child edge: {edge_id} from {parent_id} to {func_id}")
                    except Exception as e:
                        logger.error(f"Error adding parent-child edge for {func_id}: {e}")
                
                # Add connection to return value if available
                if fc.return_ref:
                    try:
                        return_id = f"obj_{fc.return_ref}"  # Add prefix for objects
                        edge_id = f"edge_{func_id}_return"
                        edges.append({
                            "data": {
                                "id": edge_id,
                                "source": func_id,
                                "target": return_id,
                                "label": "return",
                                "edgeType": "function_return"
                            }
                        })
                        logger.debug(f"Added return edge: {edge_id} from {func_id} to {return_id}")
                    except Exception as e:
                        logger.error(f"Error adding return edge for {func_id}: {e}")
                
                # Add connections to code definition if available
                if fc.code_definition_id:
                    try:
                        code_id = f"code_{fc.code_definition_id}"  # Add prefix for code definitions
                        edge_id = f"edge_{func_id}_code"
                        edges.append({
                            "data": {
                                "id": edge_id,
                                "source": func_id,
                                "target": code_id,
                                "label": "definition",
                                "edgeType": "code_version"
                            }
                        })
                        logger.debug(f"Added code definition edge: {edge_id} from {func_id} to {code_id}")
                    except Exception as e:
                        logger.error(f"Error adding code definition edge for {func_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing function call {fc.id}: {e}")
                
        # Add code definition nodes
        for cd in code_definitions:
            try:
                # Create a node for the code
                code_id = f"code_{cd.id}"  # Add prefix to make ID unique
                node_data = {
                    "data": {
                        "id": code_id,
                        "originalId": cd.id,  # Store original ID for reference
                        "label": cd.name,
                        "nodeType": "code",
                        "type": "CodeDefinition",
                        "className": cd.name,
                        "modulePath": cd.module_path,
                        "code": cd.code_content[:200] + ("..." if len(cd.code_content) > 200 else ""),
                        "version": getattr(cd, 'hash_value', 'unknown')[:8] if hasattr(cd, 'hash_value') and cd.hash_value else "unknown"
                    }
                }
                nodes.append(node_data)
                processed_ids.add(code_id)
            except Exception as e:
                logger.error(f"Error processing code definition {cd.id}: {e}")
        
        # Process other stored objects
        for obj in objects:
            try:
                # Create prefixed object ID
                obj_id = f"obj_{obj.id}"  # Add prefix to make ID unique
                
                # Skip if we've already processed this object as a function or code def
                if obj_id in processed_ids:
                    continue
                
                # Skip if object manager is missing
                if object_manager is None:
                    continue
                
                # Try to get the object value
                obj_value = None
                obj_type = "Unknown"
                try:
                    obj_value = object_manager.get(obj.id)
                    if obj_value is not None:
                        obj_type = type(obj_value).__name__
                except Exception as e:
                    logger.warning(f"Couldn't get object value for {obj.id}: {e}")
                    # Still include the node, just with limited info
                
                # Determine if it's a primitive type
                is_primitive = False
                if obj_type in ['int', 'float', 'bool', 'str', 'NoneType']:
                    is_primitive = True
                
                # Format label based on type and value
                label = obj_type
                if obj_value is not None:
                    if is_primitive:
                        # For primitives, show the value
                        str_val = str(obj_value)
                        if len(str_val) > 20:
                            label = f"{str_val[:20]}..."
                        else:
                            label = str_val
                    else:
                        # For containers, show size or just type
                        container_size = None
                        try:
                            if hasattr(obj_value, "__len__"):
                                container_size = len(obj_value)
                        except Exception as e:
                            logger.debug(f"Error getting container size for {obj.id}: {e}")
                            pass
                        
                        if container_size is not None:
                            label = f"{obj_type}({container_size})"
                
                # Create a node for the object
                node_data = {
                    "data": {
                        "id": obj_id,
                        "originalId": obj.id,  # Store original ID for reference
                        "label": label,
                        "type": obj_type,
                        "isPrimitive": is_primitive,
                        "nodeType": "object"
                    }
                }
                nodes.append(node_data)
                processed_ids.add(obj_id)
                
                # For container objects, create edges to their contents
                if obj_value is not None:
                    try:
                        if isinstance(obj_value, (list, tuple)):
                            for i, item in enumerate(obj_value[:30]):  # Limit to first 30 items
                                if isinstance(item, str) and len(item) == 32 and all(c in '0123456789abcdef' for c in item.lower()):
                                    # This looks like a reference ID
                                    target_id = f"obj_{item}"  # Add prefix for target objects
                                    edge_id = f"edge_{obj_id}_{i}"
                                    edges.append({
                                        "data": {
                                            "id": edge_id,
                                            "source": obj_id,
                                            "target": target_id,
                                            "label": f"[{i}]",
                                            "edgeType": "contains"
                                        }
                                    })
                                    logger.debug(f"Added list edge: {edge_id} from {obj_id} to {target_id}")
                        elif isinstance(obj_value, dict):
                            for k, v in list(obj_value.items())[:30]:  # Limit to first 30 items
                                key_str = str(k)
                                if isinstance(v, str) and len(v) == 32 and all(c in '0123456789abcdef' for c in v.lower()):
                                    # This looks like a reference ID
                                    target_id = f"obj_{v}"  # Add prefix for target objects
                                    edge_id = f"edge_{obj_id}_{key_str[:8]}"
                                    edges.append({
                                        "data": {
                                            "id": edge_id,
                                            "source": obj_id,
                                            "target": target_id,
                                            "label": key_str[:15] + ("..." if len(key_str) > 15 else ""),
                                            "edgeType": "key_value"
                                        }
                                    })
                                    logger.debug(f"Added dict edge: {edge_id} from {obj_id} to {target_id}")
                    except Exception as e:
                        logger.error(f"Error creating edges for container object {obj_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing object {obj.id}: {e}")
        
        # Filter out edges that point to non-existent nodes
        valid_node_ids = {node["data"]["id"] for node in nodes}
        valid_edges = []
        
        for edge in edges:
            try:
                if (edge["data"]["source"] in valid_node_ids and 
                    edge["data"]["target"] in valid_node_ids):
                    valid_edges.append(edge)
            except Exception as e:
                logger.error(f"Error processing edge: {e}, edge data: {edge}")
        
        # Find connected nodes - any node that appears in an edge
        connected_nodes = set()
        for edge in valid_edges:
            connected_nodes.add(edge["data"]["source"])
            connected_nodes.add(edge["data"]["target"])
        
        # Filter nodes based on show_isolated parameter
        filtered_nodes = []
        isolated_count = 0
        
        for node in nodes:
            node_id = node["data"]["id"]
            node_type = node["data"]["nodeType"]
            
            is_connected = node_id in connected_nodes
            
            # Determine if we should include this node
            include_node = (
                # Always include function and code nodes
                node_type in ["function", "code"] or
                # Include connected object nodes
                (node_type == "object" and is_connected) or
                # Include isolated object nodes if requested
                (node_type == "object" and not is_connected and show_isolated)
            )
            
            if include_node:
                filtered_nodes.append(node)
            elif node_type == "object" and not is_connected:
                isolated_count += 1
        
        if show_isolated:
            logger.info(f"Generated graph with all {len(filtered_nodes)} nodes and {len(valid_edges)} edges")
        else:
            logger.info(f"Generated graph with {len(filtered_nodes)} nodes (filtered out {isolated_count} isolated objects) and {len(valid_edges)} edges")
            
        return {"nodes": filtered_nodes, "edges": valid_edges}
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
                
        query = session.query(FunctionCall)
        if search:
            search_lower = f"%{search.lower()}%"
            query = query.filter(
                (FunctionCall.function.ilike(search_lower)) |
                (FunctionCall.file.ilike(search_lower))
            )
        if file:
            file_lower = f"%{file.lower()}%"
            query = query.filter(FunctionCall.file.ilike(file_lower))
        if function:
            function_lower = f"%{function.lower()}%"
            query = query.filter(FunctionCall.function.ilike(function_lower))
        function_calls = query.limit(100).all()
        
        # Convert to a serializable format using the model's to_dict method
        result = []
        for fc in function_calls:
            # Use the model's to_dict method as base
            call_data = fc.to_dict()
            
            # Add additional fields for API
            call_data["duration"] = (fc.end_time - fc.start_time).total_seconds() if fc.end_time and fc.start_time else None
            call_data["has_stack_recording"] = session.query(StackSnapshot).filter(StackSnapshot.function_call_id == fc.id).count() > 0
            
            # Add serialized locals
            locals_data = {}
            if fc.locals_refs:
                for name, value in fc.locals_refs.items():
                    locals_data[name] = serialize_stored_value(value)
            call_data["locals"] = locals_data
            
            # Add serialized globals
            globals_data = {}
            if fc.globals_refs:
                for name, value in fc.globals_refs.items():
                    globals_data[name] = serialize_stored_value(value)
            call_data["globals"] = globals_data
            
            # Add serialized return value
            call_data["return_value"] = serialize_stored_value(fc.return_ref)
            
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
    global call_tracker, session
    
    try:
        if call_tracker is None or session is None:
            raise ValueError("Session is not initialized")
                
        call_info = call_tracker.get_call_with_code(call_id)
        if call_info is None:
            raise ValueError(f"Function call {call_id} not found")
        
        # Serialize the call info
        raw_call_info = serialize_call_info(call_info)
        
        # Check if there are any stack recordings for this function call
        has_recordings = session.query(StackSnapshot).filter(
            StackSnapshot.function_call_id == call_id
        ).count() > 0
        raw_call_info["has_stack_recording"] = has_recordings
        
        # Get stack traces for this function call
        stack_trace = []
        if has_recordings:
            stack_snapshots = session.query(StackSnapshot).filter(
                StackSnapshot.function_call_id == call_id
            ).order_by(StackSnapshot.order_in_call.asc()).all()
            
            for snapshot in stack_snapshots:
                # Process locals from the snapshot's locals_refs
                locals_data = {}
                if hasattr(snapshot, 'locals_refs') and snapshot.locals_refs is not None:
                    for name, value in snapshot.locals_refs.items():
                        locals_data[name] = serialize_stored_value(value)
                
                # Process globals from the snapshot's globals_refs
                globals_data = {}
                if hasattr(snapshot, 'globals_refs') and snapshot.globals_refs is not None:
                    for name, value in snapshot.globals_refs.items():
                        # Filter out module-level imports and other large objects
                        if not name.startswith("__") and not name.endswith("__"):
                            globals_data[name] = serialize_stored_value(value)
                
                # Format timestamp if it exists
                timestamp_str = None
                if hasattr(snapshot, 'timestamp') and snapshot.timestamp is not None:
                    timestamp_str = snapshot.timestamp.isoformat()
                
                trace_data = {
                    "id": str(snapshot.id),
                    "line": snapshot.line_number,
                    "timestamp": timestamp_str,
                    "locals": locals_data,
                    "globals": globals_data
                }
                stack_trace.append(trace_data)
        
        raw_call_info["stack_trace"] = stack_trace
        
        # Wrap the call info in a function_call object to match the template's expectation
        return {"function_call": raw_call_info}
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
            call_sequence = ms.get_call_sequence(session)
            session_data = {
                "id": ms.id,
                "name": ms.name,
                "description": ms.description,
                "start_time": ms.start_time.isoformat(),
                "end_time": ms.end_time.isoformat() if ms.end_time else None,
                "duration": ms.duration,  # Use the new duration property
                "function_calls": [f.id for f in call_sequence],
                "function_count": {f.function: sum(1 for x in call_sequence if x.function == f.function) for f in call_sequence},
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
async def get_session_details(session_id: str):
    """Get detailed information about a specific monitoring session"""
    global session
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
        
        # Convert session_id to integer
        try:
            session_id_int = int(session_id)
        except ValueError:
            raise ValueError(f"Invalid session ID: {session_id}")
            
        # Query the monitoring session
        monitoring_session = session.query(MonitoringSession).filter(
            MonitoringSession.id == session_id_int
        ).first()
        
        if not monitoring_session:
            raise ValueError(f"Session {session_id} not found")
        
        # Get function calls in this session
        call_sequence = monitoring_session.get_call_sequence(session)
        
        # Process function calls
        function_calls = []
        function_calls_map = {}
        common_variables = {}
        
        # Track variables that appear in all calls for a given function
        function_variables = {}
        
        for function_call in call_sequence:
            # Store function call ID
            function_calls.append(function_call.id)
            
            # Group by function name
            if function_call.function not in function_calls_map:
                function_calls_map[function_call.function] = []
                function_variables[function_call.function] = {
                    'first_call': True,
                    'locals': None,
                    'globals': None
                }
            
            function_calls_map[function_call.function].append(function_call.id)
            
            # Track common variables across calls to the same function
            if function_variables[function_call.function]['first_call']:
                # First call, initialize sets
                function_variables[function_call.function]['locals'] = set(function_call.locals_refs.keys()) if function_call.locals_refs else set()
                function_variables[function_call.function]['globals'] = set(function_call.globals_refs.keys()) if function_call.globals_refs else set()
                function_variables[function_call.function]['first_call'] = False
            else:
                # Subsequent calls, intersect with existing sets
                locals_keys = set(function_call.locals_refs.keys()) if function_call.locals_refs else set()
                globals_keys = set(function_call.globals_refs.keys()) if function_call.globals_refs else set()
                
                function_variables[function_call.function]['locals'] &= locals_keys
                function_variables[function_call.function]['globals'] &= globals_keys
        
        # Convert function_variables to common_variables format
        for func_name, vars_data in function_variables.items():
            if not vars_data['first_call']:  # Only include functions that were called at least once
                common_variables[func_name] = {
                    'locals': list(vars_data['locals']),
                    'globals': list(vars_data['globals']),
                }
        
        # Build the response
        session_data = {
            "id": monitoring_session.id,
            "name": monitoring_session.name,
            "description": monitoring_session.description,
            "start_time": monitoring_session.start_time.isoformat(),
            "end_time": monitoring_session.end_time.isoformat() if monitoring_session.end_time else None,
            "duration": monitoring_session.duration,  # Use the new duration property
            "function_calls": function_calls,
            "function_calls_map": function_calls_map,
            "function_count": {f.function: sum(1 for x in call_sequence if x.function == f.function) for f in call_sequence},
            "metadata": monitoring_session.session_metadata,
            "common_variables": common_variables
        }
        
        return session_data
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting session details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/function-call/{call_id}/execution-tree")
async def get_execution_tree(call_id: str, max_depth: int = Query(5, description="Maximum depth of execution tree")):
    """Get the hierarchical execution tree for a function call"""
    global session
    
    try:
        if session is None:
            raise ValueError("Session is not initialized")
        
        # Get the function call
        function_call = session.query(FunctionCall).filter(FunctionCall.id == call_id).first()
        if not function_call:
            raise ValueError(f"Function call {call_id} not found")
        
        # Get the execution tree using the model method
        execution_tree = function_call.get_execution_tree(session, max_depth=max_depth)
        
        return {"execution_tree": execution_tree}
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting execution tree: {e}")
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
    call_tracker = FunctionCallRepository(session)
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