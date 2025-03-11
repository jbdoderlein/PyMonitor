#!/usr/bin/env python3
"""
Database Migration Utility for PyMonitor

This script helps migrate existing PyMonitor databases to the latest schema.
It can be run directly to update a database file.
"""

import os
import sys
import argparse
import logging
import sqlite3
import shutil
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backup_database(db_path):
    """Create a backup of the database before migration"""
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return False
        
    backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"Created backup at: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return False

def check_database_schema(db_path):
    """Check the current database schema"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if function_calls table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='function_calls'")
        if not cursor.fetchone():
            logger.error("Database does not contain function_calls table")
            conn.close()
            return False
            
        # Check for return_object_id column
        try:
            cursor.execute("SELECT return_object_id FROM function_calls LIMIT 1")
            logger.info("Database schema is up to date (return_object_id column exists)")
            has_return_object_id = True
        except sqlite3.OperationalError:
            logger.warning("Database schema is outdated (missing return_object_id column)")
            has_return_object_id = False
            
        conn.close()
        return has_return_object_id
    except Exception as e:
        logger.error(f"Error checking database schema: {e}")
        return False

def migrate_database(db_path):
    """Migrate the database to the latest schema"""
    try:
        # First check if migration is needed
        if check_database_schema(db_path):
            logger.info("Database is already up to date, no migration needed")
            return True
            
        # Create backup before migration
        if not backup_database(db_path):
            logger.error("Migration aborted: Failed to create backup")
            return False
            
        # Perform migration
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add return_object_id column to function_calls table
        try:
            cursor.execute("ALTER TABLE function_calls ADD COLUMN return_object_id VARCHAR REFERENCES objects(id)")
            conn.commit()
            logger.info("Successfully added return_object_id column to function_calls table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("Column return_object_id already exists")
            else:
                logger.error(f"Error adding return_object_id column: {e}")
                conn.close()
                return False
                
        # Verify migration was successful
        if check_database_schema(db_path):
            logger.info("Migration completed successfully")
            conn.close()
            return True
        else:
            logger.error("Migration failed: Schema check after migration failed")
            conn.close()
            return False
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="PyMonitor Database Migration Utility")
    parser.add_argument("db_path", help="Path to the database file to migrate")
    parser.add_argument("--check-only", action="store_true", help="Only check schema without migrating")
    parser.add_argument("--force", action="store_true", help="Force migration even if schema appears up to date")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db_path):
        logger.error(f"Database file not found: {args.db_path}")
        return 1
        
    if args.check_only:
        check_database_schema(args.db_path)
        return 0
        
    if args.force or not check_database_schema(args.db_path):
        if migrate_database(args.db_path):
            logger.info(f"Successfully migrated database: {args.db_path}")
            return 0
        else:
            logger.error(f"Failed to migrate database: {args.db_path}")
            return 1
    else:
        logger.info(f"Database is already up to date: {args.db_path}")
        return 0

if __name__ == "__main__":
    sys.exit(main())
    
# Add module entry point
def __main__():
    """Entry point for running as a module"""
    sys.exit(main()) 