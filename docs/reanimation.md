# Function Reanimation

This document explains how to use PyMonitor's function reanimation features, which allow you to replay previous function executions from their stored state.

## Overview

The function reanimation system provides a way to:

1. Extract stored function execution data from the PyMonitor database
2. Replay function executions with the exact same arguments as before
3. Reuse captured function arguments for testing, debugging, or demonstration purposes
4. Delete specific function executions when they are no longer needed

## Basic Usage

### Loading Function Execution Data

To load the arguments for a specific function execution:

```python
import monitoringpy

# Load function execution data
args, kwargs = monitoringpy.load_execution_data(
    function_execution_id="123",  # ID of the stored function execution
    db_path="monitoring.db"       # Path to the database
)

# Print the arguments
print(f"Args: {args}")
print(f"Kwargs: {kwargs}")
```

### Reanimating Function Executions

For a complete reanimation that handles importing the function and executing it:

```python
import monitoringpy

# Reanimate a function execution
result = monitoringpy.reanimate_function(
    function_execution_id="123",   # ID of the stored function execution
    db_path="monitoring.db",       # Path to the database
    import_path="/path/to/module"  # Optional path to add to sys.path
)

# Print the result
print(f"Result: {result}")
```

### Deleting Function Executions

To delete a function execution and its associated data:

```python
import monitoringpy

# Delete a function execution
success = monitoringpy.delete_function_execution(
    function_execution_id="123",  # ID of the stored function execution
    db_path="monitoring.db"       # Path to the database
)

if success:
    print("Function execution deleted successfully")
else:
    print("Failed to delete function execution")
```

## Practical Examples

### Replaying a Function with Error

```python
import monitoringpy

# Assume you have a function execution that failed
try:
    result = monitoringpy.reanimate_function("123", "monitoring.db")
    print(f"Result: {result}")
except Exception as e:
    print(f"Error during reanimation: {e}")
    
    # Load just the arguments to inspect them
    args, kwargs = monitoringpy.load_execution_data("123", "monitoring.db")
    print(f"Args: {args}")
    print(f"Kwargs: {kwargs}")
```

### Debugging a Function Execution

```python
import monitoringpy
import pdb

# Get the function arguments
args, kwargs = monitoringpy.load_execution_data("123", "monitoring.db")

# Import the function manually
from your_module import problematic_function

# Set a breakpoint and run the function with the same arguments
pdb.set_trace()
result = problematic_function(*args, **kwargs)
```

### Creating Automated Test Cases

```python
import monitoringpy
import unittest

class TestFromRecordedExecution(unittest.TestCase):
    def test_recorded_function(self):
        # Get arguments from recorded execution
        args, kwargs = monitoringpy.load_execution_data("123", "monitoring.db")
        
        # Import the function
        from your_module import your_function
        
        # Execute the function and check the result
        result = your_function(*args, **kwargs)
        self.assertEqual(result, expected_value)
```

### Database Cleanup

```python
import monitoringpy
from monitoringpy.core import init_db, FunctionCallTracker

# Get all function executions for a specific function
db_path = "monitoring.db"
Session = init_db(db_path)
session = Session()
tracker = FunctionCallTracker(session)
call_ids = tracker.get_call_history("my_function")
session.close()

# Delete all but the most recent 5 executions
if len(call_ids) > 5:
    for call_id in call_ids[:-5]:
        monitoringpy.delete_function_execution(call_id, db_path)
        print(f"Deleted execution {call_id}")
```

## Integration with Web Explorer

The PyMonitor Web Explorer can generate scripts for reanimating functions:

1. Browse to a function execution in the Web Explorer
2. Click "Generate Reanimation Script"
3. Copy and modify the generated script as needed

Example of a generated script:

```python
# PyMonitor reanimation script - generated from Web Explorer
import sys
import monitoringpy

# Set paths
sys.path.insert(0, "/path/to/your/module")

# Reanimate the function
result = monitoringpy.reanimate_function(
    function_execution_id="123",
    db_path="/path/to/monitoring.db"
)

print(f"Result: {result}")
```

