#!/usr/bin/env python3
"""
Example script demonstrating how to use the PyMonitor reanimator functionality.
This script shows how to load a monitoring database, search for function calls,
and reanimate them. It also demonstrates the new object versioning features.
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
    db_path = "basic.db"
    
    db = load_pydb(db_path)
    
    # Example 1: Search for all function calls
    calls = db.search(limit=10)
    print(f"Found {len(calls)} function calls")
    for i, call in enumerate(calls):
        print(f"{i+1}. {call['function']} (ID: {call['id']})")
    
    # Make sure we have at least one call
    assert len(calls) > 0, "No function calls found in the database"
    
    # Example 2: Search for a specific function
    function_name = "linear_function"  # Replace with a function name in your database
    calls = db.search(function_filter=function_name, limit=10)
    print(f"\nFound {len(calls)} calls to {function_name}")
    
    # Make sure we have at least one call to the function
    assert len(calls) > 0, f"No calls to {function_name} found in the database"
    
    # Use the first call for the rest of the examples
    call_id = calls[0]['id']
    
    # Example 3: Search with performance filter
    # Note: This might not return any results depending on the database
    perf_filter: Dict[str, float] = {'pkg': 1000.0}  # Use float values for performance metrics
    perf_calls = db.search(perf_filter=perf_filter, limit=10)
    print(f"\nFound {len(perf_calls)} calls with performance filter")
    
    # Example 4: Get detailed information about a function call
    details = db.get_call_details(call_id)
    print(f"\nDetails for call {call_id}:")
    print(f"Function: {details.get('function')}")
    print(f"Line: {details.get('line')}")
    
    assert 'locals' in details, "No locals found in call details"
    assert 'return_value' in details, "No return value found in call details"
    
    # Example 5: Reanimate a function call with actual Python objects
    print(f"\nReanimating call {call_id}...")
    reanimated_objects = db.reanimate_objects(call_id)
    print(f"Function name: {reanimated_objects.get('function_name')}")
    print(f"File path: {reanimated_objects.get('file_path')}")
    
    # Print local variables
    print("\nLocal variables:")
    for name, value in reanimated_objects.get('locals', {}).items():
        print(f"  {name}: {value} (type: {type(value).__name__})")
    
    # Print global variables
    print("\nGlobal variables:")
    for name, value in reanimated_objects.get('globals', {}).items():
        print(f"  {name}: {value} (type: {type(value).__name__})")
    
    # Print return value
    print(f"\nReturn value: {reanimated_objects.get('return_value')} (type: {type(reanimated_objects.get('return_value')).__name__})")
    
    # Example 6: Get object version history
    print("\nGetting object version history...")
    # Try to find a variable that might have multiple versions
    var_name = "x"  # Replace with a variable name in your database
    history = db.get_object_history(var_name)
    
    if history:
        print(f"Found {len(history)} object identities for '{var_name}'")
        for i, obj_history in enumerate(history):
            identity = obj_history['identity']
            versions = obj_history['versions']
            
            print(f"\nObject {i+1}:")
            print(f"  Identity: {identity['identity_hash']}")
            print(f"  Name: {identity['name']}")
            print(f"  Creation time: {identity['creation_time']}")
            print(f"  Latest version: {identity['latest_version']['version_number']}")
            
            print(f"  Versions: {len(versions)}")
            for version in versions:
                print(f"    Version {version['version_number']} ({version['timestamp']}):")
                if 'value' in version:
                    print(f"      Value: {version['value']}")
                
                if 'function_calls' in version:
                    print(f"      Referenced in {len(version['function_calls'])} function calls")
                    for call in version['function_calls'][:3]:  # Show first 3 calls
                        print(f"        {call['function']} ({call['role']} as '{call['name']}')")
    else:
        print(f"No version history found for '{var_name}'")
    
    # Example 7: Compare object versions
    print("\nComparing object versions...")
    # This requires having at least two versions of an object
    # We'll try to find two versions from the history
    if history and len(history) > 0:
        obj_history = history[0]
        versions = obj_history['versions']
        
        if len(versions) >= 2:
            version1 = versions[0]
            version2 = versions[-1]  # Compare first and last version
            
            comparison = db.compare_versions(version1['version_id'], version2['version_id'])
            
            print(f"Comparing version {version1['version_number']} with version {version2['version_number']}:")
            if 'differences' in comparison:
                if comparison['differences']:
                    print(f"  Found {len(comparison['differences'])} differences:")
                    for diff in comparison['differences']:
                        print(f"    {diff['type']}: {diff.get('name', diff.get('key', ''))} - {diff['value1']} -> {diff['value2']}")
                else:
                    print("  No differences found")
            elif 'error' in comparison:
                print(f"  Error: {comparison['error']}")
        else:
            print("  Not enough versions to compare")
    
    # Test nested list structure (ncl) if it exists
    print("\nTesting nested list structure (ncl):")
    ncl = reanimated_objects.get('globals', {}).get('ncl')
    
    if ncl is not None:
        print(f"Reanimated ncl: {ncl}")
        print(f"Type of ncl: {type(ncl)}")
        
        # Verify it's a list
        assert isinstance(ncl, list), f"ncl should be a list, but got {type(ncl)}"
        
        # Check if it's a list of lists
        if len(ncl) > 0 and all(isinstance(item, list) for item in ncl):
            print("ncl is a list of lists!")
            for i, inner_list in enumerate(ncl):
                print(f"  Inner list {i}: {inner_list} (type: {type(inner_list).__name__})")
                
            # Debug the structure of ncl in the database
            print("\nDebugging ncl structure in the database:")
            structure_info = db.debug_nested_structure(call_id, 'ncl')
            print("Structure info:")
            pprint(structure_info)
            
            # Compare with the expected value from basic.py
            expected_ncl = [[1, 2, 3], [4, 5, 6]]
            print(f"\nExpected ncl from basic.py: {expected_ncl}")
            print(f"Actual reanimated ncl: {ncl}")
            
            if ncl == expected_ncl:
                print("SUCCESS: Reanimated ncl matches the expected value!")
            else:
                print("FAILURE: Reanimated ncl does not match the expected value.")
                print("This indicates an issue with the reanimation of nested lists.")
                
                # Get the raw data from the database for comparison
                raw_details = db.get_call_details(call_id)
                raw_ncl = raw_details.get('globals', {}).get('ncl')
                print(f"\nRaw ncl from database: {raw_ncl}")
                
                # Check if the raw data has the correct structure
                if isinstance(raw_ncl, dict) and raw_ncl.get('type') == 'list':
                    items = raw_ncl.get('items', {})
                    print(f"Raw ncl has {len(items)} items")
                    
                    for key, item in items.items():
                        print(f"  Item {key}: {item}")
                        
                        if isinstance(item, dict) and item.get('type') == 'list':
                            sub_items = item.get('items', {})
                            print(f"    Sub-items: {sub_items}")
        else:
            print("ncl is not a list of lists or is empty")
    else:
        print("ncl not found in globals")


if __name__ == "__main__":
    main() 