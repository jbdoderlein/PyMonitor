# PyMonitor

PyMonitor is a Python execution monitoring and analysis tool that helps you understand how your code executes by tracking function calls, variable values, and execution flow.

## Features

- **Function Execution Monitoring**: Track function calls, arguments, and return values
- **Line-by-Line Execution**: Record the state of variables at each line of code execution
- **Object Tracking**: Monitor how objects are created and modified during execution
- **Session Management**: Group related function calls into logical sessions
- **Reanimation**: Replay function executions with exact recorded state
- **Recording Control**: Selectively enable or disable monitoring for specific code sections
- **Web Interface**: Visualize and explore execution data through a web-based interface
- **MCP Protocol**: Remote monitoring and analysis

## Installation

```bash
pip install pymonitor
```

## Quick Start

```python
from monitoringpy import init_monitoring, pymonitor, start_session, end_session

# Initialize monitoring
monitor = init_monitoring()

# Start a monitoring session
start_session("Example Session")

# Decorate functions you want to monitor
@pymonitor
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n-1)

# Call your functions
result = factorial(5)
print(f"Result: {result}")

# End the session
end_session()
```

## Recording Control

PyMonitor allows you to selectively enable or disable monitoring during execution, which is useful for:

- Excluding heavy computations from monitoring to reduce overhead
- Focusing monitoring on specific parts of your code
- Creating targeted recording sessions for complex applications

### Ways to Control Recording

```python
from monitoringpy import (
    init_monitoring, pymonitor, 
    disable_recording, enable_recording, recording_context
)

# Initialize monitoring
monitor = init_monitoring()

@pymonitor
def my_function():
    # This part will be monitored
    step1()
    
    # Disable monitoring for expensive operations
    disable_recording()
    expensive_operation()
    enable_recording()
    
    # Use a context manager for cleaner code
    with recording_context(enabled=False):
        another_expensive_operation()
    
    # Back to being monitored
    final_step()
```

See the `examples/recording_control_demo.py` file for a complete example.

## Web Interface

PyMonitor includes a web interface for visualizing execution data:

```python
from monitoringpy import WebExplorer

# After collecting monitoring data
explorer = WebExplorer("monitoring.db")
explorer.start()  # Opens http://localhost:5000 by default
```

## Documentation

For detailed documentation, visit [https://pymonitor.readthedocs.io](https://pymonitor.readthedocs.io)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

PyMonitor is released under the MIT License. See [LICENSE](LICENSE) for details. 