# PyMonitor Web Explorer

PyMonitor now includes a web-based database explorer that allows you to easily view and analyze your monitoring data through a user-friendly web interface.

## Features

- View all function calls in your monitoring database
- Filter function calls by file, function name, or search term
- View detailed information about each function call:
  - Local variables
  - Global variables
  - Return values
  - Performance metrics (if PyRAPL was enabled)
- Interactive UI with sorting and filtering capabilities

## Installation

The web explorer requires Flask and Flask-CORS. Install them with:

```bash
pip install flask flask-cors
```

## Usage

### Option 1: From the Command Line

You can run the web explorer directly from the command line:

```bash
python -m monitoringpy.web_explorer path/to/your/monitoring.db
```

Additional options:
- `--host`: Host to run the server on (default: 127.0.0.1)
- `--port`: Port to run the server on (default: 5000)
- `--no-browser`: Don't open the browser automatically
- `--debug`: Run in debug mode

Example:
```bash
python -m monitoringpy.web_explorer monitoring.db --port 8080
```

### Option 2: From Python

You can also run the web explorer from your Python code:

```python
from monitoringpy import run_explorer

# Run the explorer with default settings
run_explorer("path/to/your/monitoring.db")

# Or customize the settings
run_explorer(
    db_file="path/to/your/monitoring.db",
    host="0.0.0.0",  # Allow external connections
    port=8080,       # Use a custom port
    debug=True,      # Enable debug mode
    open_browser_flag=False  # Don't open the browser automatically
)
```

## Screenshots

When you run the web explorer, you'll see a web interface that looks like this:

1. **Main View**: Lists all function calls with their file, function name, and timestamp
2. **Detail View**: Shows detailed information about the selected function call
3. **Search and Filter**: Allows you to search for specific function calls
4. **Performance Metrics**: Shows energy consumption metrics if PyRAPL was enabled

## Troubleshooting

If you encounter any issues:

1. Make sure Flask and Flask-CORS are installed
2. Check that your database file exists and is accessible
3. Ensure no other application is using the specified port
4. If you're having trouble with the browser opening automatically, try accessing the URL manually: http://127.0.0.1:5000/

## Security Note

The web explorer is designed for local development and debugging. It does not include authentication or security features, so it should not be exposed to the public internet. 