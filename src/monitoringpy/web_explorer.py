#!/usr/bin/env python3
"""
PyMonitor Web Explorer

A web-based interface for exploring PyMonitor databases.
"""

import os
import sys
import argparse
import logging
import json
import datetime
from pathlib import Path
import webbrowser
import threading
import time

try:
    from flask import Flask, render_template, request, jsonify, abort, send_from_directory
    from flask_cors import CORS
except ImportError:
    print("Flask is required for the web explorer. Install it with: pip install flask flask-cors")
    sys.exit(1)

from .models import init_db
from .db_operations import DatabaseManager
from .reanimator import Reanimator  # Import the reanimator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables
db_manager = None
db_path = None
reanimator = None  # Add reanimator instance

# Create templates directory if it doesn't exist
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
os.makedirs(template_dir, exist_ok=True)

# Create static directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), 'static')
os.makedirs(static_dir, exist_ok=True)

# JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)

def create_app(db_manager):
    app = Flask(__name__)
    app.json_encoder = DateTimeEncoder

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/db-info')
    def get_db_info():
        global db_path
        return jsonify({'db_path': db_path})

    @app.route('/api/function-calls')
    def get_function_calls():
        search = request.args.get('search', '')
        file_filter = request.args.get('file', '')
        function_filter = request.args.get('function', '')

        function_calls = db_manager.get_all_function_calls()
        filtered_calls = []

        for call in function_calls:
            call_dict = {
                'id': call.id,
                'function': call.function,
                'file': call.file,
                'line': call.line,
                'start_time': call.start_time,
                'end_time': call.end_time,
                'event_type': call.event_type,
                'perf_label': call.perf_label,
                'perf_pkg': call.perf_pkg,
                'perf_dram': call.perf_dram
            }
            
            if search and search.lower() not in call.function.lower():
                continue
            if file_filter and file_filter != call.file:
                continue
            if function_filter and function_filter != call.function:
                continue
            filtered_calls.append(call_dict)

        return jsonify({'function_calls': filtered_calls})

    @app.route('/api/function-call/<function_id>')
    def get_function_call(function_id):
        try:
            function_id = int(function_id)
        except ValueError:
            return jsonify({'error': 'Invalid function ID'}), 400

        function_calls = db_manager.get_all_function_calls()
        function_call = next((call for call in function_calls if call.id == function_id), None)
        
        if not function_call:
            return jsonify({'error': 'Function call not found'}), 404

        call_dict = {
            'id': function_call.id,
            'function': function_call.function,
            'file': function_call.file,
            'line': function_call.line,
            'start_time': function_call.start_time,
            'end_time': function_call.end_time,
            'event_type': function_call.event_type,
            'perf_label': function_call.perf_label,
            'perf_pkg': function_call.perf_pkg,
            'perf_dram': function_call.perf_dram
        }

        details = db_manager.get_function_call_data(function_id)
        return jsonify({
            'function_call': call_dict,
            'details': details
        })

    return app

def open_browser(url):
    """Open the browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open(url)

def run_explorer(db_file, host='127.0.0.1', port=5000, debug=False, open_browser_flag=True):
    """
    Run the web explorer.
    
    Args:
        db_file: Path to the database file
        host: Host to run the server on
        port: Port to run the server on
        debug: Whether to run in debug mode
        open_browser_flag: Whether to open a browser automatically
    """
    global db_manager, db_path, reanimator
    
    # Check if the database file exists
    if not os.path.exists(db_file):
        logger.error(f"Database file not found: {db_file}")
        sys.exit(1)
    
    # Initialize the database manager
    db_path = db_file
    Session = init_db(db_file)
    db_manager = DatabaseManager(Session)
    
    # Initialize the reanimator
    try:
        reanimator = Reanimator(db_file)
        logger.info("Reanimator initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing reanimator: {e}")
        reanimator = None
    
    # Open browser after a delay
    if open_browser_flag:
        url = f"http://{host}:{port}"
        threading.Timer(1.5, open_browser, args=[url]).start()
    
    # Run the Flask app
    app = create_app(db_manager)
    app.run(host=host, port=port, debug=debug)

def main():
    """Command-line entry point"""
    parser = argparse.ArgumentParser(description="PyMonitor Web Explorer")
    parser.add_argument("db_path", help="Path to the database file to explore")
    parser.add_argument("--host", default="127.0.0.1", help="Host to run the server on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the server on (default: 5000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    
    args = parser.parse_args()
    
    run_explorer(
        args.db_path, 
        host=args.host, 
        port=args.port, 
        debug=args.debug, 
        open_browser_flag=not args.no_browser
    )

if __name__ == "__main__":
    main()

# Module entry point
def __main__():
    """Entry point for running as a module"""
    main()