"""
Core functionality for PyMonitor.
This module contains the core implementation of the monitoring system.
"""

from .code_manager import CodeManager
from .function_call import FunctionCallRepository
from .models import (
    CodeDefinition,
    CodeObjectLink,
    FunctionCall,
    MonitoringSession,
    ObjectIdentity,
    StackSnapshot,
    StoredObject,
    export_db,
    init_db,
)
from .monitoring import PyMonitoring, init_monitoring, pymonitor
from .reanimation import (
    load_execution_data,
    load_snapshot,
    load_snapshot_in_frame,
    reanimate_function,
    replay_session_from,
    run_with_state,
)
from .representation import ObjectManager
from .session import end_session, session_context, start_session
from .trace import TraceExporter


# Recording control helper functions
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

def recording_context(enabled=False):
    """Context manager for controlling PyMonitor recording.

    Usage:
        # Disable recording for a block of code
        with spacetimepy.recording_context(enabled=False):
            # Code runs without being monitored
            expensive_function()

        # Only monitor a specific section
        spacetimepy.disable_recording()
        # Setup code runs without monitoring
        with spacetimepy.recording_context(enabled=True):
            # This section will be monitored
            important_function()
        # Back to not monitoring

    Args:
        enabled: Whether recording should be enabled within the context
                (True = enable, False = disable)

    Returns:
        A context manager that controls recording state
    """
    class RecordingContext:
        def __init__(self, enabled):
            self.enabled = enabled
            self.previous_state = None

        def __enter__(self):
            monitor = PyMonitoring.get_instance()
            if monitor is not None:
                self.previous_state = monitor.is_recording_enabled
                if self.enabled:
                    monitor.enable_recording()
                else:
                    monitor.disable_recording()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            monitor = PyMonitoring.get_instance()
            if monitor is not None and self.previous_state is not None:
                if self.previous_state:
                    monitor.enable_recording()
                else:
                    monitor.disable_recording()
            # Don't suppress exceptions
            return False

    return RecordingContext(enabled)

__all__ = [
    # Database initialization
    'init_db',
    'export_db',
    #decorators
    'pymonitor',
    'init_monitoring',
    # Core classes
    'PyMonitoring',
    'FunctionCallRepository',
    'CodeManager',
    'ObjectManager',
    'TraceExporter',
    # Models
    'StoredObject',
    'ObjectIdentity',
    'StackSnapshot',
    'FunctionCall',
    'CodeDefinition',
    'CodeObjectLink',
    'MonitoringSession',
    # Session management
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
    'load_snapshot',
    'load_snapshot_in_frame',
    'run_with_state',
    'replay_session_from',
]
