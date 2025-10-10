"""
Session management for SpaceTimeMonitor.
This module provides functions for creating and managing monitoring sessions.
"""

from typing import Any, cast

from .monitoring import SpaceTimeMonitor


def start_session(name: str | None = None, description: str | None = None, metadata: dict[str, Any] | None = None) -> int | None:
    """Start a new monitoring session to group function calls.

    Args:
        name: Optional name for the session
        description: Optional description for the session
        metadata: Optional metadata dictionary for additional information

    Returns:
        The session ID of the new session or None if session creation failed
    """
    monitor = SpaceTimeMonitor.get_instance()
    if monitor is None:
        print("ERROR: Monitoring is not initialized. Call init_monitoring() first.")
        return None

    # Get the result and force it to be treated as int for type checking
    result = monitor.start_session(name, description, metadata)
    if result is not None:
        return cast("int", result)
    return None

def end_session() -> int | None:
    """End the current monitoring session and calculate common variables.

    Returns:
        The session ID of the completed session or None if no session was active
    """
    monitor = SpaceTimeMonitor.get_instance()
    if monitor is None:
        print("ERROR: Monitoring is not initialized.")
        return None

    # Get the result and force it to be treated as int for type checking
    result = monitor.end_session()
    if result is not None:
        return cast("int", result)
    return None

def session_context(name: str | None = None, description: str | None = None, metadata: dict[str, Any] | None = None):
    """Context manager for creating a monitoring session.

    Usage:
        with spacetimepy.session_context("My Session"):
            # Call monitored functions
            my_function()

    Args:
        name: Optional name for the session
        description: Optional description for the session
        metadata: Optional metadata dictionary for additional information

    Returns:
        A context manager that starts a session on entry and ends it on exit
    """
    class SessionContext:
        def __enter__(self):
            self.session_id = start_session(name, description, metadata)
            return self.session_id

        def __exit__(self, exc_type, exc_val, exc_tb):
            end_session()
            # Don't suppress exceptions
            return False

    return SessionContext()
