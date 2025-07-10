"""
PyMonitor - A Python execution monitoring and analysis tool.
"""

from .core import (
    init_db,
    init_monitoring,
    pymonitor,
    PyMonitoring,
    FunctionCallRepository,
    CodeManager,
    ObjectManager,
    StoredObject,
    ObjectIdentity,
    StackSnapshot,
    FunctionCall,
    CodeDefinition,
    CodeObjectLink,
    MonitoringSession,
    load_execution_data,
    reanimate_function,
    load_snapshot,
    load_snapshot_in_frame,
    start_session,
    end_session,
    session_context,
    run_with_state,
    replay_session_from,
    disable_recording,
    enable_recording,
    recording_context,
)

# NOTE: WebExplorer is not imported by default to avoid loading heavy web dependencies
# To use the web interface, import it explicitly:
# from monitoringpy.interface import WebExplorer
# 
# Or use the convenience function:
# from monitoringpy.interface import start_web_explorer
# start_web_explorer('my_session.db')

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
    # Wrapped modules - pygame is available but not imported by default
    # 'pygame',  # Use: from monitoringpy import pygame (when needed)
    
    # Web interface - import explicitly when needed
    # 'WebExplorer',  # Use: from monitoringpy.interface import WebExplorer
    # 'start_web_explorer',  # Use: from monitoringpy.interface import start_web_explorer
]


