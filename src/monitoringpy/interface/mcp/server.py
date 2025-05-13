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

from monitoringpy.core import (
    init_db, StoredObject, FunctionCall, StackSnapshot, 
    CodeDefinition, FunctionCallTracker, ObjectManager
)

# Get the logger but don't configure it yet
logger = logging.getLogger(__name__)

class MCPServer:
    """MCP Server for PyMonitor"""
    
    def __init__(self, db_path: str):
        """Initialize the MCP server.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = str(Path(db_path).expanduser())
        self.setup_logging()
        
        # Initialize database and components
        Session = init_db(self.db_path)
        self.session = Session()
        self.object_manager = ObjectManager(self.session)
        self.call_tracker = FunctionCallTracker(self.session)
        self.server = None

    def setup_logging(self):
        """Set up logging configuration"""
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

        # Add the handlers to the logger
        logger.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        logger.info(f"Starting MCP server with log file: {log_file}")

    async def start(self):
        """Start the MCP server"""
        self.server = Server(
            name="PyMonitor MCP Server",
            version="1.0.0",
            initialization_options=InitializationOptions(
                notification_options=NotificationOptions(
                    should_notify_on_initialization=True
                )
            )
        )

        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available tools"""
            return [
                types.Tool(
                    name="list_function_calls",
                    description="List all function calls with optional filters",
                    parameters=[
                        types.Parameter(
                            name="search",
                            description="Search term to filter function names",
                            type="string",
                            required=False
                        ),
                        types.Parameter(
                            name="file",
                            description="Filter by file path",
                            type="string",
                            required=False
                        ),
                        types.Parameter(
                            name="function",
                            description="Filter by exact function name",
                            type="string",
                            required=False
                        )
                    ]
                ),
                types.Tool(
                    name="get_function_call",
                    description="Get detailed information about a specific function call",
                    parameters=[
                        types.Parameter(
                            name="call_id",
                            description="ID of the function call to get",
                            type="string",
                            required=True
                        )
                    ]
                ),
                types.Tool(
                    name="get_object_graph",
                    description="Get the object graph data for visualization",
                    parameters=[
                        types.Parameter(
                            name="random_string",
                            description="Dummy parameter for no-parameter tools",
                            type="string",
                            required=True
                        )
                    ]
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any] | None
        ) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """Handle tool calls"""
            try:
                if name == "list_function_calls":
                    search = arguments.get("search", "") if arguments else ""
                    file_filter = arguments.get("file", "") if arguments else ""
                    function_filter = arguments.get("function", "") if arguments else ""
                    
                    calls = self.get_function_calls(search, file_filter, function_filter)
                    return [types.TextContent(text=str(calls))]
                
                elif name == "get_function_call":
                    if not arguments or "call_id" not in arguments:
                        raise ValueError("call_id is required")
                    
                    call_info = self.get_function_call(arguments["call_id"])
                    if call_info is None:
                        return [types.TextContent(text="Function call not found")]
                    return [types.TextContent(text=str(call_info))]
                
                elif name == "get_object_graph":
                    graph = self.get_object_graph()
                    return [types.TextContent(text=str(graph))]
                
                else:
                    return [types.TextContent(text=f"Unknown tool: {name}")]
            
            except Exception as e:
                logger.error(f"Error handling tool call: {e}")
                return [types.TextContent(text=f"Error: {str(e)}")]

        try:
            await self.server.start()
        finally:
            if self.session:
                self.session.close()

    def close(self):
        """Close the database session"""
        if self.session:
            self.session.close()
            self.session = None

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
            
            # Get stack recording if available
            call = self.session.query(FunctionCall).filter_by(id=int(call_id)).first()
            if call and call.first_snapshot_id:
                stack_snapshots = []
                current_snapshot = self.session.query(StackSnapshot).filter_by(id=call.first_snapshot_id).first()
                
                while current_snapshot:
                    snapshot_data = {
                        'id': current_snapshot.id,
                        'line_number': current_snapshot.line_number,
                        'locals_refs': current_snapshot.locals_refs,
                        'globals_refs': current_snapshot.globals_refs,
                        'timestamp': current_snapshot.timestamp.isoformat() if current_snapshot.timestamp else None,
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
                
                call_dict['stack_recording'] = stack_snapshots
            
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
            edge_ids = set()
            
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
                            # 2. Code Definition Node (if exists)
                            if code_info.get('id'):
                                # Use code definition ID directly
                                code_def_id = code_info['id']
                                if code_def_id not in node_ids:
                                    node_ids.add(code_def_id)
                                    nodes.append({
                                        'data': {
                                            'id': code_def_id,
                                            'label': code_info.get('name', 'Code'),
                                            'type': 'code',
                                            'details': code_info.get('code_content', '')
                                        }
                                    })
                                    # Edge from object node to code node
                                    edge_id_code = f"edge_code_{obj.id}_{code_def_id}"
                                    if edge_id_code not in edge_ids:
                                        edge_ids.add(edge_id_code)
                                        edges.append({
                                            'data': {
                                                'id': edge_id_code,
                                                'source': obj.id,
                                                'target': code_def_id,
                                                'label': 'defined_by'
                                            }
                                        })
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
    server = MCPServer(db_path)
    try:
        await server.start()
    finally:
        server.close()

def __main__():
    """Entry point for running as a module"""
    parser = argparse.ArgumentParser(description="PyMonitor MCP Server")
    parser.add_argument("db_path", help="Path to the database file to explore")
    args = parser.parse_args()
    
    import asyncio
    asyncio.run(main(args.db_path))

if __name__ == "__main__":
    __main__() 