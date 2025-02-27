# MonitoringPy

A Python package for monitoring function calls and generating execution graphs. This package uses Python's sys.monitoring API to track function calls and their relationships, making it easy to visualize program flow.

## Requirements

- Python 3.10 or higher
- Graphviz (for graph generation)

## Installation

From PyPI (not yet published):
```bash
pip install monitoringpy
```

From source:
```bash
pip install .
```

For development:
```bash
pip install -e .
```

## Usage

1. Create a `monitor_config.json` file in your project directory:

```json
{
    "tool_id": 1,
    "tool_name": "monitoringpy",
    "monitor": {
        "your_file.py": ["function_to_monitor"]
    },
    "output": {
        "file": "data.jsonl"
    }
}
```

2. Import and initialize monitoring in your code:

```python
from monitoringpy import init_monitoring

# Basic initialization (looks for monitor_config.json in the same directory)
init_monitoring()

# Custom config file path (relative to the current file)
init_monitoring('configs/monitor_config.json')

# Override output file location
init_monitoring(output_file='custom/path/trace.jsonl')

# Your code here - functions will be monitored according to monitor_config.json
def my_function():
    pass
```

Note: All paths (config file and output file) are resolved relative to the location of the Python file that calls `init_monitoring()`.

3. Generate execution graph using either:

   a. Python API:
   ```python
   from monitoringpy.generate_graph import generate_dot_graph
   generate_dot_graph("data.jsonl", "execution_graph.dot")
   ```

   b. Command-line interface:
   ```bash
   # Generate DOT file
   monitoringpy-graph data.jsonl

   # Generate DOT file with custom output name
   monitoringpy-graph data.jsonl -o custom_graph.dot

   # Generate both DOT and PNG files
   monitoringpy-graph data.jsonl --png
   ```

## Features

- Function call monitoring
- Argument and return value tracking
- Execution graph generation
- Support for multi-threaded applications
- Global variable tracking
- Command-line interface for graph generation
- Explicit monitoring initialization
- Configurable output paths
- Relative path resolution

## License

MIT License 