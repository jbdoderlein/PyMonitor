#!/usr/bin/env python3
"""
Example script demonstrating how to use the SpaceTimePy reanimator functionality.
This script shows how to load a monitoring database, search for function calls,
and reanimate them. It also demonstrates the new object versioning features.
"""

import os
import sys
from pprint import pprint
from typing import Dict

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from basic import *
from src.spacetimepy import load_pydb

def main():
    # Path to the database file
    db_path = "basic.db"
    
    db = load_pydb(db_path)
    
    # Example 1: Search for all function calls
    calls = db.search(limit=10)
    for i, call in enumerate(calls):
        print(f"{i+1}. {call['function']} (ID: {call['id']})")
    
    # Make sure we have at least one call
    assert len(calls) > 0, "No function calls found in the database"
    
    # Example 2: Search for a specific function
    function_name = "linear_function"  # Replace with a function name in your database
    calls = db.search(function_filter=function_name, limit=10)
    
    # Make sure we have at least one call to the function
    assert len(calls) > 0, f"No calls to {function_name} found in the database"
    
    # Use the first call for the rest of the examples
    call_id = calls[0]['id']
    
    # Example 3: Search with performance filter
    # Note: This might not return any results depending on the database
    perf_filter: Dict[str, float] = {'pkg': 1000.0}  # Use float values for performance metrics
    perf_calls = db.search(perf_filter=perf_filter, limit=10)
    
    # Example 4: Get detailed information about a function call
    details = db.get_call_details(call_id)
    
    assert 'locals' in details, "No locals found in call details"
    assert 'return_value' in details, "No return value found in call details"
    

    reanimated_objects = db.reanimate_objects(call_id)

    # Example 6: Get object version history
    # Try to find a variable that might have multiple versions
    var_name = "x"  # Replace with a variable name in your database
    history = db.get_object_history(var_name)
    
    # Assert that we found history for the variable
    assert history is not None, f"No history found for variable '{var_name}'"
    assert len(history) > 0, f"Expected at least one object identity for '{var_name}'"
    
    # Test the first object's history
    obj_history = history[0]
    identity = obj_history['identity']
    versions = obj_history['versions']
    
    # Assert the identity structure
    assert 'identity_hash' in identity, "Identity missing identity_hash"
    assert 'name' in identity, "Identity missing name"
    assert 'creation_time' in identity, "Identity missing creation_time"
    assert 'latest_version' in identity, "Identity missing latest_version"
    
    # Assert we have at least one version
    assert len(versions) > 0, "Expected at least one version"
    
    # Test nested list structure (ncl) if it exists
    print("\nTesting nested list structure (ncl):")
    ncl = reanimated_objects.get('globals', {}).get('ncl')
    
    # Assert ncl exists and is a list
    assert ncl is not None, "ncl not found in globals"
    assert isinstance(ncl, list), f"ncl should be a list, but got {type(ncl)}"
    
    # Assert ncl is a list of lists with correct values
    assert len(ncl) == 2, f"Expected ncl to have 2 items, got {len(ncl)}"
    assert all(isinstance(item, list) for item in ncl), "Expected all items in ncl to be lists"
    
    # Assert the values of the nested lists
    assert ncl[0] == [1, 2, 3], f"Expected first inner list to be [1, 2, 3], got {ncl[0]}"
    assert ncl[1] == [4, 5, 6], f"Expected second inner list to be [4, 5, 6], got {ncl[1]}"
    
    # Get and verify the raw data structure
    raw_details = db.get_call_details(call_id)
    raw_ncl = raw_details.get('globals', {}).get('ncl')
    assert raw_ncl is not None, "Raw ncl not found in database"
    assert raw_ncl.get('type') == 'list', f"Expected raw ncl to be a list, got {raw_ncl.get('type')}"
    
    # Debug print the raw data structure
    print("\nRaw ncl structure:")
    pprint(raw_ncl)
    
    # Verify the raw data structure
    items = raw_ncl.get('items', {})
    print("\nItems in raw_ncl:")
    pprint(items)
    
    assert len(items) == 2, f"Expected raw ncl to have 2 items, got {len(items)}"
    
    # Verify each inner list in the raw data
    for i, (key, item) in enumerate(items.items()):
        print(f"\nInner list {i}:")
        pprint(item)
        assert item.get('type') == 'list', f"Expected item {i} to be a list, got {item.get('type')}"
        
        # Get the actual list contents using the ID
        list_id = item.get('id')
        assert list_id is not None, f"Expected list {i} to have an ID"
        
        # Get the list details from the database
        list_details = db.get_call_details(list_id)
        print(f"List {i} details:")
        pprint(list_details)
        
        # Get the items from the list details
        list_items = list_details.get('items', {})
        print(f"List {i} items:")
        pprint(list_items)
        
        # Verify the number of items
        expected_values = [1, 2, 3] if i == 0 else [4, 5, 6]
        assert len(list_items) == len(expected_values), f"Expected {len(expected_values)} items in list {i}, got {len(list_items)}"
        
        # Verify each item in the list
        for j, (item_key, item_value) in enumerate(list_items.items()):
            assert item_value.get('type') == 'int', f"Expected item {j} in list {i} to be an integer"
            assert int(item_value.get('value')) == expected_values[j], f"Expected item {j} in list {i} to be {expected_values[j]}, got {item_value.get('value')}"
    
    print("SUCCESS: All nested list structure assertions passed!")

    # Test different executions of linear_function
    print("\nTesting different executions of linear_function:")
    
    # Get all calls to linear_function
    linear_calls = db.search(function_filter="linear_function")
    assert len(linear_calls) == 6, f"Expected 6 calls to linear_function, got {len(linear_calls)}"
    
    # Test the first 5 calls (with gcl.x = 10)
    for i in range(5):
        call_id = linear_calls[i]['id']
        details = db.get_call_details(call_id)
        globals_dict = details.get('globals', {})
        
        # Verify gcl.x is 10
        gcl = globals_dict.get('gcl')
        print(f"gcl: {gcl}")
        assert gcl is not None, f"gcl not found in call {call_id}"
        assert gcl.get('type') == 'object', f"Expected gcl to be an object in call {call_id}"
        assert gcl.get('__class__') == 'CustomClass', f"Expected gcl to be a CustomClass in call {call_id}"
        assert gcl.get('attributes', {}).get('x') == 10, f"Expected gcl.x to be 10 in call {call_id}"
        
        # Verify the custom object parameter
        locals_dict = details.get('locals', {})
        cl = locals_dict.get('cl')
        assert cl is not None, f"cl not found in call {call_id}"
        assert cl.get('type') == 'object', f"Expected cl to be an object in call {call_id}"
        assert cl.get('__class__') == 'CustomClass', f"Expected cl to be a CustomClass in call {call_id}"
        assert cl.get('attributes', {}).get('x') == i, f"Expected cl.x to be {i} in call {call_id}"
    
    # Test the last call (with gcl.x = 100)
    last_call_id = linear_calls[5]['id']
    last_details = db.get_call_details(last_call_id)
    last_globals = last_details.get('globals', {})
    
    # Verify gcl.x is 100
    last_gcl = last_globals.get('gcl')
    assert last_gcl is not None, "gcl not found in last call"
    assert last_gcl.get('type') == 'object', "Expected gcl to be an object in last call"
    assert last_gcl.get('__class__') == 'CustomClass', "Expected gcl to be a CustomClass in last call"
    assert last_gcl.get('attributes', {}).get('x') == 100, "Expected gcl.x to be 100 in last call"
    
    # Verify the custom object parameter in the last call
    last_locals = last_details.get('locals', {})
    last_cl = last_locals.get('cl')
    assert last_cl is not None, "cl not found in last call"
    assert last_cl.get('type') == 'object', "Expected cl to be an object in last call"
    assert last_cl.get('__class__') == 'CustomClass', "Expected cl to be a CustomClass in last call"
    assert last_cl.get('attributes', {}).get('x') == 4, "Expected cl.x to be 4 in last call"
    
    print("SUCCESS: All linear_function calls verified correctly!")


if __name__ == "__main__":
    main() 