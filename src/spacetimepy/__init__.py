"""
SpaceTimePy - A Python execution monitoring and analysis tool.
"""

from .core import (
    CodeDefinition,
    CodeManager,
    CodeObjectLink,
    FunctionCall,
    FunctionCallRepository,
    MonitoringSession,
    ObjectIdentity,
    ObjectManager,
    PyMonitoring,
    StackSnapshot,
    StoredObject,
    disable_recording,
    enable_recording,
    end_session,
    function,
    init_db,
    init_monitoring,
    line,
    load_execution_data,
    load_snapshot,
    load_snapshot_in_frame,
    pymonitor,
    reanimate_function,
    recording_context,
    replay_session_from,
    run_with_state,
    session_context,
    start_session,
)

# NOTE: WebExplorer is not imported by default to avoid loading heavy web dependencies
# To use the web interface, import it explicitly:
# from spacetimepy.interface import WebExplorer
#
# Or use the convenience function:
# from spacetimepy.interface import start_web_explorer
# start_web_explorer('my_session.db')
#
# To start the API from an existing monitor instance:
# import spacetimepy
# monitor = spacetimepy.init_monitoring()
# spacetimepy.start_api(monitor, 3456)

# Import start_api convenience function
def _lazy_import_start_api():
    """Lazy import start_api to avoid loading web dependencies."""
    from .interface import start_api
    return start_api

def _lazy_import_refresh_api_database():
    """Lazy import refresh_api_database to avoid loading web dependencies."""
    from .interface import refresh_api_database
    return refresh_api_database

def __getattr__(name):
    if name == 'start_api':
        return _lazy_import_start_api()
    if name == 'refresh_api_database':
        return _lazy_import_refresh_api_database()
    raise AttributeError(f"module {__name__} has no attribute {name}")

__version__ = '0.1.0'


__all__ = [
    # Core functionality
    'init_db',
    'PyMonitoring',
    'FunctionCallRepository',
    'CodeManager',
    'ObjectManager',
    #decorators
    'pymonitor',
    'function',
    'line',
    'init_monitoring',
    # Models
    'StoredObject',
    'ObjectIdentity',
    'StackSnapshot',
    'FunctionCall',
    'CodeDefinition',
    'CodeObjectLink',
    'MonitoringSession',
    # Monitoring
    'init_monitoring',
    'pymonitor',
    # Session Management
    'start_session',
    'end_session',
    'session_context',
    # Recording control
    'disable_recording',
    'enable_recording',
    'recording_context',
    # Reanimation
    'load_execution_data',
    'reanimate_function',
    'run_with_state',
    'load_snapshot',
    'load_snapshot_in_frame',
    'replay_session_from',
    # API functionality
    'start_api',
    'refresh_api_database',
    # Wrapped modules - pygame is available but not imported by default
    # 'pygame',  # Use: from spacetimepy import pygame (when needed)

    # Web interface - import explicitly when needed
    # 'WebExplorer',  # Use: from spacetimepy.interface import WebExplorer
    # 'start_web_explorer',  # Use: from spacetimepy.interface import start_web_explorer
]


