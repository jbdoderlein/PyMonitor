"""
Interface implementations for SpaceTimePy.
This module contains web, MCP server, and STE implementations.
"""

# Lazy imports to avoid loading heavy web dependencies unless needed
def _lazy_import_web_explorer():
    """Lazy import WebExplorer to avoid loading Flask/FastAPI dependencies."""
    from .web.ui import WebUIExplorer as WebExplorer
    return WebExplorer

def _lazy_import_run_api():
    """Lazy import run_api to avoid loading FastAPI dependencies."""
    from .web.api import run_api
    return run_api

def _lazy_import_initialize_db():
    """Lazy import initialize_db to avoid loading FastAPI dependencies."""
    from .web.api import initialize_db
    return initialize_db

def _lazy_import_start_api_from_monitor():
    """Lazy import start_api_from_monitor to avoid loading FastAPI dependencies."""
    from .web.api import start_api_from_monitor
    return start_api_from_monitor

def _lazy_import_refresh_database():
    """Lazy import refresh_database to avoid loading FastAPI dependencies."""
    from .web.api import refresh_database
    return refresh_database

# Use __getattr__ to make imports work transparently
def __getattr__(name):
    if name == 'WebExplorer':
        return _lazy_import_web_explorer()
    if name == 'run_api':
        return _lazy_import_run_api()
    if name == 'initialize_db':
        return _lazy_import_initialize_db()
    if name == 'start_api_from_monitor':
        return _lazy_import_start_api_from_monitor()
    if name == 'refresh_database':
        return _lazy_import_refresh_database()
    raise AttributeError(f"module {__name__} has no attribute {name}")

# Convenience function for quick web interface access
def start_web_explorer(db_file: str, host: str = '127.0.0.1', port: int = 5000, debug: bool = False):
    """Convenience function to quickly start the web explorer.

    Args:
        db_file: Path to the SQLite database file
        host: Host to run the server on (default: 127.0.0.1)
        port: Port to run the server on (default: 5000)
        debug: Whether to run in debug mode (default: False)

    Example:
        >>> from spacetimepy.interface import start_web_explorer
        >>> start_web_explorer('my_session.db')
    """
    WebExplorer = _lazy_import_web_explorer()
    explorer = WebExplorer(db_file)
    explorer.run(host=host, port=port, debug=debug)

# Convenience function for starting API from monitor instance  
def start_api(monitor, port: int):
    """Convenience function to start the API server from a monitor instance.

    This provides the exact interface requested by the user:
    monitor = spacetimepy.init_monitoring(...)
    spacetimepy.start_api(monitor, 3456)

    Args:
        monitor: SpaceTimeMonitor instance (as returned by init_monitoring)
        port: Port number to run the API server on

    Returns:
        threading.Thread: The thread running the API server

    Example:
        >>> import spacetimepy
        >>> monitor = spacetimepy.init_monitoring()
        >>> api_thread = spacetimepy.start_api(monitor, 3456)
        >>> # API server is now running in background on port 3456
    """
    start_api_from_monitor_func = _lazy_import_start_api_from_monitor()
    return start_api_from_monitor_func(monitor, port=port)

# Convenience function for refreshing API database
def refresh_api_database():
    """Convenience function to refresh the API database connection.
    
    This is useful when the database file has been updated by another process
    and you want the API to see the new data without restarting the server.
    
    Returns:
        bool: True if refresh was successful, False otherwise
        
    Example:
        >>> from spacetimepy.interface import refresh_api_database
        >>> success = refresh_api_database()
        >>> if success:
        >>>     print("Database refreshed successfully")
    """
    refresh_func = _lazy_import_refresh_database()
    return refresh_func()

__all__ = [
    'WebExplorer',
    'run_api',
    'initialize_db',
    'start_api_from_monitor',
    'start_api',
    'start_web_explorer',
    'refresh_database',
    'refresh_api_database',
]
