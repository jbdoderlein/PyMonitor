#!/usr/bin/env python3
"""
PyMonitor Web Explorer

A web-based interface for exploring PyMonitor databases.
"""

import os
import sys
import argparse
import logging
import json
import datetime
from pathlib import Path
import webbrowser
import threading
import time
from typing import Dict, Any, List, Optional

try:
    from flask import Flask, render_template, request, jsonify, abort, send_from_directory, Response
    from flask_cors import CORS
except ImportError:
    print("Flask is required for the web explorer. Install it with: pip install flask flask-cors")
    sys.exit(1)

from sqlalchemy.orm import Session
from .models import (
    init_db, StoredObject, FunctionCall, StackSnapshot, 
    CodeDefinition
)
from .function_call import FunctionCallTracker, FunctionCallInfo
from .representation import Object, Primitive, List, DictObject, CustomClass, ObjectManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables
call_tracker = None
session = None
db_path = None
object_manager = None

# Create templates directory if it doesn't exist
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
os.makedirs(template_dir, exist_ok=True)

# Create static directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), 'static')
os.makedirs(static_dir, exist_ok=True)

# JSON encoder for datetime objects and custom objects
class CustomJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects and custom objects"""
    def default(self, obj):
        logger.debug(f"Attempting to serialize object of type: {type(obj).__name__}")
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        try:
            # Try to convert to a basic type that json can handle
            if type(obj).__name__ == 'MyCustomClass':
                logger.info(f"Found MyCustomClass: {obj}, attempting to serialize")
                result = str(obj)
                logger.info(f"MyCustomClass serialized to: {result}")
                return result
            if hasattr(obj, '__dict__'):
                return str(obj)  # Convert custom objects to their string representation
            return str(obj)  # Fallback to string representation
        except Exception as e:
            logger.error(f"Error serializing object of type {type(obj).__name__}: {e}")
            return f"<{type(obj).__name__} object>"  # Last resort fallback

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

def serialize_call_info(call_info: FunctionCallInfo) -> Dict[str, Any]:
    """Serialize FunctionCallInfo to JSON-compatible dictionary"""
    global session  # Access the global session variable
    
    logger.debug("Serializing call info")
    # Convert timestamps to ISO format strings first
    start_time = call_info['start_time'].isoformat() if call_info['start_time'] else None
    end_time = call_info['end_time'].isoformat() if call_info['end_time'] else None
    
    try:
        # Handle locals and globals, ensuring we don't pass None values to serialize_stored_value
        locals_dict = {}
        for k, v in call_info['locals'].items():
            if v is not None:
                locals_dict[k] = serialize_stored_value(v)
            else:
                locals_dict[k] = {"value": "None", "type": "NoneType"}

        globals_dict = {}
        for k, v in call_info['globals'].items():
            if v is not None:
                globals_dict[k] = serialize_stored_value(v)
            else:
                globals_dict[k] = {"value": "None", "type": "NoneType"}

        # Handle return value
        return_value = serialize_stored_value(call_info['return_value']) if call_info['return_value'] is not None else {"value": "None", "type": "NoneType"}

        result = {
            'function': call_info['function'],
            'file': call_info['file'],
            'line': call_info['line'],
            'start_time': start_time,
            'end_time': end_time,
            'locals': locals_dict,
            'globals': globals_dict,
            'return_value': return_value,
            'has_stack_trace': False  # Default value
        }

        # Check if this function call has a stack trace
        try:
            if session:
                call = session.query(FunctionCall).filter_by(id=int(call_info.get('id', 0))).first()
                if call and call.first_snapshot_id:
                    result['has_stack_trace'] = True
        except Exception as e:
            logger.warning(f"Failed to check for stack trace: {e}")
            if session and "transaction has been rolled back" in str(e):
                try:
                    session.rollback()
                except:
                    pass

        # Add RAPL data if available
        if 'energy_data' in call_info:
            result['energy_data'] = call_info['energy_data']
            
        # Add code information if available
        if 'code' in call_info and call_info['code']:
            result['code'] = call_info['code']
        elif 'code_definition_id' in call_info and call_info['code_definition_id'] and session:
            try:
                # Use raw SQL query to avoid SQLAlchemy parameter binding issues with string IDs
                from sqlalchemy import text
                sql = text("SELECT * FROM code_definitions WHERE id = :id")
                query_result = session.execute(sql, {"id": call_info['code_definition_id']})
                row = query_result.fetchone()
                if row:
                    result['code'] = {
                        'content': row.code_content,
                        'module_path': row.module_path,
                        'type': row.type,
                        'first_line_no': row.first_line_no
                    }
                    logger.info(f"Found code definition for {call_info['function']}")
            except Exception as e:
                logger.warning(f"Failed to get code definition: {e}")
                # Ensure session is valid for future queries
                if session and "transaction has been rolled back" in str(e):
                    try:
                        session.rollback()
                    except:
                        pass
        
        # Test JSON serialization
        try:
            json.dumps(result, cls=CustomJSONEncoder)
            logger.debug("Call info successfully serialized to JSON")
        except Exception as e:
            logger.error(f"Failed to serialize call info to JSON: {e}")
            # Try to identify which part failed
            for key, value in result.items():
                try:
                    json.dumps(value, cls=CustomJSONEncoder)
                except Exception as e:
                    logger.error(f"Failed to serialize {key}: {e}")
        return result
    except Exception as e:
        logger.error(f"Error in serialize_call_info: {e}")
        raise

def create_app(tracker: FunctionCallTracker):
    global call_tracker, session, object_manager
    
    app = Flask(__name__)
    app.json_encoder = CustomJSONEncoder  # Use our custom encoder
    CORS(app)
    
    call_tracker = tracker
    session = tracker.session
    object_manager = tracker.object_manager

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/graph')
    def graph():
        print("Rendering graph.html")
        return render_template('graph.html')

    @app.route('/stack-traces')
    def stack_traces():
        """View for listing functions with stack traces"""
        return render_template('stack_traces.html')

    @app.route('/stack-trace/<function_id>')
    def stack_trace(function_id):
        """View for displaying a specific function's stack trace"""
        return render_template('stack_trace.html')

    @app.route('/compare-traces')
    def compare_traces():
        return render_template('compare_traces.html')

    @app.route('/api/functions-with-traces')
    def get_functions_with_traces():
        """Get list of functions that have stack traces"""
        try:
            if not session:
                return jsonify({'error': 'Database session not initialized'}), 500
                
            # Query for unique functions that have stack traces
            functions = (session.query(FunctionCall.function, FunctionCall.file, FunctionCall.line)
                       .filter(FunctionCall.first_snapshot_id.isnot(None))
                       .group_by(FunctionCall.function, FunctionCall.file, FunctionCall.line)
                       .all())
            
            result = []
            for func in functions:
                # Get all calls for this function to count total traces
                calls = (session.query(FunctionCall)
                        .filter(FunctionCall.function == func.function,
                               FunctionCall.file == func.file,
                               FunctionCall.line == func.line,
                               FunctionCall.first_snapshot_id.isnot(None))
                        .order_by(FunctionCall.start_time.desc())  # Get most recent first
                        .all())
                
                if calls:
                    # Process each call for this function
                    traces = []
                    total_snapshots = 0
                    
                    for call in calls:
                        # Count snapshots for this call
                        snapshot_count = 0
                        current_snapshot = call.first_snapshot
                        while current_snapshot:
                            snapshot_count += 1
                            current_snapshot = current_snapshot.next_snapshot
                        
                        total_snapshots += snapshot_count
                        
                        # Add trace info
                        traces.append({
                            'id': call.id,
                            'timestamp': call.start_time.isoformat() if call.start_time else None,
                            'snapshot_count': snapshot_count,
                            'execution_time': (call.end_time - call.start_time).total_seconds() if call.end_time and call.start_time else None
                        })
                    
                    result.append({
                        'id': calls[0].id,  # Use first call as reference
                        'name': func.function,
                        'file': func.file,
                        'line': func.line,
                        'trace_count': len(calls),
                        'total_snapshots': total_snapshots,
                        'last_executed': calls[0].start_time.isoformat() if calls[0].start_time else None,
                        'traces': traces  # Include all traces
                    })
            
            # Sort by function name
            result.sort(key=lambda x: x['name'])
            
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error getting functions with traces: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/stack-trace/<function_id>')
    def get_stack_trace(function_id):
        """Get the stack trace for a specific function call"""
        try:
            if not session:
                return jsonify({'error': 'Database session not initialized'}), 500
                
            # Get the function call by ID
            function = session.query(FunctionCall).get(function_id)
            if not function or not function.first_snapshot:
                return jsonify({'error': 'Function call not found or has no stack trace'}), 404
            
            # Create result dictionary with function info
            result = {
                'function_id': function.id,
                'function_name': function.function,
                'file': function.file,
                'line': function.line,
                'start_time': function.start_time.isoformat() if function.start_time else None,
                'end_time': function.end_time.isoformat() if function.end_time else None,
                'snapshots': []
            }
            
            # Try to get the source code from the database instead of the file system
            try:
                # First check if there's a code_definition_id associated with this function call
                if hasattr(function, 'code_definition_id') and function.code_definition_id:
                    # Use raw SQL query to avoid SQLAlchemy parameter binding issues with string IDs
                    from sqlalchemy import text
                    sql = text("SELECT * FROM code_definitions WHERE id = :id")
                    query_result = session.execute(sql, {"id": function.code_definition_id})
                    row = query_result.fetchone()
                    if row:
                        result['code'] = {
                            'content': row.code_content,
                            'module_path': row.module_path,
                            'type': row.type,
                            'first_line_no': row.first_line_no
                        }
                        logger.info(f"Found code definition in database for function {function.function}")
                # If no code in database, fall back to file system as before
                elif os.path.exists(function.file):
                    with open(function.file, 'r') as f:
                        content = f.read()
                        result['code'] = {
                            'content': content,
                            'file': function.file,
                            'first_line_no': 1  # Default to 1 when reading from file
                        }
                    logger.info(f"Read code from file: {function.file}")
            except Exception as e:
                logger.error(f"Error reading source code: {e}")
                
            # Build the trace by following the linked list
            current = function.first_snapshot
            while current:
                snapshot = {
                    'id': current.id,
                    'line': current.line_number,
                    'timestamp': current.timestamp.isoformat() if current.timestamp else None,
                    'locals': {},
                    'globals': {}
                }
                
                # Add local variables
                if current.locals_refs:
                    for name, ref in current.locals_refs.items():
                        if ref and object_manager:
                            try:
                                snapshot['locals'][name] = serialize_stored_value(ref)
                            except Exception as e:
                                logger.error(f"Error serializing local variable {name}: {e}")
                                snapshot['locals'][name] = {"value": f"<error: {str(e)}>", "type": "Error"}
                
                # Add global variables
                if current.globals_refs:
                    for name, ref in current.globals_refs.items():
                        if ref and object_manager:
                            try:
                                snapshot['globals'][name] = serialize_stored_value(ref)
                            except Exception as e:
                                logger.error(f"Error serializing global variable {name}: {e}")
                                snapshot['globals'][name] = {"value": f"<error: {str(e)}>", "type": "Error"}
                
                result['snapshots'].append(snapshot)
                current = current.next_snapshot
            
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error getting stack trace: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/snapshot/<snapshot_id>')
    def get_snapshot(snapshot_id):
        """Get detailed information about a specific stack snapshot"""
        try:
            snapshot = session.query(StackSnapshot).get(snapshot_id)
            if not snapshot:
                return jsonify({'error': 'Snapshot not found'}), 404
            
            result = {
                'id': snapshot.id,
                'line': snapshot.line_number,
                'timestamp': snapshot.timestamp.isoformat(),
                'locals': {
                    name: serialize_stored_value(ref)
                    for name, ref in snapshot.locals_refs.items()
                },
                'globals': {
                    name: serialize_stored_value(ref)
                    for name, ref in snapshot.globals_refs.items()
                }
            }
            
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error getting snapshot: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/object-graph')
    def get_object_graph():
        """Get the object graph data for visualization"""
        try:
            logger.info("Starting object graph generation")
            # Get all stored objects and function calls
            objects = object_manager.session.query(StoredObject).all()
            call_ids = call_tracker.get_call_history()
            
            logger.info(f"Found {len(objects)} objects and {len(call_ids)} function calls")
            
            # Prepare nodes and edges for the graph
            nodes = []
            edges = []
            seen_objects = set()
            node_ids = set()  # Track which nodes we've created
            
            # First pass: Create all nodes for stored objects
            for obj in objects:
                if obj.id in seen_objects:
                    continue
                seen_objects.add(obj.id)
                node_ids.add(obj.id)
                
                try:
                    logger.debug(f"Processing object {obj.id} of type {obj.type_name}")
                    value = object_manager.get(obj.id)
                    # Convert value to string safely
                    if value is not None:
                        logger.debug(f"Object value type: {type(value)}")
                        if isinstance(value, (int, float, bool, str)):
                            label = str(value)
                        elif isinstance(value, (list, tuple)):
                            label = f"[{', '.join(str(x) for x in value[:3])}{'...' if len(value) > 3 else ''}]"
                        elif isinstance(value, dict):
                            items = [f"{k}: {v}" for k, v in list(value.items())[:3]]
                            label = f"{{{', '.join(items)}{'...' if len(value) > 3 else ''}}}"
                        else:
                            # For custom objects, use type_name from database and string representation
                            try:
                                value_str = str(value)
                                # Extract any parameters from the string representation
                                params = value_str.split('(', 1)[1].rstrip(')') if '(' in value_str else ''
                                label = f"{obj.type_name}({params})" if params else obj.type_name
                                logger.debug(f"Custom object label: {label}")
                            except Exception as e:
                                logger.warning(f"Failed to get string representation of custom object: {e}")
                                label = f"{obj.type_name}()"
                    else:
                        label = f"{obj.type_name}()"
                except Exception as e:
                    logger.warning(f"Error processing object {obj.id}: {e}")
                    label = f"<{obj.type_name}>"
                
                try:
                    node_data = {
                        'id': obj.id,
                        'label': label[:50] + '...' if len(label) > 50 else label,
                        'type': obj.type_name,  # This is now the actual class name
                        'isPrimitive': obj.is_primitive,
                        'nodeType': 'object'  # Mark as object node
                    }
                    logger.debug(f"Created node data: {node_data}")
                    nodes.append({'data': node_data})

                    # Add code version node if available
                    if object_manager.code_manager:
                        try:
                            code_info = object_manager.code_manager.get_object_code(obj.id)
                            if code_info and isinstance(code_info, dict):
                                # Ensure all required fields are present
                                required_fields = {'id', 'name', 'code', 'module_path'}
                                if not all(field in code_info for field in required_fields):
                                    logger.warning(f"Incomplete code info for object {obj.id}: missing fields {required_fields - code_info.keys()}")
                                    continue

                                code_version_id = f"code_{code_info['id']}"
                                if code_version_id not in node_ids:
                                    node_ids.add(code_version_id)
                                    print(f"code_info: {code_info}")
                                    code_node_data = {
                                        'id': code_version_id,
                                        'label': f"{code_info['name']} v{code_info.get('version_number', '1')}",
                                        'type': 'CodeVersion',
                                        'isPrimitive': False,
                                        'nodeType': 'code',
                                        'className': code_info['name'],
                                        'version': code_info.get('version_number', '1'),
                                        'modulePath': code_info['module_path'],
                                        'code': code_info['code']
                                    }
                                    nodes.append({'data': code_node_data})
                                    logger.debug(f"Created code version node: {code_version_id}")

                                    # Only create the edge if we successfully created the node
                                    edge_data = {
                                        'id': f"edge_code_{obj.id}_{code_version_id}",
                                        'source': obj.id,
                                        'target': code_version_id,
                                        'label': 'implements',
                                        'edgeType': 'code_version'
                                    }
                                    edges.append({'data': edge_data})
                                    logger.debug(f"Created code version edge: {edge_data}")
                                else:
                                    # If the node already exists, just add the edge
                                    edge_data = {
                                        'id': f"edge_code_{obj.id}_{code_version_id}",
                                        'source': obj.id,
                                        'target': code_version_id,
                                        'label': 'implements',
                                        'edgeType': 'code_version'
                                    }
                                    edges.append({'data': edge_data})
                                    logger.debug(f"Created code version edge for existing node: {edge_data}")
                            else:
                                logger.debug(f"No valid code info found for object {obj.id}")
                        except Exception as e:
                            logger.warning(f"Error creating code version node for object {obj.id}: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Error creating node data for object {obj.id}: {e}")
                    continue
            
            logger.info(f"Created {len(nodes)} nodes for objects")
            # Add nodes for function calls
            for call_id in call_ids:
                try:
                    logger.debug(f"Processing function call {call_id}")
                    call_info = call_tracker.get_call(call_id)
                    # Convert timestamps to ISO format strings
                    start_time = call_info['start_time'].isoformat() if call_info['start_time'] else None
                    end_time = call_info['end_time'].isoformat() if call_info['end_time'] else None
                    
                    try:
                        node_data = {
                            'id': f"call_{call_id}",
                            'label': f"{call_info['function']}()",
                            'type': 'FunctionCall',
                            'isPrimitive': False,
                            'nodeType': 'function',  # Mark as function node
                            'file': call_info['file'],
                            'line': call_info['line'],
                            'startTime': start_time,
                            'endTime': end_time
                        }
                        logger.debug(f"Created function node data: {node_data}")
                        nodes.append({'data': node_data})
                    except Exception as e:
                        logger.error(f"Error creating function node data for call {call_id}: {e}")
                        continue
                    
                    # Add edges for local variables
                    for var_name, var_ref in call_info['locals'].items():
                        if var_ref is not None:
                            try:
                                # Convert non-string references to their stored object IDs
                                if not isinstance(var_ref, str):
                                    # Try to store the value and get its reference
                                    try:
                                        var_ref = object_manager.store(var_ref)
                                        logger.debug(f"Stored local var {var_name} with ref {var_ref}")
                                    except Exception as e:
                                        logger.warning(f"Could not store local var {var_name}: {e}")
                                        continue
                                
                                # Verify the target exists in our nodes
                                if not any(node['data']['id'] == var_ref for node in nodes):
                                    logger.warning(f"Target node {var_ref} not found for local var {var_name}")
                                    continue
                                
                                edge_data = {
                                    'id': f"edge_local_{call_id}_{var_name}",
                                    'source': f"call_{call_id}",
                                    'target': var_ref,
                                    'label': f'local:{var_name}',
                                    'edgeType': 'function_var'
                                }
                                logger.debug(f"Created local var edge: {edge_data}")
                                edges.append({'data': edge_data})
                            except Exception as e:
                                logger.error(f"Error creating edge for local var {var_name}: {e}")
                    
                    # Add edges for global variables
                    for var_name, var_ref in call_info['globals'].items():
                        if var_ref is not None:
                            try:
                                # Convert non-string references to their stored object IDs
                                if not isinstance(var_ref, str):
                                    # Try to store the value and get its reference
                                    try:
                                        var_ref = object_manager.store(var_ref)
                                        logger.debug(f"Stored global var {var_name} with ref {var_ref}")
                                    except Exception as e:
                                        logger.warning(f"Could not store global var {var_name}: {e}")
                                        continue
                                
                                # Verify the target exists in our nodes
                                if not any(node['data']['id'] == var_ref for node in nodes):
                                    logger.warning(f"Target node {var_ref} not found for global var {var_name}")
                                    continue
                                
                                edge_data = {
                                    'id': f"edge_global_{call_id}_{var_name}",
                                    'source': f"call_{call_id}",
                                    'target': var_ref,
                                    'label': f'global:{var_name}',
                                    'edgeType': 'function_var'
                                }
                                logger.debug(f"Created global var edge: {edge_data}")
                                edges.append({'data': edge_data})
                            except Exception as e:
                                logger.error(f"Error creating edge for global var {var_name}: {e}")
                    
                    # Add edge for return value
                    if call_info['return_value'] is not None:
                        try:
                            return_ref = call_info['return_value']
                            # Convert non-string references to their stored object IDs
                            if not isinstance(return_ref, str):
                                # Try to store the value and get its reference
                                try:
                                    return_ref = object_manager.store(return_ref)
                                    logger.debug(f"Stored return value with ref {return_ref}")
                                except Exception as e:
                                    logger.warning(f"Could not store return value: {e}")
                                    continue
                            
                            if any(node['data']['id'] == return_ref for node in nodes):
                                edge_data = {
                                    'id': f"edge_return_{call_id}",
                                    'source': f"call_{call_id}",
                                    'target': return_ref,
                                    'label': 'return',
                                    'edgeType': 'function_return'
                                }
                                logger.debug(f"Created return value edge: {edge_data}")
                                edges.append({'data': edge_data})
                            else:
                                logger.warning(f"Target node {return_ref} not found for return value")
                        except Exception as e:
                            logger.error(f"Error creating edge for return value: {e}")
                except Exception as e:
                    logger.error(f"Error processing function call {call_id}: {e}")
            
            logger.info(f"Created {len(edges)} edges")
            
            # Convert to JSON-safe format
            try:
                # First test nodes and edges separately with detailed logging
                logger.info("Testing nodes serialization...")
                nodes_json = json.dumps({'nodes': nodes}, cls=CustomJSONEncoder)
                logger.info("Nodes serialized successfully")
                logger.debug(f"First node example: {json.dumps(nodes[0] if nodes else {}, cls=CustomJSONEncoder)}")
                
                logger.info("Testing edges serialization...")
                edges_json = json.dumps({'edges': edges}, cls=CustomJSONEncoder)
                logger.info("Edges serialized successfully")
                logger.debug(f"First edge example: {json.dumps(edges[0] if edges else {}, cls=CustomJSONEncoder)}")
                
                # Now try to combine them
                logger.info("Attempting to combine nodes and edges...")
                result = {'nodes': nodes, 'edges': edges}
                
                # Instead of using jsonify directly, manually serialize with our encoder
                final_json = json.dumps(result, cls=CustomJSONEncoder)
                logger.info("Successfully serialized complete graph data to JSON")
                
                # Return a Response object with the correct content type
                return Response(
                    final_json,
                    mimetype='application/json'
                )
            except Exception as e:
                logger.error(f"Error serializing graph data to JSON: {e}")
                # Try to identify if the problem is in the structure
                logger.error(f"Nodes count: {len(nodes)}, Edges count: {len(edges)}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception args: {e.args}")
                
                # Return a reduced dataset for debugging
                safe_nodes = []
                safe_edges = []
                
                # Try to find which nodes and edges can be serialized
                for node in nodes[:20]:  # Test first 20 nodes
                    try:
                        json.dumps(node, cls=CustomJSONEncoder)
                        safe_nodes.append(node)
                    except Exception as e:
                        logger.error(f"Cannot serialize node {node.get('data', {}).get('id')}: {e}")
                
                for edge in edges[:20]:  # Test first 20 edges
                    try:
                        json.dumps(edge, cls=CustomJSONEncoder)
                        safe_edges.append(edge)
                    except Exception as e:
                        logger.error(f"Cannot serialize edge {edge.get('data', {}).get('id')}: {e}")
                
                error_response = json.dumps({
                    'error': str(e),
                    'debug_info': {
                        'safe_nodes': safe_nodes[:5],  # Send first 5 safe nodes
                        'safe_edges': safe_edges[:5],  # Send first 5 safe edges
                        'total_nodes': len(nodes),
                        'total_edges': len(edges),
                        'safe_nodes_count': len(safe_nodes),
                        'safe_edges_count': len(safe_edges)
                    }
                }, cls=CustomJSONEncoder)
                
                return Response(error_response, status=500, mimetype='application/json')
        except Exception as e:
            logger.error(f"Error generating object graph: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/db-info')
    def get_db_info():
        global db_path
        return jsonify({'db_path': db_path})

    @app.route('/api/function-calls')
    def get_function_calls():
        try:
            search = request.args.get('search', '').lower()
            file_filter = request.args.get('file', '')
            function_filter = request.args.get('function', '')

            # Get all call IDs from history
            all_calls = []
            
            if not call_tracker:
                logger.error("Call tracker is not initialized")
                return jsonify({
                    'error': 'Call tracker is not initialized',
                    'function_calls': []
                }), 500

            try:
                logger.info("Getting call history...")
                call_ids = call_tracker.get_call_history()
                logger.info(f"Found {len(call_ids)} calls in history")
                
                for call_id in call_ids:
                    try:
                        logger.debug(f"Getting call info for {call_id}")
                        call_info = call_tracker.get_call(call_id)
                        if not call_info:
                            logger.warning(f"No call info found for ID {call_id}")
                            continue
                        
                        # Apply filters
                        if search and search not in call_info['function'].lower():
                            continue
                        if file_filter and file_filter != call_info['file']:
                            continue
                        if function_filter and function_filter != call_info['function']:
                            continue
                        
                        # Add call ID to the serialized info
                        call_dict = serialize_call_info(call_info)
                        call_dict['id'] = call_id
                        all_calls.append(call_dict)
                        
                    except Exception as e:
                        logger.error(f"Error processing call {call_id}: {e}", exc_info=True)
                        continue  # Skip problematic calls but continue processing others

                logger.info(f"Successfully processed {len(all_calls)} calls")
                return jsonify({
                    'function_calls': all_calls,
                    'total_calls': len(call_ids),
                    'processed_calls': len(all_calls)
                })
                
            except Exception as e:
                logger.error(f"Error getting call history: {e}", exc_info=True)
                return jsonify({
                    'error': f"Error getting call history: {str(e)}",
                    'function_calls': []
                }), 500
                
        except Exception as e:
            logger.error(f"Unexpected error in get_function_calls: {e}", exc_info=True)
            return jsonify({
                'error': f"Unexpected error: {str(e)}",
                'function_calls': []
            }), 500

    @app.route('/function-call/<call_id>')
    def function_call(call_id):
        """View for a specific function call"""
        return render_template('function_call.html')

    @app.route('/api/function-call/<call_id>')
    def get_function_call(call_id):
        try:
            call_info = call_tracker.get_call(call_id)
            call_dict = serialize_call_info(call_info)
            call_dict['id'] = call_id
            
            # Get call history
            history = call_tracker.get_call_history()
            
            try:
                call_index = history.index(call_id)
                # Add navigation info
                call_dict['prev_call'] = history[call_index - 1] if call_index > 0 else None
                call_dict['next_call'] = history[call_index + 1] if call_index < len(history) - 1 else None
            except (ValueError, IndexError) as e:
                logger.warning(f"Error finding call in history: {e}")
                call_dict['prev_call'] = None
                call_dict['next_call'] = None
            
            # Get stack trace for this call
            try:
                if call_tracker and session:
                    call = session.query(FunctionCall).filter_by(id=int(call_id)).first()
                    if call and call.first_snapshot_id:
                        stack_snapshots = []
                        current_snapshot = session.query(StackSnapshot).filter_by(id=call.first_snapshot_id).first()
                        
                        while current_snapshot:
                            snapshot_data = {
                                'line': current_snapshot.line_number,
                                'timestamp': current_snapshot.timestamp.isoformat(),
                                'locals': {},
                                'globals': {}
                            }
                            
                            # Process local variables
                            for name, ref in current_snapshot.locals_refs.items():
                                try:
                                    snapshot_data['locals'][name] = serialize_stored_value(ref)
                                except Exception as e:
                                    logger.error(f"Error serializing local {name}: {e}")
                                    snapshot_data['locals'][name] = {'value': f"<Error: {str(e)}>", 'type': 'Error'}
                            
                            # Process global variables
                            for name, ref in current_snapshot.globals_refs.items():
                                try:
                                    snapshot_data['globals'][name] = serialize_stored_value(ref)
                                except Exception as e:
                                    logger.error(f"Error serializing global {name}: {e}")
                                    snapshot_data['globals'][name] = {'value': f"<Error: {str(e)}>", 'type': 'Error'}
                            
                            stack_snapshots.append(snapshot_data)
                            
                            # Get next snapshot
                            if current_snapshot.next_snapshot_id:
                                current_snapshot = session.query(StackSnapshot).filter_by(id=current_snapshot.next_snapshot_id).first()
                            else:
                                break
                        
                        call_dict['stack_trace'] = stack_snapshots
            except Exception as e:
                logger.error(f"Error getting stack trace: {e}")
                call_dict['stack_trace'] = []
            
            return jsonify({'function_call': call_dict})
        except ValueError as e:
            return jsonify({'error': 'Function call not found'}), 404
        except Exception as e:
            logger.error(f"Error getting function call: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/function-traces/<int:function_id>')
    def get_function_traces(function_id):
        """Get all traces for a specific function"""
        try:
            if not session:
                return jsonify({'error': 'Database session not initialized'}), 500
            
            # Get the function call to get its details
            function = session.query(FunctionCall).get(function_id)
            if not function:
                return jsonify({'error': 'Function not found'}), 404
            
            # Get all calls for this function that have traces
            function_calls = (session.query(FunctionCall)
                .filter(FunctionCall.function == function.function,
                       FunctionCall.file == function.file,
                       FunctionCall.line == function.line,
                       FunctionCall.first_snapshot_id.isnot(None))
                .order_by(FunctionCall.start_time.desc())
                .all())
            
            result = {
                'traces': [{
                    'id': call.id,
                    'timestamp': call.start_time.isoformat() if call.start_time else None,
                    'snapshots': []
                } for call in function_calls]
            }
            
            # For each function call, get its stack snapshots
            for trace in result['traces']:
                call = next(c for c in function_calls if c.id == trace['id'])
                current_snapshot = call.first_snapshot
                
                while current_snapshot:
                    snapshot_data = {
                        'line': current_snapshot.line_number,
                        'locals': {},
                        'globals': {}
                    }
                    
                    # Add local variables
                    if current_snapshot.locals_refs:
                        for name, ref in current_snapshot.locals_refs.items():
                            if ref and object_manager:
                                try:
                                    value = object_manager.get(ref)
                                    snapshot_data['locals'][name] = {
                                        'type': type(value).__name__,
                                        'value': str(value)
                                    }
                                except Exception as e:
                                    logger.error(f"Error getting local variable {name}: {e}")
                                    snapshot_data['locals'][name] = {
                                        'type': 'Error',
                                        'value': f"<error: {str(e)}>"
                                    }
                    
                    # Add global variables
                    if current_snapshot.globals_refs:
                        for name, ref in current_snapshot.globals_refs.items():
                            if ref and object_manager:
                                try:
                                    value = object_manager.get(ref)
                                    snapshot_data['globals'][name] = {
                                        'type': type(value).__name__,
                                        'value': str(value)
                                    }
                                except Exception as e:
                                    logger.error(f"Error getting global variable {name}: {e}")
                                    snapshot_data['globals'][name] = {
                                        'type': 'Error',
                                        'value': f"<error: {str(e)}>"
                                    }
                    
                    trace['snapshots'].append(snapshot_data)
                    current_snapshot = current_snapshot.next_snapshot
            
            return jsonify(result)
                
        except Exception as e:
            logger.error(f"Error getting function traces: {e}")
            return jsonify({'error': str(e)}), 500

    return app

def open_browser(url):
    """Open the browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open(url)

def run_explorer(db_file, host='127.0.0.1', port=5000, debug=False, open_browser_flag=True):
    """
    Run the web explorer.
    
    Args:
        db_file: Path to the database file
        host: Host to run the server on
        port: Port to run the server on
        debug: Whether to run in debug mode
        open_browser_flag: Whether to open a browser automatically
    """
    global call_tracker, session, db_path, object_manager
    
    # Check if the database file exists
    if not os.path.exists(db_file):
        logger.error(f"Database file not found: {db_file}")
        sys.exit(1)
    
    # Initialize the database and tracker
    db_path = db_file
    Session = init_db(db_file)
    session = Session()
    object_manager = ObjectManager(session)
    call_tracker = FunctionCallTracker(session)
    
    # Open browser after a delay
    if open_browser_flag:
        url = f"http://{host}:{port}"
        threading.Timer(1.5, open_browser, args=[url]).start()
    
    # Run the Flask app
    app = create_app(call_tracker)
    try:
        app.run(host=host, port=port, debug=debug)
    finally:
        if session:
            session.close()

def main():
    """Command-line entry point"""
    parser = argparse.ArgumentParser(description="PyMonitor Web Explorer")
    parser.add_argument("db_path", help="Path to the database file to explore")
    parser.add_argument("--host", default="127.0.0.1", help="Host to run the server on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the server on (default: 5000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    
    args = parser.parse_args()
    
    run_explorer(
        args.db_path, 
        host=args.host, 
        port=args.port, 
        debug=args.debug, 
        open_browser_flag=not args.no_browser
    )

if __name__ == "__main__":
    main()

# Module entry point
def __main__():
    """Entry point for running as a module"""
    main()