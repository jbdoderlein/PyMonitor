#!/usr/bin/env python3
"""
Test runner script for PyMonitor.
This script discovers and runs all tests in the tests directory.
"""

import unittest
import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_tests():
    """Discover and run all tests in the tests directory."""
    # Get the directory containing this script
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Discover all tests in the tests directory
    test_suite = unittest.defaultTestLoader.discover(test_dir)
    
    # Run the tests
    test_runner = unittest.TextTestRunner(verbosity=2, failfast=True)
    result = test_runner.run(test_suite)
    
    # Return the appropriate exit code
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    sys.exit(run_tests()) 