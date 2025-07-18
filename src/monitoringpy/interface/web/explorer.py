#!/usr/bin/env python3
"""
PyMonitor Web Explorer

A web-based interface for exploring PyMonitor databases.
"""

import argparse
import logging
import os
import sys

from sqlalchemy.orm import Session

from monitoringpy.core import FunctionCallRepository, ObjectManager, init_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_explorer(db_file: str) -> tuple[Session, FunctionCallRepository, ObjectManager]:
    """Initialize the database and tracker

    Args:
        db_file: Path to the SQLite database file

    Returns:
        Tuple of (session, call_tracker, object_manager)
    """
    # Check if the database file exists
    if not os.path.exists(db_file):
        logger.error(f"Database file not found: {db_file}")
        sys.exit(1)

    # Initialize the database and tracker
    Session = init_db(db_file)
    session = Session()
    object_manager = ObjectManager(session)
    call_tracker = FunctionCallRepository(session)

    return session, call_tracker, object_manager

def run_explorer(
    db_file: str,
    mode: str = 'both',
    ui_host: str = '127.0.0.1',
    ui_port: int = 5000,
    api_host: str = '127.0.0.1',
    api_port: int = 8000,
    debug: bool = False
) -> None:
    """Run the web explorer.

    Args:
        db_file: Path to the SQLite database file
        mode: Mode to run the explorer in ('ui', 'api', or 'both')
        ui_host: Host to run the UI server on
        ui_port: Port to run the UI server on
        api_host: Host to run the API server on
        api_port: Port to run the API server on
        debug: Whether to run in debug mode
    """
    if mode not in ['ui', 'api', 'both']:
        logger.error(f"Invalid mode: {mode}. Must be one of: ui, api, both")
        sys.exit(1)

    # Run the API server if needed
    api_process = None
    if mode in ['api', 'both']:
        from monitoringpy.interface.web.api import run_api

        if mode == 'both':
            # Run the API server in a separate process if we're in 'both' mode
            import multiprocessing
            api_process = multiprocessing.Process(
                target=run_api,
                args=(db_file, api_host, api_port)
            )
            api_process.start()
            logger.info(f"API server started at http://{api_host}:{api_port}")
        else:
            # Run the API server in the main process if we're in 'api' mode
            run_api(db_file, api_host, api_port)

    # Run the UI server if needed
    if mode in ['ui', 'both']:
        from monitoringpy.interface.web.ui import run_ui

        # In 'both' mode, pass the API host and port to the UI server
        if mode == 'both':
            run_ui(db_file, ui_host, ui_port, debug, api_host, api_port)
        else:
            run_ui(db_file, ui_host, ui_port, debug)

    # Stop the API server if it's running
    if api_process and api_process.is_alive():
        api_process.terminate()
        api_process.join()
        logger.info("API server stopped.")

def main():
    """Main function for the explorer command line tool."""
    parser = argparse.ArgumentParser(description='PyMonitor Web Explorer')
    parser.add_argument('db_file', help='Path to the SQLite database file')
    parser.add_argument('--mode', '-m', choices=['ui', 'api', 'both'], default='both',
                        help='Mode to run the explorer in (ui, api, or both)')
    parser.add_argument('--ui-host', default='127.0.0.1', help='Host to run the UI server on')
    parser.add_argument('--ui-port', type=int, default=5000, help='Port to run the UI server on')
    parser.add_argument('--api-host', default='127.0.0.1', help='Host to run the API server on')
    parser.add_argument('--api-port', type=int, default=8000, help='Port to run the API server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')

    args = parser.parse_args()

    run_explorer(
        args.db_file,
        args.mode,
        args.ui_host,
        args.ui_port,
        args.api_host,
        args.api_port,
        args.debug
    )

if __name__ == '__main__':
    main()
