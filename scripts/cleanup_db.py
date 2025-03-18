#!/usr/bin/env python3
"""
Database Cleanup Utility for PyMonitor

This script helps clean up a PyMonitor database by removing duplicate function call records
and fixing other common issues.
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
    """Create a backup of the database before cleanup"""
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

def check_database_integrity(db_path):
    """Check the integrity of the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Run SQLite's integrity check
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        
        if result[0] == "ok":
            logger.info("Database integrity check passed")
            integrity_ok = True
        else:
            logger.error(f"Database integrity check failed: {result[0]}")
            integrity_ok = False
            
        conn.close()
        return integrity_ok
    except Exception as e:
        logger.error(f"Error checking database integrity: {e}")
        return False

def find_duplicate_function_calls(db_path):
    """Find duplicate function call IDs in the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Find duplicate IDs
        cursor.execute("""
            SELECT id, COUNT(*) as count
            FROM function_calls
            GROUP BY id
            HAVING count > 1
        """)
        
        duplicates = cursor.fetchall()
        
        if duplicates:
            logger.warning(f"Found {len(duplicates)} duplicate function call IDs")
            for dup in duplicates:
                logger.info(f"ID: {dup[0]} appears {dup[1]} times")
        else:
            logger.info("No duplicate function call IDs found")
            
        conn.close()
        return duplicates
    except Exception as e:
        logger.error(f"Error finding duplicate function calls: {e}")
        return []

def remove_duplicate_function_calls(db_path):
    """Remove duplicate function call records from the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Find duplicate IDs
        duplicates = find_duplicate_function_calls(db_path)
        
        if not duplicates:
            conn.close()
            return True
            
        # For each duplicate ID, keep only the first occurrence
        for dup_id, count in duplicates:
            # Get all records with this ID
            cursor.execute("SELECT rowid FROM function_calls WHERE id = ? ORDER BY rowid", (dup_id,))
            rows = cursor.fetchall()
            
            # Keep the first one, delete the rest
            for row in rows[1:]:
                cursor.execute("DELETE FROM function_calls WHERE rowid = ?", (row[0],))
                logger.info(f"Deleted duplicate record with rowid {row[0]} for ID {dup_id}")
        
        # Commit changes
        conn.commit()
        logger.info("Successfully removed duplicate function call records")
        
        # Verify no more duplicates
        cursor.execute("""
            SELECT id, COUNT(*) as count
            FROM function_calls
            GROUP BY id
            HAVING count > 1
        """)
        
        if cursor.fetchone():
            logger.warning("Some duplicates still remain after cleanup")
            success = False
        else:
            logger.info("All duplicates successfully removed")
            success = True
            
        conn.close()
        return success
    except Exception as e:
        logger.error(f"Error removing duplicate function calls: {e}")
        return False

def vacuum_database(db_path):
    """Vacuum the database to reclaim space and optimize performance"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Run VACUUM to rebuild the database file
        cursor.execute("VACUUM")
        
        conn.close()
        logger.info("Database vacuumed successfully")
        return True
    except Exception as e:
        logger.error(f"Error vacuuming database: {e}")
        return False

def cleanup_database(db_path, vacuum=True):
    """Perform a complete database cleanup"""
    logger.info(f"Starting cleanup of database: {db_path}")
    
    # Create a backup first
    if not backup_database(db_path):
        logger.error("Failed to create backup, aborting cleanup")
        return False
        
    # Check integrity
    if not check_database_integrity(db_path):
        logger.warning("Database integrity check failed, proceeding with caution")
    
    # Remove duplicate function calls
    if not remove_duplicate_function_calls(db_path):
        logger.error("Failed to remove duplicate function calls")
        return False
        
    # Vacuum the database if requested
    if vacuum and not vacuum_database(db_path):
        logger.error("Failed to vacuum database")
        return False
        
    logger.info(f"Database cleanup completed successfully: {db_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="PyMonitor Database Cleanup Utility")
    parser.add_argument("db_path", help="Path to the database file to clean up")
    parser.add_argument("--no-vacuum", action="store_true", help="Skip vacuuming the database")
    parser.add_argument("--check-only", action="store_true", help="Only check for issues without fixing them")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db_path):
        logger.error(f"Database file not found: {args.db_path}")
        return 1
        
    if args.check_only:
        check_database_integrity(args.db_path)
        find_duplicate_function_calls(args.db_path)
        return 0
        
    if cleanup_database(args.db_path, not args.no_vacuum):
        logger.info(f"Successfully cleaned up database: {args.db_path}")
        return 0
    else:
        logger.error(f"Failed to clean up database: {args.db_path}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 