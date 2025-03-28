#!/usr/bin/env python3
"""
PyMonitor MCP Server

A Model Context Protocol (MCP) server for exploring PyMonitor function execution data.
"""

import os
import sys
import logging
import argparse
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import AnyUrl

from .models import init_db, StoredObject, FunctionCall, StackSnapshot, CodeDefinition
from .function_call import FunctionCallTracker
from .representation import ObjectManager

# Configure logging to both file and console
log_dir = Path.home() / ".pymonitor" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"mcp_server_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Create file handler
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatters and add them to the handlers
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
console_handler.setFormatter(console_formatter)

# Get the logger and add the handlers
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

logger.info(f"Starting MCP server with log file: {log_file}")

class FunctionCallInfo:
    """Information about a function call"""
    def __init__(self):
        self.function: str = ""
        self.file: str = ""
        self.line: int = 0
        self.start_time: Optional[datetime.datetime] = None
        self.end_time: Optional[datetime.datetime] = None
        self.locals: Dict[str, Any] = {}
        self.globals: Dict[str, Any] = {}
        self.return_value: Optional[Any] = None
        self.id: Optional[str] = None
        self.prev_call: Optional[str] = None
        self.next_call: Optional[str] = None
        self.stack_trace: Optional[List[Dict[str, Any]]] = None

