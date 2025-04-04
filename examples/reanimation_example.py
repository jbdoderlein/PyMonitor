#!/usr/bin/env python3
"""
Example demonstrating PyMonitor's function reanimation features.

This example:
1. Creates a function and monitors its execution
2. Gets the function execution ID
3. Reanimates the function with the same arguments
"""

import os
import sys
import random
from monitoringpy import init_monitoring, pymonitor, load_execution_data, reanimate_function

# Define a function to monitor
@pymonitor
def sort_and_find(numbers, target):
    """Sort a list of numbers and find a target value's position."""
    print(f"Sorting list of {len(numbers)} numbers and finding {target}")
    sorted_list = sorted(numbers)
    
    # Binary search for the target
    left, right = 0, len(sorted_list) - 1
    while left <= right:
        mid = (left + right) // 2
        if sorted_list[mid] == target:
            return mid
        elif sorted_list[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    
    return -1

def main():
    # Create a database file
    db_path = "reanimation_example.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Initialize monitoring
    init_monitoring(db_path)
    print(f"Initialized monitoring with database at {db_path}")
    
    # Generate random data
    numbers = [random.randint(1, 100) for _ in range(20)]
    target = random.choice(numbers)
    
    print("\n--- Original Function Execution ---")
    print(f"Input: numbers={numbers}, target={target}")
    
    # Call the monitored function
    result = sort_and_find(numbers, target)
    print(f"Result: {result}")
    
    # Get the function call ID (last recorded call for this function)
    from monitoringpy.core import init_db, FunctionCallTracker
    Session = init_db(db_path)
    session = Session()
    tracker = FunctionCallTracker(session)
    call_ids = tracker.get_call_history("sort_and_find")
    function_execution_id = call_ids[-1]  # Get the most recent call
    session.close()
    
    print(f"\nFunction execution ID: {function_execution_id}")
    
    # Now demonstrate reanimation
    print("\n--- Function Reanimation Using load_execution_data ---")
    
    # Load the arguments
    args, kwargs = load_execution_data(function_execution_id, db_path)
    print(f"Loaded args: {args}")
    print(f"Loaded kwargs: {kwargs}")
    
    # Call the function with the same arguments
    reanimated_result = sort_and_find(*args, **kwargs)
    print(f"Reanimated result: {reanimated_result}")
    
    # Now demonstrate the reanimate_function shorthand
    print("\n--- Function Reanimation Using reanimate_function ---")
    
    # Use the all-in-one approach
    reanimated_result2 = reanimate_function(function_execution_id, db_path)
    print(f"Reanimated result: {reanimated_result2}")
    
    # Verify all results match
    print("\n--- Verification ---")
    print(f"Original result: {result}")
    print(f"Reanimation with load_execution_data: {reanimated_result}")
    print(f"Reanimation with reanimate_function: {reanimated_result2}")
    print(f"All results match: {result == reanimated_result == reanimated_result2}")

if __name__ == "__main__":
    main() 