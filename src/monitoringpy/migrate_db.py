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
    """Migrate the database schema to the latest version"""
    try:
        # Check if migration is needed
        if check_database_schema(db_path):
            logger.info(f"Database schema is already up to date: {db_path}")
            return True
            
        # Create a backup before migration
        if not backup_database(db_path):
            logger.error("Failed to create backup, aborting migration")
            return False
            
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # Start a transaction
            cursor.execute("BEGIN TRANSACTION")
            
            # Check for return_object_id column
            try:
                cursor.execute("SELECT return_object_id FROM function_calls LIMIT 1")
            except sqlite3.OperationalError:
                # Add return_object_id column if it doesn't exist
                logger.info("Adding return_object_id column to function_calls table")
                cursor.execute("ALTER TABLE function_calls ADD COLUMN return_object_id VARCHAR REFERENCES objects(id)")
            
            # Check for auto-increment ID column
            try:
                # Check if id is INTEGER or STRING
                cursor.execute("PRAGMA table_info(function_calls)")
                columns = cursor.fetchall()
                id_column = next((col for col in columns if col[1] == 'id'), None)
                
                if id_column and id_column[2].upper() != 'INTEGER':
                    # Need to migrate from String ID to auto-increment Integer ID
                    logger.info("Migrating from String ID to auto-increment Integer ID")
                    
                    # Create new tables with the updated schema
                    cursor.execute("""
                        CREATE TABLE function_calls_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            event_type VARCHAR,
                            file VARCHAR,
                            function VARCHAR,
                            line INTEGER,
                            start_time TIMESTAMP,
                            end_time TIMESTAMP,
                            return_object_id VARCHAR REFERENCES objects(id),
                            perf_label VARCHAR,
                            perf_pkg FLOAT,
                            perf_dram FLOAT
                        )
                    """)
                    
                    # Copy data from old table to new table
                    cursor.execute("""
                        INSERT INTO function_calls_new 
                        (event_type, file, function, line, start_time, end_time, 
                         return_object_id, perf_label, perf_pkg, perf_dram)
                        SELECT event_type, file, function, line, start_time, end_time, 
                               return_object_id, perf_label, perf_pkg, perf_dram
                        FROM function_calls
                    """)
                    
                    # Create new association tables
                    cursor.execute("""
                        CREATE TABLE function_call_locals_new (
                            function_call_id INTEGER REFERENCES function_calls_new(id),
                            object_id VARCHAR REFERENCES objects(id),
                            arg_name VARCHAR,
                            PRIMARY KEY (function_call_id, object_id, arg_name)
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE function_call_globals_new (
                            function_call_id INTEGER REFERENCES function_calls_new(id),
                            object_id VARCHAR REFERENCES objects(id),
                            var_name VARCHAR,
                            PRIMARY KEY (function_call_id, object_id, var_name)
                        )
                    """)
                    
                    # We can't easily copy data from old association tables to new ones
                    # because we don't have a mapping from old string IDs to new integer IDs
                    # So we'll just start fresh with empty association tables
                    
                    # Drop old tables
                    cursor.execute("DROP TABLE function_call_locals")
                    cursor.execute("DROP TABLE function_call_globals")
                    cursor.execute("DROP TABLE function_calls")
                    
                    # Rename new tables to original names
                    cursor.execute("ALTER TABLE function_calls_new RENAME TO function_calls")
                    cursor.execute("ALTER TABLE function_call_locals_new RENAME TO function_call_locals")
                    cursor.execute("ALTER TABLE function_call_globals_new RENAME TO function_call_globals")
                    
                    # Create indexes
                    cursor.execute("CREATE INDEX idx_function_calls_function ON function_calls(function)")
                    cursor.execute("CREATE INDEX idx_function_calls_file ON function_calls(file)")
                else:
                    # Check if execution_id column exists and remove it if it does
                    execution_id_column = next((col for col in columns if col[1] == 'execution_id'), None)
                    if execution_id_column:
                        logger.info("Removing execution_id column from function_calls table")
                        
                        # SQLite doesn't support DROP COLUMN directly, so we need to create a new table
                        cursor.execute("""
                            CREATE TABLE function_calls_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                event_type VARCHAR,
                                file VARCHAR,
                                function VARCHAR,
                                line INTEGER,
                                start_time TIMESTAMP,
                                end_time TIMESTAMP,
                                return_object_id VARCHAR REFERENCES objects(id),
                                perf_label VARCHAR,
                                perf_pkg FLOAT,
                                perf_dram FLOAT
                            )
                        """)
                        
                        # Copy data from old table to new table
                        cursor.execute("""
                            INSERT INTO function_calls_new 
                            (id, event_type, file, function, line, start_time, end_time, 
                             return_object_id, perf_label, perf_pkg, perf_dram)
                            SELECT id, event_type, file, function, line, start_time, end_time, 
                                   return_object_id, perf_label, perf_pkg, perf_dram
                            FROM function_calls
                        """)
                        
                        # Drop old table
                        cursor.execute("DROP TABLE function_calls")
                        
                        # Rename new table to original name
                        cursor.execute("ALTER TABLE function_calls_new RENAME TO function_calls")
                        
                        # Create indexes
                        cursor.execute("CREATE INDEX idx_function_calls_function ON function_calls(function)")
                        cursor.execute("CREATE INDEX idx_function_calls_file ON function_calls(file)")
            except Exception as e:
                logger.error(f"Error migrating database schema: {e}")
                raise
            
            # Commit the transaction
            conn.commit()
            logger.info("Database migration completed successfully")
            return True
            
        except Exception as e:
            # Rollback the transaction if an error occurs
            conn.rollback()
            logger.error(f"Error during migration: {e}")
            return False
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error migrating database: {e}")
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