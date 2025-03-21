#!/usr/bin/env python3
"""
Fix Human Keys in PyMonitor Database

This script fixes issues with dictionaries that have Human objects as keys
in a PyMonitor database.
"""

import os
import sys
import argparse
import logging
import sqlite3
from datetime import datetime

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backup_database(db_path):
    """Create a backup of the database before fixing"""
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return False
        
    backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        logger.info(f"Created backup at: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return False

def fix_human_keys(db_path):
    """Fix Human keys in the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Find objects with Human keys in object_structure
        cursor.execute("""
            SELECT id, object_structure FROM objects 
            WHERE type_name = 'defaultdict' 
            AND object_structure LIKE '%Human%'
        """)
        
        objects_to_fix = cursor.fetchall()
        
        if not objects_to_fix:
            logger.info("No objects with Human keys found")
            conn.close()
            return True
            
        logger.info(f"Found {len(objects_to_fix)} objects with Human keys")
        
        # Fix each object
        for obj_id, obj_structure in objects_to_fix:
            logger.info(f"Fixing object {obj_id}")
            
            # Convert the structure to use string keys
            # This is a simple approach - we're just removing the problematic structure
            # and letting PyMonitor recreate it with the fixed code
            cursor.execute("""
                UPDATE objects SET object_structure = NULL
                WHERE id = ?
            """, (obj_id,))
            
        # Commit changes
        conn.commit()
        logger.info("Successfully fixed Human keys in objects")
        
        # Now fix ObjectItem entries
        cursor.execute("""
            SELECT id, key FROM object_items
            WHERE key LIKE '%Human%'
        """)
        
        items_to_fix = cursor.fetchall()
        
        if items_to_fix:
            logger.info(f"Found {len(items_to_fix)} object items with Human keys")
            
            for item_id, key in items_to_fix:
                # Convert the key to a string representation
                new_key = f"Human({key})"
                cursor.execute("""
                    UPDATE object_items SET key = ?
                    WHERE id = ?
                """, (new_key, item_id))
                
            conn.commit()
            logger.info("Successfully fixed Human keys in object items")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error fixing Human keys: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Fix Human Keys in PyMonitor Database")
    parser.add_argument("db_path", help="Path to the database file to fix")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db_path):
        logger.error(f"Database file not found: {args.db_path}")
        return 1
        
    # Create a backup first
    if not backup_database(args.db_path):
        logger.error("Failed to create backup, aborting")
        return 1
        
    # Fix Human keys
    if fix_human_keys(args.db_path):
        logger.info(f"Successfully fixed Human keys in database: {args.db_path}")
        return 0
    else:
        logger.error(f"Failed to fix Human keys in database: {args.db_path}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 