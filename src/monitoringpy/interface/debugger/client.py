#!/usr/bin/env python3
"""
Client module for the PyMonitor Reexecutionner.

Provides a client class to communicate with the reexecutionner server.
"""

import json
import logging
import socket
import sys
from typing import Any

logger = logging.getLogger(__name__)

class ReexecutionnerClient:
    """
    Client for communicating with the PyMonitor Reexecutionner.
    
    Provides methods for sending commands to the reexecutionner server
    and receiving responses.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        Initialize the client.
        
        Args:
            host: Host where the reexecutionner server is running
            port: Port where the reexecutionner server is listening
        """
        self.host = host
        self.port = port
        self.socket = None

    def connect(self) -> bool:
        """
        Connect to the reexecutionner server.
        
        Returns:
            True if connection was successful, False otherwise
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            logger.info(f"Connected to reexecutionner at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to reexecutionner: {e}")
            self.socket = None
            return False

    def disconnect(self) -> None:
        """Disconnect from the reexecutionner server."""
        if self.socket:
            self.socket.close()
            self.socket = None
            logger.info("Disconnected from reexecutionner")

    def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """
        Send a command to the reexecutionner server.
        
        Args:
            command: Dict containing the command and arguments
            
        Returns:
            Dict containing the server response
            
        Raises:
            ConnectionError: If not connected to server or error occurs
        """
        if not self.socket:
            raise ConnectionError("Not connected to reexecutionner server")

        try:
            # Encode command as JSON and send
            command_json = json.dumps(command).encode() + b'\n'
            self.socket.sendall(command_json)

            # Receive and decode response
            response_data = self.socket.recv(4096)
            if not response_data:
                raise ConnectionError("Connection closed by server")

            response_json = response_data.decode().strip()
            response = json.loads(response_json)
            return response

        except Exception as e:
            logger.error(f"Error sending command: {e}")
            self.disconnect()  # Disconnect on error
            raise ConnectionError(f"Error communicating with server: {e}")

    def get_status(self) -> dict[str, Any]:
        """
        Get the current status of the reexecutionner.
        
        Returns:
            Dict containing the status information
        """
        command = {"command": "status"}
        return self.send_command(command)

    def list_functions(self) -> dict[str, list[int]]:
        """
        List all functions in the database.
        
        Returns:
            Dict mapping function names to lists of call IDs
        """
        command = {"command": "list_functions"}
        response = self.send_command(command)

        if response.get("status") != "success":
            logger.error(f"Error listing functions: {response.get('message', 'Unknown error')}")
            return {}

        return response.get("functions", {})

    def list_calls(self, function_name: str) -> list[dict[str, Any]]:
        """
        List all calls for a specific function.
        
        Args:
            function_name: Name of the function to list calls for
            
        Returns:
            List of call details for the function
        """
        command = {
            "command": "list_calls",
            "function": function_name
        }
        response = self.send_command(command)

        if response.get("status") != "success":
            logger.error(f"Error listing calls: {response.get('message', 'Unknown error')}")
            return []

        return response.get("calls", [])

    def reanimate(self, call_id: str | int, ignore_globals: list[str] | None = None,
                update_db: bool = False) -> dict[str, Any]:
        """
        Reanimate a function call.
        
        Args:
            call_id: ID of the function call to reanimate
            ignore_globals: List of global variables to ignore
            update_db: Whether to update the database with new call data
            
        Returns:
            Dict containing the result of the reanimation
        """
        command = {
            "command": "reanimate",
            "call_id": str(call_id),
            "ignore_globals": ignore_globals if ignore_globals is not None else [],
            "update_db": update_db
        }
        return self.send_command(command)

    def replay(self, call_id: str | int, ignore_globals: list[str] | None = None) -> dict[str, Any]:
        """
        Replay a session from a function call.
        
        Args:
            call_id: ID of the function call to replay from
            ignore_globals: List of global variables to ignore
            
        Returns:
            Dict containing the result of the replay
        """
        command = {
            "command": "replay",
            "call_id": str(call_id),
            "ignore_globals": ignore_globals if ignore_globals is not None else []
        }
        return self.send_command(command)


def main():
    """Command-line interface for the reexecutionner client."""
    import argparse

    parser = argparse.ArgumentParser(description="PyMonitor Reexecutionner Client")
    parser.add_argument("--host", default="localhost", help="Reexecutionner server host")
    parser.add_argument("--port", type=int, default=8765, help="Reexecutionner server port")
    parser.add_argument("command", choices=["status", "list-functions", "list-calls", "reanimate", "replay"],
                      help="Command to execute")
    parser.add_argument("--function", help="Function name for list-calls command")
    parser.add_argument("--call-id", help="Call ID for reanimate and replay commands")
    parser.add_argument("--ignore-globals", nargs="*", help="Global variables to ignore")
    parser.add_argument("--update-db", action="store_true", help="Update DB with new call data (for reanimate)")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    # Create client and connect
    client = ReexecutionnerClient(host=args.host, port=args.port)
    if not client.connect():
        sys.exit(1)

    try:
        # Execute the requested command
        if args.command == "status":
            response = client.get_status()
            print(json.dumps(response, indent=2))

        elif args.command == "list-functions":
            functions = client.list_functions()
            print(json.dumps(functions, indent=2))

        elif args.command == "list-calls":
            if not args.function:
                parser.error("--function is required for list-calls command")
            calls = client.list_calls(args.function)
            print(json.dumps(calls, indent=2))

        elif args.command == "reanimate":
            if not args.call_id:
                parser.error("--call-id is required for reanimate command")
            response = client.reanimate(
                args.call_id,
                ignore_globals=args.ignore_globals,
                update_db=args.update_db
            )
            print(json.dumps(response, indent=2))

        elif args.command == "replay":
            if not args.call_id:
                parser.error("--call-id is required for replay command")
            response = client.replay(
                args.call_id,
                ignore_globals=args.ignore_globals
            )
            print(json.dumps(response, indent=2))

    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
