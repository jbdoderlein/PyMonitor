#!/usr/bin/env python3
"""
Runner module for the PyMonitor Reexecutionner.

Handles the main process of connecting to a database and executing commands.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from ...core import (
    FunctionCall,
    MonitoringSession,
    init_db,
    init_monitoring,
    reanimate_function,
    replay_session_from,
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

        # Map of command name to handler function
        self.command_handlers: dict[str, Callable] = {
            "reanimate": self.handle_reanimate,
            "replay": self.handle_replay,
            "status": self.handle_status,
            "list_functions": self.handle_list_functions,
            "list_calls": self.handle_list_calls,
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

    async def process_command(self, command: dict[str, Any]) -> dict[str, Any]:
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

    async def handle_reanimate(self, command: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a reanimate command.
        
        Args:
            command: Dict containing the command arguments
            
        Returns:
            Dict containing the command response
        """
        # This is a placeholder implementation - will be expanded in future
        call_id = command.get("call_id")
        if not call_id:
            return {"status": "error", "message": "No call_id specified"}

        ignore_globals = command.get("ignore_globals", [])
        update_db = command.get("update_db", False)

        # Reanimate the function call
        logger.info(f"Reanimating function call {call_id} (update_db={update_db})")

        # Call the reanimate_function with appropriate parameters
        # This would be expanded to properly handle the results
        try:
            result = reanimate_function(
                call_id,
                self.db_path,
                ignore_globals=ignore_globals
            )
            return {"status": "success", "result": str(result)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def handle_replay(self, command: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a replay command.
        
        Args:
            command: Dict containing the command arguments
            
        Returns:
            Dict containing the command response
        """
        # This is a placeholder implementation - will be expanded in future
        call_id = command.get("call_id")
        if not call_id:
            return {"status": "error", "message": "No call_id specified"}

        ignore_globals = command.get("ignore_globals", [])

        # Replay the session from the specified call
        logger.info(f"Replaying session from call {call_id}")

        try:
            new_branch_id = replay_session_from(
                int(call_id),
                self.db_path,
                ignore_globals=ignore_globals
            )
            return {"status": "success", "new_branch_id": new_branch_id}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def handle_status(self, command: dict[str, Any]) -> dict[str, Any]:
        """Return the current status of the runner."""
        return {
            "status": "success",
            "db_path": self.db_path,
            "background_mode": self.background_mode,
            "running": self.running
        }

    async def handle_list_functions(self, command: dict[str, Any]) -> dict[str, Any]:
        """List all functions in the database."""
        session_info = self.db_session.query(MonitoringSession).first()
        if not session_info:
            return {"status": "error", "message": "No monitoring session found"}

        functions = {}
        if hasattr(session_info, 'function_calls_map') and session_info.function_calls_map:
            for func_name, call_ids in session_info.function_calls_map.items():
                # Convert to list of integers if needed
                if hasattr(call_ids, '__iter__') and not isinstance(call_ids, str):
                    functions[func_name] = [int(x) for x in call_ids]
                else:
                    functions[func_name] = [int(call_ids)]

        return {"status": "success", "functions": functions}

    async def handle_list_calls(self, command: dict[str, Any]) -> dict[str, Any]:
        """List all calls for a specific function."""
        function_name = command.get("function")
        if not function_name:
            return {"status": "error", "message": "No function name specified"}

        session_info = self.db_session.query(MonitoringSession).first()
        if not session_info or not hasattr(session_info, 'function_calls_map'):
            return {"status": "error", "message": "No monitoring session found"}

        if function_name not in session_info.function_calls_map:
            return {"status": "error", "message": f"Function {function_name} not found"}

        call_ids = session_info.function_calls_map[function_name]
        # Convert to list of integers
        if hasattr(call_ids, '__iter__') and not isinstance(call_ids, str):
            calls = [int(str(x)) for x in call_ids]  # Convert to string first to handle Column[int]
        else:
            calls = [int(str(call_ids))]  # Convert to string first to handle Column[int]

        # Get call details for each ID
        call_details = []
        for call_id in calls:
            call = self.db_session.get(FunctionCall, call_id)
            if call:
                call_details.append({
                    "id": call_id,
                    "function": call.function,
                    "file": str(call.file) if hasattr(call, 'file') else None,
                    "line": int(call.line) if hasattr(call, 'line') else None
                })

        return {"status": "success", "calls": call_details}

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