## Advanced Usage

### Custom Reanimation Logic

For more complex scenarios, you can use the low-level APIs:

```python
import monitoringpy
from monitoringpy.core import init_db, ObjectManager

# Initialize database
Session = init_db("monitoring.db")
session = Session()

try:
    # Create managers
    obj_manager = ObjectManager(session)
    
    # Get stored objects by reference
    stored_obj = obj_manager.get("obj_ref_123")
    
    # Work with loaded objects
    print(f"Stored object: {stored_obj}")
    
    # Manually rehydrate objects
    rehydrated = obj_manager.rehydrate("obj_ref_123")
    print(f"Rehydrated: {rehydrated}")
    
finally:
    session.close()
```

### Working with Complex Objects

For complex objects like custom classes:

```python
import monitoringpy

# Get the arguments
args, kwargs = monitoringpy.load_execution_data("123", "monitoring.db")

# Access complex objects
complex_obj = kwargs.get("complex_param")

# Inspect the object
print(f"Type: {type(complex_obj)}")
print(f"Attributes: {dir(complex_obj)}")

# Work with the object
result = complex_obj.some_method()
```

### Bulk Function Deletion

To delete multiple function executions at once:

```python
import monitoringpy
from monitoringpy.core import init_db, FunctionCallTracker

# Get all executions of functions that match a pattern
db_path = "monitoring.db"
Session = init_db(db_path)
session = Session()
tracker = FunctionCallTracker(session)

# Find all function calls
all_calls = tracker.get_call_history() 

# Filter to find test functions
test_calls = [call_id for call_id in all_calls 
              if "test_" in tracker.get_call(call_id)["function"]]
session.close()

# Delete all test functions
for call_id in test_calls:
    monitoringpy.delete_function_execution(call_id, db_path)
    print(f"Deleted test function execution {call_id}")
```

## Best Practices

1. **Database Location**: Keep your database files in a consistent location and use absolute paths to avoid path-related issues.

2. **Module Imports**: Ensure that the modules containing your functions are importable. You might need to adjust your `PYTHONPATH` or use the `import_path` parameter.

3. **Complex Objects**: Be aware that some very complex objects may not rehydrate perfectly. Test and verify before relying on reanimation for critical operations.

4. **Session Management**: Always close your database sessions when done, preferably using context managers or try/finally blocks.

5. **Error Handling**: Wrap reanimation calls in try/except blocks to handle potential errors gracefully.

6. **Database Management**: Regularly clean up old or unused function executions to keep the database size manageable. Consider implementing an automatic cleanup policy for large projects.

## Limitations

- The reanimation system can only replay functions that were previously monitored with PyMonitor.
- External dependencies and global state may affect replay reliability.
- Functions that rely on external resources (files, network connections, etc.) may behave differently during reanimation.
- Very complex objects or those with custom pickle behavior might not rehydrate perfectly.
- Deleting function executions might affect reference counts for stored objects, but won't delete objects that are referenced by other function calls.

## Troubleshooting

### Function Not Found

If the function cannot be imported:

1. Ensure the module is in your Python path
2. Check that the function name matches exactly
3. Use the `import_path` parameter to add the directory to `sys.path`

### Arguments Don't Match

If the arguments don't match the function signature:

1. Check the function's current definition
2. Look for changes in parameter names or order
3. Consider extracting the arguments and manually adapting them

### Database Errors

For database connection issues:

1. Verify the database file exists and is readable
2. Check permissions on the database file
3. Ensure you're using the correct database path

### Deletion Failures

If deleting a function execution fails:

1. Verify that the function execution ID exists in the database
2. Check for database lock issues (another process might be using the database)
3. Ensure you have write permissions on the database file

## Future Enhancements

The reanimation system will be expanded in future releases to include:

- Support for reanimating class methods with proper instance state
- Enhanced handling of complex data structures
- Integration with debuggers for step-by-step reanimation
- Time travel debugging features to explore execution state
- Bulk operations for deleting multiple function executions at once 