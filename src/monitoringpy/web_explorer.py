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
from .models import init_db, StoredObject
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
        # Make sure ref is a string
        ref_str = str(ref)
        
        # First try to get the actual value directly
        try:
            value = object_manager.get(ref_str)
            if value is not None:
                # Successfully reconstructed the value
                if type(value).__name__ == 'MyCustomClass':
                    logger.info(f"Found MyCustomClass in stored value: {value}")
                return {
                    "value": str(value),
                    "type": type(value).__name__
                }
        except Exception as e:
            logger.debug(f"Could not get value directly: {e}")
        
        # If direct access failed, try database
        stored_obj = object_manager.session.query(StoredObject).filter(StoredObject.id == ref_str).first()
        if not stored_obj:
            # If we couldn't get it from database or direct access, it's truly not found
            return {"value": f"<not found: {ref_str}>", "type": "Error"}
            
        if stored_obj.is_primitive:
            return {
                "value": stored_obj.primitive_value,
                "type": stored_obj.type_name
            }
            
        try:
            # Try to get the actual value again (in case we missed it first time)
            value = object_manager.get(ref_str)
            if type(value).__name__ == 'MyCustomClass':
                logger.info(f"Found MyCustomClass in stored object: {value}")
            
            # Get code definition if available
            code_info = None
            if object_manager.code_manager:
                code_info = object_manager.code_manager.get_object_code(ref_str)
            
            return {
                "value": str(value),  # Convert to string to ensure JSON serialization
                "type": stored_obj.type_name,
                "code": code_info
            }
        except (ImportError, AttributeError) as e:
            logger.warning(f"Import/Attribute error for {ref_str}: {e}")
            # If we can't unpickle due to missing class, return a generic representation
            # Still try to get code definition
            code_info = None
            if object_manager.code_manager:
                code_info = object_manager.code_manager.get_object_code(ref_str)
                
            return {
                "value": f"<{stored_obj.type_name} object>",
                "type": stored_obj.type_name,
                "code": code_info
            }
    except Exception as e:
        logger.warning(f"Error serializing stored value {ref}: {e}")
        return {"value": f"<error: {str(e)}>", "type": "Error"}

def serialize_call_info(call_info: FunctionCallInfo) -> Dict[str, Any]:
    """Serialize FunctionCallInfo to JSON-compatible dictionary"""
    logger.debug("Serializing call info")
    # Convert timestamps to ISO format strings first
    start_time = call_info['start_time'].isoformat() if call_info['start_time'] else None
    end_time = call_info['end_time'].isoformat() if call_info['end_time'] else None
    
    try:
        result = {
            'function': call_info['function'],
            'file': call_info['file'],
            'line': call_info['line'],
            'start_time': start_time,
            'end_time': end_time,
            'locals': {k: serialize_stored_value(v) for k, v in call_info['locals'].items()},
            'globals': {k: serialize_stored_value(v) for k, v in call_info['globals'].items()},
            'return_value': serialize_stored_value(call_info['return_value'])
        }
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
    app = Flask(__name__)
    app.json_encoder = CustomJSONEncoder  # Use our custom encoder
    CORS(app)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/graph')
    def graph():
        print("Rendering graph.html")
        return render_template('graph.html')

    @app.route('/api/object-graph')
    def get_object_graph():
        """Get the object graph data for visualization"""
        print("Getting object graph")
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
                            # For custom objects, use their string representation
                            try:
                                label = str(value)
                                logger.debug(f"Custom object string representation: {label}")
                            except Exception as e:
                                logger.warning(f"Failed to get string representation of custom object: {e}")
                                label = f"<{obj.type_name} object>"
                    else:
                        label = f"<{obj.type_name}>"
                except Exception as e:
                    logger.warning(f"Error processing object {obj.id}: {e}")
                    label = f"<{obj.type_name}>"
                
                try:
                    node_data = {
                        'id': obj.id,
                        'label': label[:50] + '...' if len(label) > 50 else label,
                        'type': obj.type_name,
                        'isPrimitive': obj.is_primitive,
                        'nodeType': 'object'  # Mark as object node
                    }
                    logger.debug(f"Created node data: {node_data}")
                    nodes.append({'data': node_data})
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
        search = request.args.get('search', '').lower()
        file_filter = request.args.get('file', '')
        function_filter = request.args.get('function', '')

        # Get all call IDs from history
        all_calls = []
        try:
            call_ids = tracker.get_call_history()
            for call_id in call_ids:
                try:
                    call_info = tracker.get_call(call_id)
                    
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
                except ValueError:
                    continue  # Skip if call not found
        except Exception as e:
            logger.error(f"Error getting function calls: {e}")
            return jsonify({'error': str(e)}), 500

        return jsonify({'function_calls': all_calls})

    @app.route('/api/function-call/<call_id>')
    def get_function_call(call_id):
        try:
            call_info = tracker.get_call(call_id)
            call_dict = serialize_call_info(call_info)
            call_dict['id'] = call_id
            
            # Get call history
            history = tracker.get_call_history()
            call_index = history.index(call_id)
            
            # Add navigation info
            call_dict['prev_call'] = history[call_index - 1] if call_index > 0 else None
            call_dict['next_call'] = history[call_index + 1] if call_index < len(history) - 1 else None
            
            return jsonify({'function_call': call_dict})
        except ValueError as e:
            return jsonify({'error': 'Function call not found'}), 404
        except Exception as e:
            logger.error(f"Error getting function call: {e}")
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