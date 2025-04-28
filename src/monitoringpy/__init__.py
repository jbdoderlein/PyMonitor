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
    pymonitor_line,
    PyMonitoring,
    FunctionCallTracker,
    CodeManager,
    ObjectManager,
    StoredObject,
    ObjectVersion,
    ObjectIdentity,
    StackSnapshot,
    FunctionCall,
    CodeDefinition,
    CodeVersion,
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
    'pymonitor_line',
    'pymonitor',
    'init_monitoring',
    # Models
    'StoredObject',
    'ObjectVersion',
    'ObjectIdentity',
    'StackSnapshot',
    'FunctionCall',
    'CodeDefinition',
    'CodeVersion',
    'CodeObjectLink',
    'MonitoringSession',
    # Interfaces
    'WebExplorer',
    'MCPServer',
    # Monitoring
    'init_monitoring',
    'pymonitor_line',
    'pymonitor',
    # Session Management
    'start_session',
    'end_session',
    'session_context',
    # Reanimation 
    'load_execution_data',
    'reanimate_function',
    'delete_function_execution',
    'load_snapshot',
    'load_snapshot_in_frame',
    # Wrapped modules
    'pygame',
]

