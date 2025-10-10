#!/usr/bin/env python3
"""
Example demonstrating how to delete function executions with SpaceTimePy.

This example:
1. Creates a function and monitors its execution
2. Lists all function executions in the database
3. Deletes a specific function execution
4. Verifies the deletion
"""

import os
from spacetimepy import init_monitoring, pymonitor, delete_function_execution

# Define a function to monitor
@pymonitor
def example_function(a, b):
    """A simple example function."""
    print(f"Running example_function({a}, {b})")
    return a + b

def main():
    # Create a database file
    db_path = "delete_example.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Initialize monitoring
    init_monitoring(db_path)
    print(f"Initialized monitoring with database at {db_path}")
    
    # Call the monitored function multiple times
    print("\n--- Creating function executions ---")
    for i in range(3):
        result = example_function(i, i+1)
        print(f"  Call {i+1} result: {result}")
    
    # Get all function call IDs
    from spacetimepy.core import init_db, FunctionCallTracker
    Session = init_db(db_path)
    session = Session()
    tracker = FunctionCallTracker(session)
    call_ids = tracker.get_call_history("example_function")
    print(f"\nFunction executions in database: {call_ids}")
    
    if not call_ids:
        print("No function executions found in database")
        session.close()
        return
    
    # Delete the second function call
    target_id = call_ids[1] if len(call_ids) > 1 else call_ids[0]
    session.close()
    
    print(f"\n--- Deleting function execution {target_id} ---")
    success = delete_function_execution(target_id, db_path)
    print(f"Deletion {'successful' if success else 'failed'}")
    
    # Verify the deletion
    Session = init_db(db_path)
    session = Session()
    tracker = FunctionCallTracker(session)
    remaining_calls = tracker.get_call_history("example_function")
    session.close()
    
    print(f"\nRemaining function executions: {remaining_calls}")
    print(f"Execution {target_id} {'was' if target_id not in remaining_calls else 'was not'} deleted")
    
    # Try to delete a non-existent execution
    print("\n--- Trying to delete non-existent execution ---")
    nonexistent_id = "9999"
    success = delete_function_execution(nonexistent_id, db_path)
    print(f"Deletion {'successful' if success else 'failed'}")

if __name__ == "__main__":
    main() 