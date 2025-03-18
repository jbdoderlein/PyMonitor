#!/usr/bin/env python3
"""
Test script to verify how nested lists are stored and reanimated.
"""

import os
import sys
import logging
import json
from pprint import pprint

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.monitoringpy import load_pydb
from src.monitoringpy.db_operations import DatabaseManager
from src.monitoringpy.models import init_db, Object, ObjectItem

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def main():
    # Path to the database file
    db_path = "examples/basic.db"
    
    # Initialize the database session
    Session = init_db(db_path)
    db_manager = DatabaseManager(Session)
    
    # Load the reanimator
    reanimator = load_pydb(db_path)
    
    # Get the first function call
    calls = reanimator.search(limit=1)
    if not calls:
        print("No function calls found in the database")
        return
    
    call_id = calls[0]['id']
    print(f"Examining function call: {call_id}")
    
    # Get the raw data for the ncl variable
    session = Session()
    try:
        # Get the function call
        from sqlalchemy import text
        result = session.execute(text(f"""
            SELECT o.id, o.type_name, o.is_primitive, o.primitive_value
            FROM objects o
            JOIN function_call_globals fcg ON o.id = fcg.object_id
            JOIN function_calls fc ON fcg.function_call_id = fc.id
            WHERE fc.id = :call_id AND fcg.var_name = 'ncl'
        """), {"call_id": call_id})
        
        ncl_obj = result.fetchone()
        if not ncl_obj:
            print("ncl variable not found in globals")
            return
        
        print(f"Found ncl object: {ncl_obj}")
        ncl_id = ncl_obj[0]
        
        # Get the items of the ncl list
        result = session.execute(text(f"""
            SELECT oi.key, oi.value_id
            FROM object_items oi
            WHERE oi.parent_id = :parent_id
            ORDER BY oi.key
        """), {"parent_id": ncl_id})
        
        items = result.fetchall()
        print(f"ncl has {len(items)} items:")
        for item in items:
            key, value_id = item
            print(f"  Item {key}: {value_id}")
            
            # Get the type of this item
            result = session.execute(text(f"""
                SELECT o.id, o.type_name, o.is_primitive, o.primitive_value
                FROM objects o
                WHERE o.id = :id
            """), {"id": value_id})
            
            item_obj = result.fetchone()
            if item_obj is None:
                print(f"    Item object not found for ID: {value_id}")
                continue
                
            print(f"    Type: {item_obj[1]}")
            
            # If it's a list, get its items
            if item_obj[1] == 'list':
                result = session.execute(text(f"""
                    SELECT oi.key, oi.value_id
                    FROM object_items oi
                    WHERE oi.parent_id = :parent_id
                    ORDER BY oi.key
                """), {"parent_id": value_id})
                
                sub_items = result.fetchall()
                print(f"    Sub-items: {len(sub_items)}")
                
                for sub_item in sub_items:
                    sub_key, sub_value_id = sub_item
                    print(f"      Sub-item {sub_key}: {sub_value_id}")
                    
                    # Get the type and value of this sub-item
                    result = session.execute(text(f"""
                        SELECT o.id, o.type_name, o.is_primitive, o.primitive_value
                        FROM objects o
                        WHERE o.id = :id
                    """), {"id": sub_value_id})
                    
                    sub_item_obj = result.fetchone()
                    if sub_item_obj:
                        print(f"        Type: {sub_item_obj[1]}")
                        print(f"        Value: {sub_item_obj[3]}")
    finally:
        session.close()
    
    # Compare with the reanimated object
    print("\nReanimating the function call...")
    reanimated_objects = reanimator.reanimate_objects(call_id)
    ncl = reanimated_objects.get('globals', {}).get('ncl')
    print(f"Reanimated ncl: {ncl}")
    
    # Compare with the expected value
    expected_ncl = [[1, 2, 3], [4, 5, 6]]
    print(f"Expected ncl: {expected_ncl}")
    
    if ncl == expected_ncl:
        print("SUCCESS: Reanimated ncl matches the expected value!")
    else:
        print("FAILURE: Reanimated ncl does not match the expected value.")

if __name__ == "__main__":
    main() 