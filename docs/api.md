# PyMonitor API Documentation

This document describes the REST API endpoints available in PyMonitor's web explorer.

## Function Calls

### List Function Calls
- **Endpoint**: `/api/function-calls`
- **Method**: GET
- **Query Parameters**:
  - `search` (optional): Search term to filter function names
  - `file` (optional): Filter by exact file path
  - `function` (optional): Filter by exact function name
- **Response**: 
```json
{
    "function_calls": [
        {
            "id": "1",
            "function": "binary_search_line",
            "file": "examples/basic3.py",
            "line": 8,
            "start_time": "2024-03-14T15:30:00",
            "end_time": "2024-03-14T15:30:01",
            "locals": {...},
            "globals": {...},
            "return_value": "..."
        }
    ],
    "total_calls": 10,
    "processed_calls": 10
}
```

### Get Function Call Details
- **Endpoint**: `/api/function-call/{call_id}`
- **Method**: GET
- **Response**: 
```json
{
    "id": "1",
    "function": "binary_search_line",
    "file": "examples/basic3.py",
    "line": 8,
    "start_time": "2024-03-14T15:30:00",
    "end_time": "2024-03-14T15:30:01",
    "locals": {...},
    "globals": {...},
    "return_value": "...",
    "prev_call": "2",  // ID of previous call in history
    "next_call": "4"   // ID of next call in history
}
```

## Stack Traces

### Get Stack Trace
- **Endpoint**: `/api/stack-trace/{function_id}`
- **Method**: GET
- **Response**:
```json
{
    "function_id": "1",
    "function_name": "binary_search_line",
    "file": "examples/basic3.py",
    "line": 8,
    "start_time": "2024-03-14T15:30:00",
    "end_time": "2024-03-14T15:30:01",
    "code": {
        "content": "...",
        "module_path": "...",
        "type": "function",
        "first_line_no": 8
    },
    "snapshots": [
        {
            "id": "1",
            "line": 9,
            "timestamp": "2024-03-14T15:30:00.100",
            "locals": {...},
            "globals": {...}
        }
    ]
}
```

### Get Snapshot Details
- **Endpoint**: `/api/snapshot/{snapshot_id}`
- **Method**: GET
- **Response**:
```json
{
    "id": "1",
    "line": 9,
    "timestamp": "2024-03-14T15:30:00.100",
    "locals": {
        "variable_name": {
            "value": "...",
            "type": "..."
        }
    },
    "globals": {
        "variable_name": {
            "value": "...",
            "type": "..."
        }
    }
}
```

## Object Graph

### Get Object Graph
- **Endpoint**: `/api/object-graph`
- **Method**: GET
- **Response**:
```json
{
    "nodes": [
        {
            "data": {
                "id": "...",
                "label": "...",
                "type": "..."
            }
        }
    ],
    "edges": [
        {
            "data": {
                "id": "...",
                "source": "...",
                "target": "...",
                "label": "...",
                "edgeType": "..."
            }
        }
    ]
}
```

## Database Information

### Get Database Info
- **Endpoint**: `/api/db-info`
- **Method**: GET
- **Response**:
```json
{
    "db_path": "/path/to/database.db"
}
```

## Error Responses

All endpoints may return error responses in the following format:
```json
{
    "error": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- 200: Success
- 404: Resource not found
- 500: Internal server error

## Base URL

By default, the API is served at `http://localhost:5000/api/`

## Examples

### Get all calls of a specific function

```bash
curl http://localhost:5000/api/function-calls?function=binary_search_line
```

### Get details of a specific function call

```bash
curl http://localhost:5000/api/function-call/123
```

### Get database information

```bash
curl http://localhost:5000/api/db-info
```

## Using with Other Applications

To integrate PyMonitor with other applications:

1. Start the PyMonitor web server:
   ```bash
   python -m monitoringpy.web_explorer your_database.db
   ```

2. Make HTTP requests to the API endpoints from your application.

3. Process the JSON responses as needed.

Example Python code to interact with the API:

```python
import requests

# Base URL for the API
BASE_URL = 'http://localhost:5000/api'

# Get all calls for a specific function
def get_function_calls(function_name):
    response = requests.get(f'{BASE_URL}/function-calls', params={'function': function_name})
    return response.json()

# Get details of a specific call
def get_call_details(call_id):
    response = requests.get(f'{BASE_URL}/function-call/{call_id}')
    return response.json()

# Get database information
def get_db_info():
    response = requests.get(f'{BASE_URL}/db-info')
    return response.json()
```

## Notes

- All timestamps are in ISO 8601 format
- Object references in responses can be used to track object versions
- Function calls include navigation links to previous and next calls
- The API uses standard HTTP status codes (200 for success, 4xx for client errors, 5xx for server errors)
- Large responses may include pagination information 

## Function Reanimation API

PyMonitor provides Python functions for reanimating previous function executions. These are not REST API endpoints but Python library functions.

### Load Function Execution Data

```python
from monitoringpy import load_execution_data

args, kwargs = load_execution_data(
    function_execution_id="123",  # ID of the stored function execution
    db_path="monitoring.db"       # Path to the database
)
```

**Parameters**:
- `function_execution_id`: String ID of the function execution to load
- `db_path`: Path to the database file containing the execution data

**Returns**:
- A tuple of `(args, kwargs)` where:
  - `args`: List of positional arguments
  - `kwargs`: Dictionary of keyword arguments

### Reanimate Function

```python
from monitoringpy import reanimate_function

result = reanimate_function(
    function_execution_id="123",   # ID of the stored function execution
    db_path="monitoring.db",       # Path to the database
    import_path="/path/to/module"  # Optional path to add to sys.path
)
```

**Parameters**:
- `function_execution_id`: String ID of the function execution to reanimate
- `db_path`: Path to the database file containing the execution data
- `import_path`: (Optional) Path to add to sys.path before importing the function module

**Returns**:
- The result of executing the function with the original arguments

### Delete Function Execution

```python
from monitoringpy import delete_function_execution

success = delete_function_execution(
    function_execution_id="123",  # ID of the function execution to delete
    db_path="monitoring.db"       # Path to the database
)
```

**Parameters**:
- `function_execution_id`: String ID of the function execution to delete
- `db_path`: Path to the database file containing the execution data

**Returns**:
- Boolean value indicating whether the deletion was successful

### Web API Extension for Deletion
For completeness, the following REST API endpoint is recommended to be added to the web interface:

- **Endpoint**: `/api/function-call/{call_id}`
- **Method**: DELETE
- **Response**: 
```json
{
    "success": true,
    "message": "Function call deleted successfully"
}
```

or in case of failure:
```json
{
    "success": false,
    "error": "Error message describing what went wrong"
}
```

### Generate Reanimation Script

The Web Explorer provides an additional endpoint to generate a reanimation script:

- **Endpoint**: `/api/generate-reanimation-script/{call_id}`
- **Method**: GET
- **Response**: 
```json
{
    "script": "# PyMonitor reanimation script\nimport sys\nimport monitoringpy\n\n# Set paths\nsys.path.insert(0, \"/path/to/module\")\n\n# Reanimate the function\nresult = monitoringpy.reanimate_function(\n    function_execution_id=\"123\",\n    db_path=\"/path/to/database.db\"\n)\n\nprint(f\"Result: {result}\")"
}
```

For more detailed documentation on the reanimation features, see [reanimation.md](reanimation.md). 