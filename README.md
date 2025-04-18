# PyMonitor

PyMonitor is a powerful Python monitoring and introspection tool that allows you to track function calls, arguments, return values, and object states during program execution. It provides detailed insights into your code's behavior and performance, making it easier to debug, profile, and understand complex applications.

## Features

- **Function Call Monitoring**: Track all function calls, their arguments, and return values
- **Object Introspection**: Capture detailed information about objects, including their attributes and structure
- **Database Storage**: Store monitoring data in SQLite databases for later analysis
- **Web Explorer**: Browse and analyze monitoring data through a user-friendly web interface
- **Low Overhead**: Designed to minimize performance impact on monitored applications
- **Custom Object Support**: Handles custom classes, nested objects, and complex data structures
- **Automatic Schema Migration**: Seamlessly upgrade database schemas when the library is updated
- **Object Versioning**: Track changes to objects over time with detailed version history
- **Function Reanimation**: Replay previous function executions using stored arguments

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/PyMonitor.git
cd PyMonitor

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

## Quick Start

### Basic Usage

```python
from monitoringpy import init_monitoring, stop_monitoring

# Initialize monitoring
init_monitoring("my_app.db")

# Your code to monitor
def my_function(a, b):
    return a + b

result = my_function(5, 10)
print(f"Result: {result}")

# Stop monitoring
stop_monitoring()
```

### Viewing Results

```bash
# Run the web explorer
python -m monitoringpy.web_explorer my_app.db
```

Then open your browser at http://127.0.0.1:5000 to explore the monitoring data.

## Advanced Usage

### Monitoring with Context Manager

```python
from monitoringpy import MonitoringContext

# Use context manager for monitoring a specific block of code
with MonitoringContext("my_app.db"):
    # Code to monitor
    result = complex_calculation(data)
```

### Custom Object Handling

PyMonitor can handle custom objects and their attributes:

```python
from monitoringpy import init_monitoring, stop_monitoring

class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        
    def distance(self, other):
        return ((self.x - other.x)**2 + (self.y - other.y)**2)**0.5

# Initialize monitoring
init_monitoring("custom_objects.db")

# Create and use custom objects
p1 = Point(3, 4)
p2 = Point(6, 8)
distance = p1.distance(p2)
print(f"Distance: {distance}")

# Stop monitoring
stop_monitoring()
```

### Performance Monitoring with PyRAPL

If you have PyRAPL installed, PyMonitor can track energy consumption:

```python
from monitoringpy import init_monitoring, stop_monitoring

# Initialize monitoring with PyRAPL enabled
init_monitoring("performance.db", enable_pyrapl=True)

# Your code to monitor
result = compute_intensive_function()

# Stop monitoring
stop_monitoring()
```

## Function Reanimation

PyMonitor allows you to replay previous function executions using the stored arguments:

```python
import monitoringpy

# Load the arguments from a previous function execution
args, kwargs = monitoringpy.load_execution_data("123", "monitoring.db")

# Import the function manually
from your_module import your_function

# Execute the function with the same arguments
result = your_function(*args, **kwargs)
print(f"Result: {result}")

# Or use the shorthand method that handles everything
result = monitoringpy.reanimate_function("123", "monitoring.db")
print(f"Result: {result}")
```

For detailed documentation on the reanimation features, see [docs/reanimation.md](docs/reanimation.md).

## Web Explorer

The web explorer provides a user-friendly interface to browse and analyze monitoring data:

- View all function calls with timestamps and durations
- Explore function arguments and return values
- Examine object structures and attributes
- Filter and search for specific functions or objects
- Analyze performance metrics (if PyRAPL is enabled)
- View object version history and compare changes between versions

To run the web explorer:

```bash
python -m monitoringpy.web_explorer your_database.db
```

For more details, see [WEB_EXPLORER.md](WEB_EXPLORER.md).

## Database Schema Migration

PyMonitor automatically handles database schema migrations when the library is updated. If you encounter issues with older databases, you can manually migrate them:

```python
from monitoringpy.migrate_db import migrate_database

# Migrate an older database to the current schema
migrate_database("old_database.db")
```

## Examples

Check out the `examples/` directory for more usage examples:

- `basic.py`: Simple function monitoring
- `custom_objects.py`: Monitoring with custom objects
- `performance.py`: Performance monitoring with PyRAPL

## Testing

PyMonitor includes a comprehensive test suite to ensure reliability and correctness:

```bash
# Run all tests
python tests/run_tests.py

# Or use the standard unittest module
python -m unittest discover tests
```

The tests cover:

- Object hashing and identity management
- Object storage and retrieval
- Object versioning and version history
- Function call data with versioned objects
- Complex object structures and custom classes

For more details on the test suite, see [tests/README.md](tests/README.md).

## Troubleshooting

### Common Issues

1. **Database Errors**: If you encounter database errors, try migrating the database:
   ```python
   from monitoringpy.migrate_db import migrate_database
   migrate_database("your_database.db")
   ```

2. **Module Not Found Errors**: Ensure your Python path includes the project directory:
   ```bash
   export PYTHONPATH=$PYTHONPATH:/path/to/PyMonitor
   ```

3. **Performance Issues**: If monitoring causes significant slowdowns, consider:
   - Reducing the monitoring depth (default is 3)
   - Disabling PyRAPL if it's enabled
   - Monitoring only specific functions instead of all functions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Add tests for your changes
4. Ensure all tests pass (`python tests/run_tests.py`)
5. Commit your changes (`git commit -m 'Add some amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 