class PyMonitorDatabase:
    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path).expanduser())
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found: {self.db_path}")
        
        # Initialize database and components
        Session = init_db(self.db_path)
        self.session = Session()
        self.object_manager = ObjectManager(self.session)
        self.call_tracker = FunctionCallTracker(self.session)

    def get_function_calls(self, search: str = "", file_filter: str = "", function_filter: str = "") -> List[Dict[str, Any]]:
        """Get function calls with optional filters"""
        try:
            call_ids = self.call_tracker.get_call_history()
            all_calls = []
            
            for call_id in call_ids:
                call_info = self.call_tracker.get_call(call_id)
                if not call_info:
                    continue
                
                # Apply filters
                if search and search.lower() not in call_info['function'].lower():
                    continue
                if file_filter and file_filter != call_info['file']:
                    continue
                if function_filter and function_filter != call_info['function']:
                    continue
                
                # Convert to dict and add call ID
                call_dict = dict(call_info)
                call_dict['id'] = call_id
                all_calls.append(call_dict)
            
            return all_calls
        except Exception as e:
            logger.error(f"Error getting function calls: {e}")
            raise

    def get_function_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific function call"""
        try:
            call_info = self.call_tracker.get_call(call_id)
            if not call_info:
                return None
            
            # Convert to dict
            call_dict = dict(call_info)
            
            # Get call history for navigation
            history = self.call_tracker.get_call_history()
            try:
                call_index = history.index(call_id)
                call_dict['prev_call'] = history[call_index - 1] if call_index > 0 else None
                call_dict['next_call'] = history[call_index + 1] if call_index < len(history) - 1 else None
            except (ValueError, IndexError):
                call_dict['prev_call'] = None
                call_dict['next_call'] = None
            
            # Get stack trace if available
            call = self.session.query(FunctionCall).filter_by(id=int(call_id)).first()
            if call and call.first_snapshot_id:
                stack_snapshots = []
                current_snapshot = self.session.query(StackSnapshot).filter_by(id=call.first_snapshot_id).first()
                
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
                            snapshot_data['locals'][name] = self._serialize_stored_value(ref)
                        except Exception as e:
                            logger.error(f"Error serializing local {name}: {e}")
                            snapshot_data['locals'][name] = {'value': f"<Error: {str(e)}>", 'type': 'Error'}
                    
                    # Process global variables
                    for name, ref in current_snapshot.globals_refs.items():
                        try:
                            snapshot_data['globals'][name] = self._serialize_stored_value(ref)
                        except Exception as e:
                            logger.error(f"Error serializing global {name}: {e}")
                            snapshot_data['globals'][name] = {'value': f"<Error: {str(e)}>", 'type': 'Error'}
                    
                    stack_snapshots.append(snapshot_data)
                    
                    # Get next snapshot
                    if current_snapshot.next_snapshot_id:
                        current_snapshot = self.session.query(StackSnapshot).filter_by(id=current_snapshot.next_snapshot_id).first()
                    else:
                        break
                
                call_dict['stack_trace'] = stack_snapshots
            
            return call_dict
        except Exception as e:
            logger.error(f"Error getting function call: {e}")
            raise

    def _serialize_stored_value(self, ref: Optional[str]) -> Dict[str, Any]:
        """Serialize a stored value"""
        if ref is None:
            return {"value": "None", "type": "NoneType"}
            
        try:
            value = self.object_manager.get(ref)
            if value is None:
                return {"value": f"<not found: {ref}>", "type": "Error"}
                
            # Get code definition if available
            code_info = None
            if self.object_manager.code_manager:
                code_info = self.object_manager.code_manager.get_object_code(ref)
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

    def get_object_graph(self) -> Dict[str, Any]:
        """Get the object graph data for visualization"""
        try:
            # Get all stored objects and function calls
            objects = self.session.query(StoredObject).all()
            call_ids = self.call_tracker.get_call_history()
            
            # Prepare nodes and edges
            nodes = []
            edges = []
            seen_objects = set()
            node_ids = set()
            
            # Create nodes for stored objects
            for obj in objects:
                if obj.id in seen_objects:
                    continue
                seen_objects.add(obj.id)
                node_ids.add(obj.id)
                
                try:
                    value = self.object_manager.get(obj.id)
                    label = str(value) if value is not None else f"{obj.type_name}()"
                    
                    node_data = {
                        'id': obj.id,
                        'label': label[:50] + '...' if len(label) > 50 else label,
                        'type': obj.type_name,
                        'isPrimitive': obj.is_primitive,
                        'nodeType': 'object'
                    }
                    nodes.append({'data': node_data})
                    
                    # Add code version node if available
                    if self.object_manager.code_manager:
                        code_info = self.object_manager.code_manager.get_object_code(obj.id)
                        if code_info and isinstance(code_info, dict):
                            code_version_id = f"code_{code_info['id']}"
                            if code_version_id not in node_ids:
                                node_ids.add(code_version_id)
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
                                
                                edge_data = {
                                    'id': f"edge_code_{obj.id}_{code_version_id}",
                                    'source': obj.id,
                                    'target': code_version_id,
                                    'label': 'implements',
                                    'edgeType': 'code_version'
                                }
                                edges.append({'data': edge_data})
                except Exception as e:
                    logger.error(f"Error creating node data for object {obj.id}: {e}")
                    continue
            
            # Add nodes for function calls
            for call_id in call_ids:
                try:
                    call_info = self.call_tracker.get_call(call_id)
                    start_time = call_info['start_time'].isoformat() if call_info['start_time'] else None
                    end_time = call_info['end_time'].isoformat() if call_info['end_time'] else None
                    
                    node_data = {
                        'id': f"call_{call_id}",
                        'label': f"{call_info['function']}()",
                        'type': 'FunctionCall',
                        'isPrimitive': False,
                        'nodeType': 'function',
                        'file': call_info['file'],
                        'line': call_info['line'],
                        'startTime': start_time,
                        'endTime': end_time
                    }
                    nodes.append({'data': node_data})
                    
                    # Add edges for local variables
                    for var_name, var_ref in call_info['locals'].items():
                        if var_ref is not None:
                            if not isinstance(var_ref, str):
                                try:
                                    var_ref = self.object_manager.store(var_ref)
                                except Exception as e:
                                    logger.warning(f"Could not store local var {var_name}: {e}")
                                    continue
                            
                            if any(node['data']['id'] == var_ref for node in nodes):
                                edge_data = {
                                    'id': f"edge_local_{call_id}_{var_name}",
                                    'source': f"call_{call_id}",
                                    'target': var_ref,
                                    'label': f'local:{var_name}',
                                    'edgeType': 'function_var'
                                }
                                edges.append({'data': edge_data})
                    
                    # Add edges for global variables
                    for var_name, var_ref in call_info['globals'].items():
                        if var_ref is not None:
                            if not isinstance(var_ref, str):
                                try:
                                    var_ref = self.object_manager.store(var_ref)
                                except Exception as e:
                                    logger.warning(f"Could not store global var {var_name}: {e}")
                                    continue
                            
                            if any(node['data']['id'] == var_ref for node in nodes):
                                edge_data = {
                                    'id': f"edge_global_{call_id}_{var_name}",
                                    'source': f"call_{call_id}",
                                    'target': var_ref,
                                    'label': f'global:{var_name}',
                                    'edgeType': 'function_var'
                                }
                                edges.append({'data': edge_data})
                    
                    # Add edge for return value
                    if call_info['return_value'] is not None:
                        return_ref = call_info['return_value']
                        if not isinstance(return_ref, str):
                            try:
                                return_ref = self.object_manager.store(return_ref)
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
                            edges.append({'data': edge_data})
                except Exception as e:
                    logger.error(f"Error processing function call {call_id}: {e}")
            
            return {'nodes': nodes, 'edges': edges}
        except Exception as e:
            logger.error(f"Error generating object graph: {e}")
            raise

async def main(db_path: str):
    """Run the MCP server"""
    logger.info(f"Starting PyMonitor MCP Server with DB path: {db_path}")
    
    try:
        logger.debug("Initializing database connection")
        db = PyMonitorDatabase(db_path)
        logger.debug("Database connection initialized successfully")
        
        logger.debug("Creating MCP server instance")
        server = Server("pymonitor-explorer")
        logger.debug("MCP server instance created")
        
        # Register handlers
        logger.debug("Registering handlers")
        
        @server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available tools"""
            logger.debug("Handling list_tools request")
            tools = [
                types.Tool(
                    name="list_function_calls",
                    description="List all function calls with optional filters",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "search": {"type": "string", "description": "Search term to filter function names"},
                            "file": {"type": "string", "description": "Filter by file path"},
                            "function": {"type": "string", "description": "Filter by exact function name"},
                        },
                    },
                ),
                types.Tool(
                    name="get_function_call",
                    description="Get detailed information about a specific function call",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "call_id": {"type": "string", "description": "ID of the function call to get"},
                        },
                        "required": ["call_id"],
                    },
                ),
                types.Tool(
                    name="get_object_graph",
                    description="Get the object graph data for visualization",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
            ]
            logger.debug(f"Returning {len(tools)} tools")
            return tools
        
        @server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any] | None
        ) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """Handle tool calls"""
            logger.debug(f"Handling tool call: {name} with arguments: {arguments}")
            if not arguments:
                arguments = {}
            
            try:
                if name == "list_function_calls":
                    logger.debug("Executing list_function_calls")
                    calls = db.get_function_calls(
                        search=arguments.get("search", ""),
                        file_filter=arguments.get("file", ""),
                        function_filter=arguments.get("function", "")
                    )
                    logger.debug(f"Found {len(calls)} function calls")
                    return [types.TextContent(type="text", text=str(calls))]
                
                elif name == "get_function_call":
                    logger.debug("Executing get_function_call")
                    if "call_id" not in arguments:
                        raise ValueError("Missing required argument: call_id")
                    
                    call_info = db.get_function_call(arguments["call_id"])
                    if not call_info:
                        raise ValueError(f"Function call not found: {arguments['call_id']}")
                    
                    logger.debug("Successfully retrieved function call info")
                    return [types.TextContent(type="text", text=str(call_info))]
                
                elif name == "get_object_graph":
                    logger.debug("Executing get_object_graph")
                    graph_data = db.get_object_graph()
                    logger.debug(f"Generated graph with {len(graph_data['nodes'])} nodes and {len(graph_data['edges'])} edges")
                    return [types.TextContent(type="text", text=str(graph_data))]
                
                else:
                    raise ValueError(f"Unknown tool: {name}")
            
            except Exception as e:
                logger.error(f"Error handling tool call {name}: {e}", exc_info=True)
                raise
        
        # Run the server with stdio transport
        logger.debug("Setting up stdio transport")
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("Server running with stdio transport")
            try:
                logger.debug("Starting server with initialization options")
                await server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="pymonitor",
                        server_version="0.1.0",
                        capabilities=server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                        ),
                    ),
                )
            except Exception as e:
                logger.error("Error during server run", exc_info=True)
                raise
    
    except Exception as e:
        logger.error("Fatal server error", exc_info=True)
        raise
    finally:
        if hasattr(db, 'session'):
            logger.debug("Closing database session")
            db.session.close()
            logger.debug("Database session closed")

def __main__():
    """Entry point for running as a module"""
    try:
        parser = argparse.ArgumentParser(description="PyMonitor MCP Server")
        parser.add_argument("--db-path", required=True, help="Path to the database file")
        args = parser.parse_args()
        
        logger.info(f"Starting server with database path: {args.db_path}")
        db_path = args.db_path
        import asyncio
        asyncio.run(main(db_path))
    except Exception as e:
        logger.error("Error in main entry point", exc_info=True)
        raise

if __name__ == "__main__":
    __main__() 