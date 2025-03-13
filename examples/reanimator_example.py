#!/usr/bin/env python3
"""
Example script demonstrating how to use the PyMonitor reanimator functionality.
This script shows how to load a monitoring database, search for function calls,
and reanimate them.
"""

import os
import sys
import datetime
from pprint import pprint
from typing import Dict

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import basic
from src.monitoringpy import load_pydb

def main():
    # Path to the database file
    db_path = "examples/basic.db"
    
    db = load_pydb(db_path)
    
    # Example 1: Search for all function calls
    calls = db.search(limit=5)
    assert len(calls) == 5
    assert calls[0]['function'] == "linear_function"

    
    # Example 2: Search for a specific function
    function_name = "linear_function"  # Replace with a function name in your database
    calls = db.search(function_filter=function_name, limit=3)
    assert len(calls) == 3
    assert calls[0]['function'] == "linear_function"
    
    # Example 3: Search with performance filter
    perf_filter: Dict[str, float] = {'pkg': 1000.0}  # Use float values for performance metrics
    calls = db.search(perf_filter=perf_filter, limit=3)
    assert len(calls) == 1
    assert calls[0]['function'] == "linear_function"
    
    # Example 4: Get detailed information about a function call
    call_id = calls[0]['id']
    details = db.get_call_details(call_id)
    assert details.get('function') == "linear_function"
    assert details.get('line') == 25
    assert details.get('start_time') is not None
    assert details.get('end_time') is not None

    assert 'locals' in details
    assert details.get('locals', {}).get('x') is not None
    assert details.get('locals', {}).get('cl') is not None
        
    assert 'return_value' in details
    assert details.get('return_value') is not None
    
    
    # Example 6: Reanimate a function call with actual Python objects
    call_id = calls[0]['id']
    reanimated_objects = db.reanimate_objects(call_id)
    assert reanimated_objects.get('function_name') == "linear_function"
    assert reanimated_objects.get('file_path') is not None
        
    # Print local variables
    assert 'locals' in reanimated_objects
    assert isinstance(reanimated_objects.get('locals', {}).get('x'), int)
    assert isinstance(reanimated_objects.get('locals', {}).get('cl'), basic.CustomClass)
    assert hasattr(reanimated_objects.get('locals', {}).get('cl'), "x")
    assert reanimated_objects.get('locals', {}).get('cl').x == 0
    # Print global variables
    assert 'globals' in reanimated_objects
    assert isinstance(reanimated_objects.get('globals', {}).get('gcl'), basic.CustomClass)

    # Print return value
    assert 'return_value' in reanimated_objects
    assert isinstance(reanimated_objects.get('return_value'), int)


if __name__ == "__main__":
    main() 