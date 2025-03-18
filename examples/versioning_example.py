#!/usr/bin/env python3
"""
Example script demonstrating the object versioning functionality in PyMonitor.
This script creates objects, modifies them, and shows how PyMonitor tracks
the different versions of the objects.
"""

import os
import sys
import time
from pprint import pprint

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.monitoringpy import pymonitor, load_pydb

# Class to demonstrate object versioning
class VersionedObject:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.history = []
        self.update_count = 0
    
    def update(self, new_value):
        """Update the value and record the change in history"""
        old_value = self.value
        self.value = new_value
        self.history.append((old_value, new_value))
        self.update_count += 1
        return self.value
    
    def __str__(self):
        return f"VersionedObject(name={self.name}, value={self.value}, updates={self.update_count})"

# Dictionary to demonstrate versioning of structured objects
@pymonitor
def create_and_modify_objects():
    """Create and modify objects to demonstrate versioning"""
    print("Creating objects...")
    
    # Create a simple object
    obj1 = VersionedObject("obj1", 10)
    print(f"Created {obj1}")
    
    # Create a dictionary
    data = {
        "name": "test_dict",
        "values": [1, 2, 3],
        "metadata": {
            "created": "now",
            "version": 1
        }
    }
    print(f"Created dictionary: {data}")
    
    # Create a list
    items = ["apple", "banana", "cherry"]
    print(f"Created list: {items}")
    
    # Sleep to ensure time difference between versions
    time.sleep(1)
    
    # Modify the simple object
    print("\nModifying objects...")
    obj1.update(20)
    print(f"Modified obj1: {obj1}")
    
    # Modify the dictionary
    data["values"].append(4)
    data["metadata"]["version"] = 2
    print(f"Modified dictionary: {data}")
    
    # Modify the list
    items.append("date")
    print(f"Modified list: {items}")
    
    # Sleep again
    time.sleep(1)
    
    # Modify objects again
    obj1.update(30)
    print(f"Modified obj1 again: {obj1}")
    
    data["metadata"]["version"] = 3
    data["new_field"] = True
    print(f"Modified dictionary again: {data}")
    
    items[0] = "avocado"  # Replace first item
    print(f"Modified list again: {items}")
    
    return obj1, data, items

@pymonitor
def process_objects(obj, data, items):
    """Process the objects to demonstrate tracking across function calls"""
    print("\nProcessing objects...")
    
    # Modify the object
    obj.update(obj.value * 2)
    print(f"Doubled obj value: {obj}")
    
    # Modify the dictionary
    data["processed"] = True
    data["metadata"]["version"] += 1
    print(f"Added processed flag to dictionary: {data}")
    
    # Modify the list
    items.sort()
    print(f"Sorted list: {items}")
    
    return obj, data, items

