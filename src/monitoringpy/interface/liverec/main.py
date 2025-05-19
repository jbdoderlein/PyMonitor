#!/usr/bin/env python3
"""
LiveRunner module for the PyMonitor Reexecutionner.

Handles the main process of connecting to a database and executing commands.
"""

import logging
import asyncio
import json
import os
import importlib.util
import sys
from typing import Dict, Any, Callable

from ...core import (
    init_db,
    init_monitoring, 
    ObjectManager,
    FunctionCallTracker,
    replay_session_from,
    FunctionCall, 
    MonitoringSession,
    pymonitor
)

logger = logging.getLogger(__name__)

class Runner:
    """
    Runner for the PyMonitor Reexecutionner.
    
    Connects to a PyMonitor database and provides an interface for 
    reexecuting stored function calls.
    """
    
    def __init__(self, db_path: str, host: str = "localhost", port: int = 8765, 
                 background_mode: bool = False):
        """
        Initialize the runner.
        
        Args:
            db_path: Path to the monitoring database file
            host: Host to bind the server
            port: Port to listen for commands
            background_mode: Whether to run executions in background mode
        """
        self.db_path = db_path
        self.host = host
        self.port = port
        self.background_mode = background_mode
        self.server = None
        self.running = False
        
        # Initialize database connection
        logger.info(f"Initializing database connection to {db_path}")
        self.db_session = init_db(db_path)()
        
        # Initialize monitoring for new recordings
        self.monitor = init_monitoring(db_path=db_path)

        self.obj_manager = ObjectManager(self.db_session)
        self.call_tracker = FunctionCallTracker(self.db_session)
        
        # Map of command name to handler function
        self.command_handlers: Dict[str, Callable] = {
            "set_example": self.handle_set_example,
            "change": self.handle_change,
            "status": self.handle_status
        }
        
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a client connection."""
        addr = writer.get_extra_info('peername')
        logger.info(f"New connection from {addr}")
        
        while self.running:
            try:
                # Read command from client
                data = await reader.readline()
                if not data:
                    break
                    
                message = data.decode().strip()
                logger.debug(f"Received: {message}")
                
                # Parse JSON command
                try:
                    command = json.loads(message)
                    response = await self.process_command(command)
                except json.JSONDecodeError:
                    response = {"status": "error", "message": "Invalid JSON command"}
                
                # Send response to client
                writer.write(json.dumps(response).encode() + b'\n')
                await writer.drain()
                
            except Exception as e:
                logger.error(f"Error handling client: {e}")
                break
                
        writer.close()
        await writer.wait_closed()
        logger.info(f"Connection from {addr} closed")
        
    async def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a command received from a client.
        
        Args:
            command: Dict containing the command and arguments
            
        Returns:
            Dict containing the command response
        """
        cmd_type = command.get("command")
        if not cmd_type:
            return {"status": "error", "message": "No command specified"}
            
        # Get the appropriate handler for this command
        handler = self.command_handlers.get(cmd_type)
        if not handler:
            return {"status": "error", "message": f"Unknown command: {cmd_type}"}
            
        # Call the handler with the command arguments
        try:
            return await handler(command)
        except Exception as e:
            logger.error(f"Error processing command {cmd_type}: {e}")
            return {"status": "error", "message": str(e)}
        
    async def setup_example(self) -> None:
        """
        Setup the example execution.
        """
        if not self.call_id:
            raise ValueError("No call_id specified")
        
        
        call_info = self.call_tracker.get_call(self.call_id)

        script_path = call_info['file']
        assert script_path is not None
        # Determine module name if not provided

        # Try to get module path from call info first
        code_info = call_info.get('code')
        module_path_from_info = code_info.get('module_path') if code_info else None

        if module_path_from_info:
            basename = os.path.basename(script_path)
            if basename.endswith('.py'):
                module_name = basename[:-3] # Remove .py extension
            else:
                module_name = basename # Use basename as is if no .py extension
        
        # Ensure module_name is a valid string
        if not module_name:
             raise ValueError(f"Could not determine a valid module name for script {script_path}")

        # Add script directory to path if necessary to allow relative imports within the script
        script_dir = os.path.dirname(script_path)
        if script_dir and script_dir not in sys.path:
             sys.path.insert(0, script_dir)

        # Create spec and module
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load script from {script_path}")
            
        module = importlib.util.module_from_spec(spec)
        # Add the module to sys.modules to handle imports correctly
        sys.modules[module_name] = module

        self.module = module
        self.module_name = module_name
        self.module_file = script_path

        # Execute the module with loaded globals
        spec.loader.exec_module(module)

        # Rehydrate the locals dictionary
        globals_dict = self.obj_manager.rehydrate_dict(call_info['globals'])
        
        filtered_globals = {k: v for k, v in globals_dict.items() if not (k.startswith('__') and k.endswith('__'))}
        module.__dict__.update(filtered_globals)
        
    async def execute_example(self) -> Dict[str, Any]:
        """
        Execute the example.
        """
        assert self.call_id is not None
        call_info = self.call_tracker.get_call(self.call_id)
        
        try:
            # reload the module
            self.module = importlib.reload(self.module)
        except Exception as e:
            print(e)
            return {"status": "error", "message": str(e)}

        # Get the function to execute
        function_name = call_info['function']
        function = getattr(self.module, function_name)

        # Rehydrate the locals dictionary
        locals_dict = self.obj_manager.rehydrate_dict(call_info['locals'])
        try:
            print("Inside execute_example", locals_dict)
            result = pymonitor("line")(function)(**locals_dict)
        except Exception as e:
            print("Inside execute_example", e)
            return {"status": "error", "message": str(e)}

        # get the stackrecording from last call
        new_call_id = self.call_tracker.get_call_history(function_name)[-1]
        stackrecording = self.call_tracker.get_function_traces(new_call_id)
        print(stackrecording)
        return {"status": "success", "result": result, "stackrecording": stackrecording}
    
    async def handle_set_example(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a set_example command.
        
        Args:
            command: Dict containing the command arguments
            
        Returns:
            Dict containing the command response
        """
        self.module_file = command.get("module_file")
        self.module_name = command.get("module_name")
        self.call_id = command.get("call_id")

        await self.setup_example()
        return await self.execute_example()
            
    async def handle_change(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a change command.
        
        Args:
            command: Dict containing the command arguments
            
        Returns:
            Dict containing the command response
        """
        return await self.execute_example()

    async def handle_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Return the current status of the runner."""
        return {
            "status": "success",
            "db_path": self.db_path,
            "background_mode": self.background_mode,
            "running": self.running
        }
        
    async def start_server(self):
        """Start the command server."""
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        
        addr = self.server.sockets[0].getsockname()
        logger.info(f'Serving on {addr}')
        
        async with self.server:
            await self.server.serve_forever()
            
    def start(self):
        """Start the runner."""
        logger.info(f"Starting reexecutionner on {self.host}:{self.port}")
        self.running = True
        
        # Run the server in the event loop
        try:
            asyncio.run(self.start_server())
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            
    def stop(self):
        """Stop the runner."""
        logger.info("Stopping reexecutionner")
        self.running = False
        
        if self.server:
            self.server.close()
            
        # Clean up database connections
        if self.db_session:
            self.db_session.close() 

if __name__ == "__main__":
    # Take args (=db_path)
    db_path = sys.argv[1]
    db_path = os.path.abspath(db_path)
    runner = Runner(db_path)
    runner.start()