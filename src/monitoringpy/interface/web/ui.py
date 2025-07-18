#!/usr/bin/env python3
"""
PyMonitor Web UI

Web UI for exploring PyMonitor databases.
"""

import logging
import os
import sys

try:
    from flask import Flask, render_template
    from flask_cors import CORS
except ImportError:
    print("Flask is required for the web explorer. Install it with: pip install flask flask-cors")
    sys.exit(1)

from monitoringpy.core import FunctionCallRepository, ObjectManager, init_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables used by the Flask app
call_tracker = None
session = None
db_path = None
object_manager = None
api_url = None

def create_ui_app(tracker, api_server_url=None):
    """Create a Flask app for the UI routes

    Args:
        tracker: The FunctionCallTracker instance
        api_server_url: Optional URL to the API server (for separate UI/API mode)
    """
    global call_tracker, api_url
    call_tracker = tracker
    api_url = api_server_url

    # Get the directory of this file
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Create Flask app
    app = Flask(
        __name__,
        template_folder=os.path.join(current_dir, 'templates'),
        static_folder=os.path.join(current_dir, 'static')
    )
    CORS(app)

    # Add a context processor to inject API URL into all templates
    @app.context_processor
    def inject_api_url():
        return {"api_url": api_url}

    # Set up UI routes
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/graph')
    def graph():
        return render_template('graph.html')

    @app.route('/stack-recordings')
    def stack_recordings():
        return render_template('stack_recordings.html')

    @app.route('/stack-recording/<function_id>')
    def stack_recording(function_id):
        return render_template('stack_recording.html', function_id=function_id)

    @app.route('/compare-traces')
    def compare_traces():
        return render_template('compare_traces.html')

    @app.route('/function-call/<call_id>')
    def function_call(call_id):
        return render_template('function_call.html', call_id=call_id)

    @app.route('/sessions')
    def sessions():
        return render_template('sessions.html')

    @app.route('/session/<session_id>')
    def session_detail(session_id):
        return render_template('session_detail.html', session_id=session_id)

    return app

class WebUIExplorer:
    """Web UI for exploring PyMonitor databases."""

    def __init__(self, db_file: str):
        """Initialize the web UI explorer with a database file.

        Args:
            db_file: Path to the SQLite database file
        """
        self.db_file = db_file
        self.host = '127.0.0.1'
        self.port = 5000
        self.debug = False
        self.api_url = None

        # These will be initialized when run() is called
        self.session = None
        self.call_tracker = None
        self.object_manager = None
        self.app = None

    def run(self, host: str = '127.0.0.1', port: int = 5000, debug: bool = False, api_host: str | None = None, api_port: int | None = None):
        """Run the web UI explorer.

        Args:
            host: Host to run the server on
            port: Port to run the server on
            debug: Whether to run in debug mode
            api_host: Optional host for the API server (for separate UI/API mode)
            api_port: Optional port for the API server (for separate UI/API mode)
        """
        global call_tracker, session, db_path, object_manager

        self.host = host
        self.port = port
        self.debug = debug

        # Set API URL if running in separate mode
        if api_host and api_port:
            self.api_url = f"http://{api_host}:{api_port}"

        # Initialize database and trackers
        # Check if the database file exists
        if not os.path.exists(self.db_file):
            logger.error(f"Database file not found: {self.db_file}")
            sys.exit(1)

        # Initialize the database and tracker
        Session = init_db(self.db_file)
        self.session = Session()
        self.object_manager = ObjectManager(self.session)
        self.call_tracker = FunctionCallRepository(self.session)

        # Set global variables for Flask app
        call_tracker = self.call_tracker
        session = self.session
        db_path = self.db_file
        object_manager = self.object_manager

        # Create the Flask app
        self.app = create_ui_app(self.call_tracker, self.api_url)

        try:
            logger.info(f"Starting Web UI server at http://{host}:{port}")
            if self.api_url:
                logger.info(f"Using API server at {self.api_url}")
            self.app.run(host=host, port=port, debug=debug)
        finally:
            if self.session:
                self.session.close()

    def close(self):
        """Close the database session."""
        if self.session:
            self.session.close()
            self.session = None

def run_ui(db_file, host='127.0.0.1', port=5000, debug=False, api_host=None, api_port=None):
    """Run the web UI explorer."""
    explorer = WebUIExplorer(db_file)
    try:
        explorer.run(
            host=host,
            port=port,
            debug=debug,
            api_host=api_host if api_host is not None else None,
            api_port=api_port if api_port is not None else None
        )
    except KeyboardInterrupt:
        logger.info("Web UI server stopped.")
    finally:
        explorer.close()
