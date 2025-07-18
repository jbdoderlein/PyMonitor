"""
Interface implementations for PyMonitor.
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

# Use __getattr__ to make imports work transparently
def __getattr__(name):
    if name == 'WebExplorer':
        return _lazy_import_web_explorer()
    if name == 'run_api':
        return _lazy_import_run_api()
    if name == 'initialize_db':
        return _lazy_import_initialize_db()
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
        >>> from monitoringpy.interface import start_web_explorer
        >>> start_web_explorer('my_session.db')
    """
    WebExplorer = _lazy_import_web_explorer()
    explorer = WebExplorer(db_file)
    explorer.run(host=host, port=port, debug=debug)

__all__ = [
    'WebExplorer',
    'run_api',
    'initialize_db',
    'start_web_explorer',
]
