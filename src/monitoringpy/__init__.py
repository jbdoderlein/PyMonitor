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

from .interface import (
    WebExplorer,
)

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
    # Interfaces
    'WebExplorer',
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
]


