#!/usr/bin/env python3
"""
PyMonitor Reexecutionner

A tool to reexecute function calls recorded in a PyMonitor database.
"""

import argparse
import logging
import os
import sys

from .runner import Runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Main entry point for the reexecutionner tool."""
    parser = argparse.ArgumentParser(description="PyMonitor Reexecutionner")
    parser.add_argument("db_path", help="Path to the monitoring database file (.db)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen for commands")
    parser.add_argument("--host", default="localhost", help="Host to bind the server")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--background", action="store_true", help="Run executions in background mode")

    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        logger.error(f"Database file not found at {args.db_path}")
        sys.exit(1)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Start the runner
    runner = Runner(
        db_path=args.db_path,
        host=args.host,
        port=args.port,
        background_mode=args.background
    )

    try:
        runner.start()
    except KeyboardInterrupt:
        logger.info("Shutting down reexecutionner...")
    finally:
        runner.stop()

if __name__ == "__main__":
    main()
