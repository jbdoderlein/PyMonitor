# PyMonitor Reanimator

The PyMonitor Reanimator is a powerful tool that allows you to load, search, and reanimate function calls that have been recorded by the PyMonitor system. This enables you to analyze past executions, debug issues, and even re-execute functions with the exact same arguments.

## Features

- **Load PyMonitor Databases**: Easily load and access monitoring data from SQLite databases.
- **Search Function Calls**: Find function calls based on various criteria such as function name, file path, time range, and performance metrics.
- **Inspect Function Details**: Get detailed information about function calls, including arguments, local variables, and return values.
- **Reanimate Function Calls**: Reconstruct the state of a function call, including all its arguments and local variables.
- **Reconstruct Python Objects**: Convert stored object representations back into actual Python objects, including custom classes.
- **Execute Reanimated Functions**: Re-run functions with the exact same arguments as a previous execution.

## Usage

### Basic Usage

```python
import monitoringpy.reanimator

# Load a PyMonitor database
db = monitoringpy.reanimator.load_pydb("path/to/database.db")

# Search for function calls
results = db.search(function_filter="my_function", limit=10)

# Get details about a specific function call (raw data)
call_id = results[0]['id']
details = db.get_call_details(call_id)

# Reanimate a function call (metadata only)
reanimated = db.reanimate(call_id)

# Reanimate a function call with actual Python objects
reanimated_objects = db.reanimate_objects(call_id)
args = reanimated_objects['locals']  # Dictionary of actual Python objects
```

### Searching for Function Calls

The `search` method allows you to find function calls based on various criteria:

```python
# Search by function name
results = db.search(function_filter="calculate_fibonacci")

# Search by file path
results = db.search(file_filter="math_utils.py")

# Search by time range
import datetime
start_time = datetime.datetime(2023, 1, 1)
end_time = datetime.datetime(2023, 1, 31)
results = db.search(time_range=(start_time, end_time))

# Search by performance metrics
results = db.search(perf_filter={'pkg': 100.0, 'dram': 50.0})

# Combine multiple filters
results = db.search(
    function_filter="calculate_fibonacci",
    file_filter="math_utils.py",
    time_range=(start_time, end_time),
    perf_filter={'pkg': 100.0}
)
```

### Getting Function Call Details

Once you have found a function call of interest, you can get detailed information about it:

```python
call_id = results[0]['id']
details = db.get_call_details(call_id)

# Access function information
function_name = details['function']
file_path = details['file']
line_number = details['line']
start_time = details['start_time']
end_time = details['end_time']

# Access arguments and local variables (raw data)
locals_dict = details['locals']
for name, value in locals_dict.items():
    print(f"{name}: {value}")

# Access return value (raw data)
return_value = details['return_value']
```

### Reanimating Function Calls (Metadata Only)

The basic reanimation feature allows you to access the metadata of a function call:

```python
reanimated = db.reanimate(call_id)

# Access function information
function_name = reanimated['function_name']
file_path = reanimated['file_path']

# Access arguments and local variables (metadata)
locals_dict = reanimated['locals']
globals_dict = reanimated['globals']
return_value = reanimated['return_value']
```

### Reanimating Function Calls with Actual Python Objects

The advanced reanimation feature reconstructs actual Python objects from their stored representations:

```python
reanimated_objects = db.reanimate_objects(call_id)

# Access function information
function_name = reanimated_objects['function_name']
file_path = reanimated_objects['file_path']

# Access arguments and local variables as actual Python objects
locals_dict = reanimated_objects['locals']
for name, value in locals_dict.items():
    print(f"{name}: {value} (type: {type(value)})")

# Access global variables as actual Python objects
globals_dict = reanimated_objects['globals']
for name, value in globals_dict.items():
    print(f"{name}: {value} (type: {type(value)})")

# Access return value as an actual Python object
return_value = reanimated_objects['return_value']
```

### Executing Reanimated Functions

You can also re-execute a function with the same arguments as a previous call:

```python
try:
    result = db.execute_reanimated(call_id)
    print(f"Execution result: {result}")
except Exception as e:
    print(f"Error executing function: {e}")
```

Note: This feature requires that the function and its module are still available in the current environment.

## Example

Here's a complete example of using the reanimator with object reconstruction:

```python
import monitoringpy.reanimator

# Load the database
db = monitoringpy.reanimator.load_pydb("monitoring.db")

# Search for all calls to a specific function
calls = db.search(function_filter="calculate_fibonacci", limit=5)
print(f"Found {len(calls)} function calls")

# Get details about the first call
if calls:
    call_id = calls[0]['id']
    
    # Get raw data
    details = db.get_call_details(call_id)
    print(f"Function: {details['function']}")
    print(f"Raw arguments:")
    for name, value in details['locals'].items():
        print(f"  {name}: {value}")
    
    # Reanimate with actual Python objects
    reanimated = db.reanimate_objects(call_id)
    print(f"Reconstructed arguments:")
    for name, value in reanimated['locals'].items():
        print(f"  {name}: {value} (type: {type(value)})")
    
    # Re-execute the function
    try:
        result = db.execute_reanimated(call_id)
        print(f"Re-execution result: {result}")
        print(f"Original result: {reanimated['return_value']}")
        print(f"Results match: {result == reanimated['return_value']}")
    except Exception as e:
        print(f"Error executing function: {e}")
```

## API Reference

### `load_pydb(db_path)`

Loads a PyMonitor database for reanimation.

- **Parameters**:
  - `db_path` (str): Path to the SQLite database file
- **Returns**: `PyDBReanimator` instance

### `PyDBReanimator` Class

#### `__init__(db_path)`

Initializes the reanimator with a database path.

- **Parameters**:
  - `db_path` (str): Path to the SQLite database file

#### `search(function_filter=None, file_filter=None, time_range=None, perf_filter=None, limit=100)`

Searches for function calls in the database based on various filters.

- **Parameters**:
  - `function_filter` (str or callable, optional): Function name or callable to filter by
  - `file_filter` (str, optional): File path to filter by
  - `time_range` (tuple, optional): Tuple of (start_time, end_time) as datetime objects
  - `perf_filter` (dict, optional): Dict with performance thresholds (e.g., {'pkg': 100, 'dram': 50})
  - `limit` (int, optional): Maximum number of results to return
- **Returns**: List of function call metadata dictionaries

#### `get_call_details(call_id)`

Gets detailed information about a specific function call.

- **Parameters**:
  - `call_id` (str): ID of the function call
- **Returns**: Dictionary with detailed function call information (raw data)

#### `reanimate(call_id)`

Reanimates a function call by reconstructing its arguments and local variables (metadata only).

- **Parameters**:
  - `call_id` (str): ID of the function call to reanimate
- **Returns**: Dictionary containing the reconstructed arguments and local variables as metadata

#### `reanimate_objects(call_id)`

Reanimates a function call by reconstructing its arguments and local variables into actual Python objects.

- **Parameters**:
  - `call_id` (str): ID of the function call to reanimate
- **Returns**: Dictionary containing the reconstructed arguments and local variables as Python objects

#### `execute_reanimated(call_id)`

Executes a function with its reanimated arguments.

- **Parameters**:
  - `call_id` (str): ID of the function call to execute
- **Returns**: The result of the function execution 