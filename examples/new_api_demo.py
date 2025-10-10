#!/usr/bin/env python3
"""
Demo of the new SpaceTimePy API with simplified decorator syntax.

This example demonstrates the new @spacetimepy.function and @spacetimepy.line
decorators which provide a cleaner, more intuitive interface.
"""
import spacetimepy

# Initialize monitoring
monitor = spacetimepy.init_monitoring(db_path="new_api_demo.db")

# Start a session
spacetimepy.start_session("New API Demo")


# Example 1: Simple function-level monitoring
@spacetimepy.function
def calculate_total(items):
    """Calculate the total of a list of items."""
    return sum(items)


# Example 2: Line-level monitoring for detailed tracing
@spacetimepy.line
def process_data(data):
    """Process data with line-by-line monitoring."""
    result = []
    for item in data:
        # Each line is monitored
        processed = item * 2
        result.append(processed)
    return result


# Example 3: Function with advanced options
def helper_function(value):
    """A helper function that will be tracked."""
    return value + 10


@spacetimepy.function(
    ignore=["temp"],  # Don't record the 'temp' variable
    track=[helper_function],  # Track calls to helper_function
)
def advanced_function(x):
    """Function with tracking and ignore options."""
    temp = x * 100  # This won't be recorded
    result = helper_function(x)  # This call will be tracked
    return result


# Example 4: Line monitoring with specific line filtering
@spacetimepy.line(lines=[67, 68, 69])  # Only monitor specific lines
def selective_monitoring(items):
    """Only monitor lines 67, 68, 69."""
    total = 0
    for item in items:  # Line 67
        total += item   # Line 68
    return total        # Line 69


# Example 5: Using custom hooks
def custom_return_hook(monitor, code, offset, return_value):
    """Custom hook that adds metadata about the return value."""
    return {
        "return_type": type(return_value).__name__,
        "return_size": len(return_value) if hasattr(return_value, '__len__') else 1
    }


@spacetimepy.function(return_hooks=[custom_return_hook])
def function_with_hooks(data):
    """Function with custom return hooks."""
    return [x * 2 for x in data]


# Run examples
if __name__ == "__main__":
    print("Running new API demonstrations...")
    
    # Example 1
    total = calculate_total([1, 2, 3, 4, 5])
    print(f"Total: {total}")
    
    # Example 2
    processed = process_data([10, 20, 30])
    print(f"Processed: {processed}")
    
    # Example 3
    result = advanced_function(5)
    print(f"Advanced result: {result}")
    
    # Example 4
    selective_result = selective_monitoring([1, 2, 3, 4])
    print(f"Selective result: {selective_result}")
    
    # Example 5
    hooked_result = function_with_hooks([1, 2, 3])
    print(f"Hooked result: {hooked_result}")
    
    # End session
    spacetimepy.end_session()
    
    print(f"\nSession data saved to: new_api_demo.db")
    print("Use the web explorer to view the recorded execution:")
    print("  web-spacetimepy new_api_demo.db")
