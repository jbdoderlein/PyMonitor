"""
PyMonitor - A Python execution monitoring and analysis tool.
"""

import functools
import traceback
from typing import Any, Optional, Callable, Tuple, Dict, List, Union

from .core import (
    init_db,
    init_monitoring,
    pymonitor,
    PyMonitoring,
    FunctionCallTracker,
    CodeManager,
    ObjectManager,
    StoredObject,
    ObjectIdentity,
    StackSnapshot,
    FunctionCall,
    CodeDefinition,
    CodeObjectLink,
    MonitoringSession,
    delete_function_execution,
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

from .core.monitoring import pymonitor

from .interface import (
    WebExplorer,
    MCPServer,
)

# Don't import pygame by default - let users import it explicitly when needed
# from . import pygame

__version__ = '0.1.0'


__all__ = [
    # Core functionality
    'init_db',
    'PyMonitoring',
    'FunctionCallTracker',
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
    'MCPServer',
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
    'delete_function_execution',
    'load_snapshot',
    'load_snapshot_in_frame',
    'replay_session_from',
    # Wrapped modules
    'pygame',
]

# Helper functions to access PyMonitoring instance methods
def disable_recording():
    """Temporarily disable recording of function calls and line execution."""
    monitor = PyMonitoring.get_instance()
    if monitor is not None:
        monitor.disable_recording()
    else:
        print("ERROR: Monitoring is not initialized. Call init_monitoring() first.")

def enable_recording():
    """Re-enable recording of function calls and line execution."""
    monitor = PyMonitoring.get_instance()
    if monitor is not None:
        monitor.enable_recording()
    else:
        print("ERROR: Monitoring is not initialized. Call init_monitoring() first.")