def main():
    # Database file path
    db_path = "versioning.db"
    
    # Remove existing database if it exists
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")
    
    # Create and modify objects
    obj1, data, items = create_and_modify_objects()
    
    # Process the objects
    obj1, data, items = process_objects(obj1, data, items)
    
    # Load the database and analyze the versioning
    print("\nAnalyzing object versions in the database...")
    db = load_pydb(db_path)
    
    # Search for function calls
    calls = db.search()
    print(f"Found {len(calls)} function calls")
    
    # Get object version history
    print("\nObject version history:")
    
    # Check for the VersionedObject
    obj_history = db.get_object_history("obj")
    if obj_history:
        print("\nVersionedObject history:")
        for identity in obj_history:
            print(f"  Identity: {identity['identity']['identity_hash']}")
            print(f"  Name: {identity['identity']['name']}")
            print(f"  Versions: {len(identity['versions'])}")
            
            for version in identity['versions']:
                print(f"    Version {version['version_number']} ({version['timestamp']}):")
                if 'function_calls' in version:
                    for call in version['function_calls']:
                        print(f"      Referenced in {call['function']} as '{call['name']}'")
    
    # Check for the dictionary
    dict_history = db.get_object_history("data")
    if dict_history:
        print("\nDictionary history:")
        for identity in dict_history:
            print(f"  Identity: {identity['identity']['identity_hash']}")
            print(f"  Name: {identity['identity']['name']}")
            print(f"  Versions: {len(identity['versions'])}")
            
            # If we have at least two versions, compare them
            if len(identity['versions']) >= 2:
                first_version = identity['versions'][0]
                last_version = identity['versions'][-1]
                
                print(f"\nComparing first and last versions of dictionary:")
                comparison = db.compare_versions(first_version['version_id'], last_version['version_id'])
                
                if 'differences' in comparison and comparison['differences']:
                    print(f"  Found {len(comparison['differences'])} differences:")
                    for diff in comparison['differences']:
                        diff_type = diff['type']
                        if diff_type == 'attribute_changed':
                            print(f"    Attribute '{diff['name']}' changed: {diff['value1']} -> {diff['value2']}")
                        elif diff_type == 'attribute_added':
                            print(f"    Attribute '{diff['name']}' added with value: {diff['value2']}")
                        elif diff_type == 'attribute_removed':
                            print(f"    Attribute '{diff['name']}' removed (was: {diff['value1']})")
                        elif diff_type == 'item_changed':
                            print(f"    Item '{diff['key']}' changed: {diff['value1']} -> {diff['value2']}")
                        elif diff_type == 'item_added':
                            print(f"    Item '{diff['key']}' added with value: {diff['value2']}")
                        elif diff_type == 'item_removed':
                            print(f"    Item '{diff['key']}' removed (was: {diff['value1']})")
                        else:
                            print(f"    {diff_type}: {diff}")
                else:
                    print("  No differences found or error occurred")
    
    # Check for the list
    list_history = db.get_object_history("items")
    if list_history:
        print("\nList history:")
        for identity in list_history:
            print(f"  Identity: {identity['identity']['identity_hash']}")
            print(f"  Name: {identity['identity']['name']}")
            print(f"  Versions: {len(identity['versions'])}")
            
            # If we have at least two versions, compare them
            if len(identity['versions']) >= 2:
                first_version = identity['versions'][0]
                last_version = identity['versions'][-1]
                
                print(f"\nComparing first and last versions of list:")
                comparison = db.compare_versions(first_version['version_id'], last_version['version_id'])
                
                if 'differences' in comparison and comparison['differences']:
                    print(f"  Found {len(comparison['differences'])} differences:")
                    for diff in comparison['differences']:
                        diff_type = diff['type']
                        if diff_type == 'item_changed':
                            print(f"    Item at index '{diff['key']}' changed: {diff['value1']} -> {diff['value2']}")
                        elif diff_type == 'item_added':
                            print(f"    Item added at index '{diff['key']}' with value: {diff['value2']}")
                        elif diff_type == 'item_removed':
                            print(f"    Item at index '{diff['key']}' removed (was: {diff['value1']})")
                        else:
                            print(f"    {diff_type}: {diff}")
                else:
                    print("  No differences found or error occurred")
    
    # Find function calls that modified objects
    print("\nFunction calls that modified objects:")
    
    # Get the first object identity if available
    if obj_history and obj_history[0]['identity']['identity_hash']:
        identity_hash = obj_history[0]['identity']['identity_hash']
        modifications = db.db_manager.find_object_modifications(identity_hash)
        
        if modifications:
            print(f"  Found {len(modifications)} function calls that modified the VersionedObject:")
            for mod in modifications:
                print(f"    {mod['function']} at {mod['file']}:{mod['line']}")
                print(f"      Changed from version {mod['before_version']['number']} to {mod['after_version']['number']}")
                if 'local_vars' in mod:
                    print(f"      Used as local variables: {', '.join(mod['local_vars'])}")
                if 'global_vars' in mod:
                    print(f"      Used as global variables: {', '.join(mod['global_vars'])}")
        else:
            print("  No modifications found for the VersionedObject")

if __name__ == "__main__":
    main() 