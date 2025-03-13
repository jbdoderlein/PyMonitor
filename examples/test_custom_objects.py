#!/usr/bin/env python3
"""
Test script to verify fixes for attribute storage issues.
"""

import os
import sys
import logging
import datetime
import atexit

# Enable debug logging
os.environ['PYMONITOR_DEBUG'] = '1'

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath('src'))

# Import the monitoring module
from monitoringpy import init_monitoring, pymonitor

class CustomClass:
    """Test class with multiple attributes."""
    def __init__(self, x):
        self.x = x
        self.y = 5
        self.z = "test"
        
    def __repr__(self):
        return f"CustomClass(x={self.x}, y={self.y}, z={self.z})"

@pymonitor
def test_function(obj):
    """Test function that uses a custom object."""
    logger.info(f"Running test_function with {obj}")
    result = obj.x + obj.y
    logger.info(f"Result: {result}")
    return result

def main():
    """Main function to run the test."""
    # Remove any existing test database
    if os.path.exists('test.db'):
        os.remove('test.db')
        logger.info("Removed existing test.db")
    
    # Initialize monitoring
    logger.info("Initializing monitoring")
    monitor = init_monitoring(db_path="test.db")
    
    # Create and use a custom object
    logger.info("Creating custom object")
    obj = CustomClass(10)
    
    # Call the test function
    logger.info("Calling test function")
    result = test_function(obj)
    logger.info(f"Function returned: {result}")
    
    # Stop monitoring - use the cleanup function that's registered with atexit
    logger.info("Stopping monitoring")
    if hasattr(monitor, 'shutdown'):
        monitor.shutdown()
    
    # Check if the database was created
    if os.path.exists('test.db'):
        logger.info("Database file created successfully")
    else:
        logger.error("Database file was not created")
        
    # Run the web explorer
    logger.info("You can now run the web explorer to check the results:")
    logger.info("python -m monitoringpy.web_explorer test.db")

if __name__ == "__main__":
    main() 